"""
rbi_scraper_v2.py — RBI circular ingestion (one-shot scrape, re-embeddable forever)

Architecture:
  - Scrape once  → store full_text + all metadata in documents table
  - Re-embed any time → read from documents.full_text, never touch RBI again
  - LLM categorization → one Groq call per doc extracts ALL metadata
  - Structural chunking → every chunk anchored with circular identity
  - Circular lineage → references, supersessions stored for graph queries

Modes:
  python rbi_scraper_v2.py backfill --years 1   # full historical load
  python rbi_scraper_v2.py daily                 # today's new circulars
  python rbi_scraper_v2.py reembed               # re-embed from stored full_text (no scraping)
  python rbi_scraper_v2.py test --url <url>      # test single circular

Env vars (from .env):
  LITELLM_BASE_URL, LITELLM_API_KEY, EMBED_MODEL
  SUPABASE_URL, SUPABASE_KEY
"""

import os
import re
import sys
import time
import json
import argparse
import datetime as dt
from io import BytesIO

import httpx
import pdfplumber
from openai import OpenAI
from supabase import create_client
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
INDEX_URL   = "https://www.rbi.org.in/scripts/bs_circularindexdisplay.aspx"
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding")
EMBED_DIMS  = 1536
CHUNK_STRATEGY = "v2_structural"   # bump this when chunking logic changes
MONTHS = ["January","February","March","April","May","June",
          "July","August","September","October","November","December"]

_llm = OpenAI(
    base_url=os.getenv("LITELLM_BASE_URL"),
    api_key=os.getenv("LITELLM_API_KEY")
)
_db = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


# ── Text cleaning ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Remove navigation noise, page numbers, duplicate lines."""
    NOISE_EXACT = {
        'skip to main content', 'selected', 'change language', 'search the website',
        'search', 'home', 'about us', 'notification', 'press releases',
        'publications', 'legal framework', 'research', 'statistics',
        'regulatory reporting', 'index to rbi circulars', 'हिंदी',
        'back to previous page', 'archives',
    }
    NOISE_STARTSWITH = (
        'home notifications', 'home ▼', 'about us ▼', 'notification ▼',
        'speeches', 'publications ▼', 'legal framework ▼', 'research ▼',
        'statistics ▼', 'regulatory reporting ▼',
    )

    lines   = text.split('\n')
    cleaned = []
    seen    = set()

    for line in lines:
        s = line.strip()
        if not s:
            continue
        sl = s.lower()

        # Navigation noise
        if sl in NOISE_EXACT:
            continue
        if any(sl.startswith(p) for p in NOISE_STARTSWITH):
            continue

        # Year-archive navigation (e.g. "2026 2025 2024 2023 ...")
        if re.match(r'^(\d{4}\s*){3,}$', s):
            continue

        # Page numbers / standalone digits
        if re.match(r'^Page \d+ of \d+$', s, re.I):
            continue
        if re.match(r'^\d{1,3}$', s):
            continue

        # File-size annotations like "(256 kb)"
        if re.match(r'^\(\d+\s*kb\)$', s, re.I):
            continue

        # Very short noise lines
        if len(s) < 15:
            continue

        # ALL-CAPS short headers (navigation labels)
        if s.isupper() and len(s) < 80:
            continue

        # Deduplicate
        if sl in seen:
            continue
        seen.add(sl)

        cleaned.append(s)

    result = '\n'.join(cleaned)
    # Replace smart quotes that break JSON generation
    result = result.replace('\u2018', "'").replace('\u2019', "'")
    result = result.replace('\u201c', '"').replace('\u201d', '"')
    result = result.replace('\u2013', '-').replace('\u2014', '-')
    return result


# ── LLM metadata extraction ───────────────────────────────────────────────────

METADATA_PROMPT = """You are an expert RBI circular analyst.
Analyze this RBI circular and return ONLY a valid JSON object with these exact keys.
Do not include any text before or after the JSON.

{{
  "category": "<exactly one from the list below>",
  "applicable_entities": ["<entity1>", "<entity2>"],
  "circular_number": "<e.g. RBI/2025-26/47 or FEMA.10/2025 or null>",
  "summary": "<one sentence: what specifically changed and who it affects>",
  "key_provisions": ["<provision 1>", "<provision 2>", "<provision 3>"],
  "effective_date": "<date string or 'immediate' or 'as specified' or null>",
  "supersedes_circulars": ["<circular number or ref>"],
  "amendment_of": "<circular number this amends, or null>",
  "references_to": ["<other circular numbers mentioned>"],
  "is_master_direction": <true or false>,
  "is_amendment": <true or false>
}}

CATEGORIES (pick exactly one):
- KYC & CKYC
- Foreign Exchange & FEMA
- Payment Systems
- NBFCs & Financial Institutions
- Co-operative & Rural Banks
- Monetary Policy
- Government Securities
- Cybersecurity & IT
- Credit Information
- Priority Sector Lending
- Banking Regulation

CATEGORIZATION RULES — READ CAREFULLY:

RULE 1: Category = SUBJECT MATTER, never the entity type.
A circular about "Digital Banking for UCBs" → Cybersecurity & IT (NOT Co-operative & Rural Banks)
A circular about "KYC norms for NBFCs" → Consumer Protection & KYC (NOT NBFCs & Financial Institutions)
A circular about "Priority Sector Lending for RRBs" → Priority Sector Lending (NOT Co-operative & Rural Banks)

RULE 2: Category-by-category disambiguation:

"KYC & CKYC":
  USE FOR: CKYCR platform operations, uploading/downloading KYC records to/from Central KYC Registry,
           responsibility of entities on CKYCR, Protean eGov registry, CKYC identifier
  DO NOT USE FOR: General KYC compliance, AML, customer due diligence, KYC document requirements

"KYC & CKYC":
  USE FOR: KYC norms (general), AML, Anti-Money Laundering, customer due diligence (CDD),
           PML Act compliance, Ombudsman, grievance redressal, limiting liability,
           unauthorised electronic transactions, responsible business conduct
  DO NOT USE FOR: CKYC registry operations (use CKYC category)

"Cybersecurity & IT":
  USE FOR: Internet banking, mobile banking, digital banking channels, IT frameworks,
           outsourcing of IT services, cybersecurity, data security, information security,
           digital payments security, fintech, cloud computing, data localisation
  DO NOT USE FOR: Payment system operations like UPI/NEFT (use Payment Systems)

"Payment Systems":
  USE FOR: UPI, NEFT, RTGS, IMPS, NACH, BBPS, prepaid payment instruments (wallets),
           payment aggregators, payment gateways, card networks, PPI
  DO NOT USE FOR: Internet/mobile banking technology (use Cybersecurity & IT)

"Foreign Exchange & FEMA":
  USE FOR: FEMA notifications, LRS (Liberalised Remittance Scheme), ECB (External Commercial
           Borrowing), FPI, NRI accounts, FCNR, overseas investments, trade settlement in INR,
           authorised dealer instructions, forex regulations
  DO NOT USE FOR: Domestic payment systems even if they involve foreign banks

"NBFCs & Financial Institutions":
  USE FOR: NBFC registration, scale-based regulation, NBFC-specific capital/liquidity norms,
           HFC regulations, AIFI directions, factoring, microfinance (NBFC-MFI specific rules),
           NBFC governance, concentration risk for NBFCs
  DO NOT USE FOR: KYC for NBFCs (use Consumer Protection & KYC),
                  Credit info for NBFCs (use Credit Information),
                  PSL for NBFCs (use Priority Sector Lending)

"Co-operative & Rural Banks":
  USE FOR: Cooperative bank licensing, formation, mergers, amalgamation, governance structure,
           inclusion/exclusion from Second Schedule, UCB conversion to SFB,
           rural cooperative bank governance, RRB recapitalisation/merger
  DO NOT USE FOR: Subject-matter circulars (KYC/IT/payments/credit) that merely apply to UCBs/RRBs

"Monetary Policy":
  USE FOR: CRR (Cash Reserve Ratio), SLR (Statutory Liquidity Ratio), repo rate, reverse repo,
           LAF (Liquidity Adjustment Facility), MSF, bank rate, MPC decisions,
           open market operations, standing deposit facility
  DO NOT USE FOR: Interest rate caps on loans (use Banking Regulation)

"Government Securities":
  USE FOR: G-Sec, Treasury Bills, dated securities, SDLs, NDS-OM platform access,
           HTM/AFS/HFT portfolio, open market operations (OMO), bond issuance
  DO NOT USE FOR: Corporate bonds, debentures (use Banking Regulation)

"Credit Information":
  USE FOR: Credit Information Companies (CICs), CIBIL, credit bureau reporting,
           credit information submission timelines, credit scores, NeSL
  DO NOT USE FOR: NPA classification (use Banking Regulation),
                  CKYC registry (use CKYC category)

"Priority Sector Lending":
  USE FOR: PSL targets and classification, agriculture lending, MSME lending targets,
           weaker sections, housing loans under PSL, PSL certificates (PSLCs),
           adjusted net bank credit (ANBC) calculations
  DO NOT USE FOR: General MSME or agriculture circulars not about PSL targets

"Banking Regulation" (DEFAULT):
  USE FOR: Capital adequacy (CRAR), NPA/stressed asset classification, provisioning norms,
           large exposure framework, concentration risk, interest rate on loans/deposits,
           bank licensing, branch authorisation, merger of banks, dividend policy,
           board governance of commercial banks, prudential norms — anything not fitting above
  USE AS LAST RESORT: Only when no other category clearly fits

APPLICABLE ENTITIES (pick all that apply from):
Commercial Banks, Private Banks, PSBs, SFBs (Small Finance Banks),
UCBs (Urban Co-operative Banks), RRBs (Regional Rural Banks),
NBFCs, HFCs, AIFIs, ARCs, Payment Banks, LABs, Primary Dealers,
All Regulated Entities

RULES:
- is_amendment = true if title contains "Amendment"
- is_master_direction = true if title contains "Master Direction" or "Master Circular"
- supersedes_circulars = list circulars explicitly superseded/withdrawn
- amendment_of = the single circular being amended (if this is an amendment)
- references_to = all other RBI circular numbers mentioned in the text
- key_provisions = 2-4 most important actionable changes (not headings)
- summary must be specific (mention what rate/requirement/entity changed)

Circular Title: {title}
Circular Date: {date}
Circular Content (first 3000 chars):
{content}
"""

def extract_metadata_llm(title: str, date: str, content: str) -> dict:
    """Single Groq call to extract all metadata from a circular."""
    # Clean smart quotes that break JSON generation
    def _clean(s):
        return (str(s)
            .replace('‘',"'").replace('’',"'")
            .replace('“','"').replace('”','"')
            .replace('–','-').replace('—','-'))

    prompt = (METADATA_PROMPT
        .replace("{title}", _clean(title))
        .replace("{date}", date)
        .replace("{content}", _clean(content[:1500]))
    )
    
    for attempt in range(4):
        try:
            # Use gemini-flash as backup if groq fails repeatedly
            model = "llama-groq" if attempt < 2 else "gemini-flash"
            
            resp = _llm.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a JSON API. Always respond with valid JSON only. No markdown, no explanation, no code fences."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=1500,
            )
            raw = resp.choices[0].message.content.strip()
            
            # Aggressively clean the response
            raw = re.sub(r'```(?:json)?\s*', '', raw)
            raw = raw.strip('`').strip()
            
            # Find JSON object in response
            start = raw.find('{')
            end = raw.rfind('}') + 1
            if start >= 0 and end > start:
                raw = raw[start:end]
            
            result = json.loads(raw)
            return result
            
        except json.JSONDecodeError as e:
            print(f"   ⚠ LLM returned invalid JSON (attempt {attempt+1}): {str(e)[:50]}")
            if attempt < 3:
                time.sleep(5 * (attempt + 1))
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                wait = 30 * (attempt + 1)
                print(f"   ⚠ Rate limit, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"   ⚠ Metadata LLM error: {e}")
                time.sleep(5)
    
    # Return safe defaults if all attempts fail
    print(f"   ⚠ Using defaults for: {title[:50]}")
    return {
        "category": "Banking Regulation",
        "applicable_entities": [],
        "circular_number": extract_circular_number_regex(content),
        "summary": title,
        "key_provisions": [],
        "effective_date": None,
        "supersedes_circulars": [],
        "amendment_of": None,
        "references_to": [],
        "is_master_direction": "master direction" in title.lower() or "master circular" in title.lower(),
        "is_amendment": "amendment" in title.lower(),
    }


def extract_circular_number_regex(text: str) -> str | None:
    """Extract RBI circular number from text using regex."""
    patterns = [
        r'RBI/\d{4}-\d{2,4}/\d+',
        r'FEMA\.\d+(?:/[A-Z]+)?/\d{4}(?:-\d{2})?',
        r'A\.P\.\s*\(DIR Series\)\s*Circular No\.\s*\d+',
        r'DBOD\.No\.[A-Z.]+/\d+',
        r'DOR\.[A-Z.]+/\d+',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0)
    return None


# ── Structural chunking ───────────────────────────────────────────────────────

def structural_chunk(full_text: str, identity_anchor: str,
                     max_chars: int = 1400) -> list[str]:
    """
    Split circular into logical sections.
    Every chunk is prefixed with identity_anchor so the vector itself
    carries which circular it came from.
    """
    # Try to split on numbered sections (1., 2., (a), (b), etc.)
    section_patterns = [
        r'\n(?=\d+\.\s+[A-Z])',          # "1. Directions..."
        r'\n(?=[A-Z][A-Z\s]{4,}:)',       # "DIRECTIONS:", "GUIDELINES:"
        r'\n(?=\([a-z]\)\s)',              # "(a) ", "(b) "
        r'\n(?=Paragraph\s+\d+)',          # "Paragraph 3"
        r'\n(?=Article\s+\d+)',            # "Article 5"
    ]

    sections = [full_text]
    for pat in section_patterns:
        new_sections = []
        for sec in sections:
            parts = re.split(pat, sec)
            new_sections.extend(p for p in parts if p.strip())
        sections = new_sections

    # Now group sections into chunks under max_chars
    chunks = []
    current = ""

    for sec in sections:
        if len(current) + len(sec) + 1 <= max_chars:
            current += "\n" + sec if current else sec
        else:
            if current.strip():
                chunks.append(identity_anchor + "\n" + current.strip())
            # If single section is too long, split by paragraph
            if len(sec) > max_chars:
                paras = re.split(r'\n\s*\n', sec)
                para_buf = ""
                for para in paras:
                    if len(para_buf) + len(para) + 1 <= max_chars:
                        para_buf += "\n" + para if para_buf else para
                    else:
                        if para_buf.strip():
                            chunks.append(identity_anchor + "\n" + para_buf.strip())
                        para_buf = para
                if para_buf.strip():
                    current = para_buf
                else:
                    current = ""
            else:
                current = sec

    if current.strip():
        chunks.append(identity_anchor + "\n" + current.strip())

    # Fallback: if we got nothing, return the whole text as one chunk
    if not chunks:
        chunks = [identity_anchor + "\n" + full_text[:max_chars*3]]

    return chunks


# ── Embeddings ────────────────────────────────────────────────────────────────

def embed_batch(text_chunks: list[str]) -> list[list[float]]:
    MAX_BATCH = 50
    all_vectors = []
    for i in range(0, len(text_chunks), MAX_BATCH):
        batch = text_chunks[i:i + MAX_BATCH]
        for attempt in range(5):
            try:
                resp = _llm.embeddings.create(
                    model=EMBED_MODEL,
                    input=batch,
                    dimensions=EMBED_DIMS,
                )
                all_vectors.extend([d.embedding for d in resp.data])
                break
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    wait = 20 * (attempt + 1)
                    print(f"   rate limit, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        else:
            raise RuntimeError("Embedding failed after 5 retries")
    return all_vectors


# ── Supabase persistence ──────────────────────────────────────────────────────

def upsert_document(title, url, published_date, full_text, metadata) -> int:
    """Upsert document with all metadata. Returns doc_id."""
    row = {
        "title":                title,
        "url":                  url,
        "published_date":       str(published_date),
        "full_text":            full_text,
        "category":             metadata.get("category", "Banking Regulation"),
        "circular_number":      metadata.get("circular_number"),
        "summary":              metadata.get("summary"),
        "applicable_entities":  metadata.get("applicable_entities", []),
        "key_provisions":       metadata.get("key_provisions", []),
        "effective_date":       metadata.get("effective_date"),
        "supersedes_circulars": metadata.get("supersedes_circulars", []),
        "amendment_of":         metadata.get("amendment_of"),
        "references_to":        metadata.get("references_to", []),
        "is_master_direction":  metadata.get("is_master_direction", False),
        "is_amendment":         metadata.get("is_amendment", False),
        "scrape_status":        "scraped",
    }
    result = _db.table("documents").upsert(row, on_conflict="url").execute()
    return result.data[0]["id"]


def save_chunks(doc_id, title, url, published_date, category,
                circular_number, chunks, vectors):
    """Delete old chunks and insert new ones."""
    _db.table("document_chunks").delete().eq("document_id", doc_id).execute()

    # Build identity for chunk metadata
    payload = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        payload.append({
            "document_id":    doc_id,
            "chunk_index":    i,
            "content":        chunk,
            "embedding":      vec,
            "title":          title,
            "url":            url,
            "published_date": str(published_date),
            "category":       category,
        })

    # Insert in batches of 50
    for i in range(0, len(payload), 50):
        _db.table("document_chunks").insert(payload[i:i+50]).execute()

    # Mark document as embedded
    _db.table("documents").update({
        "embedded_at":     dt.datetime.utcnow().isoformat(),
        "chunk_strategy":  CHUNK_STRATEGY,
        "scrape_status":   "embedded",
    }).eq("id", doc_id).execute()

    return len(payload)


def save_relationships(doc_id, metadata):
    """Store circular lineage relationships."""
    rels = []
    for ref in (metadata.get("supersedes_circulars") or []):
        if ref:
            rels.append({
                "from_document_id": doc_id,
                "to_circular_number": ref,
                "relationship_type": "supersedes"
            })
    if metadata.get("amendment_of"):
        rels.append({
            "from_document_id": doc_id,
            "to_circular_number": metadata["amendment_of"],
            "relationship_type": "amends"
        })
    for ref in (metadata.get("references_to") or []):
        if ref:
            rels.append({
                "from_document_id": doc_id,
                "to_circular_number": ref,
                "relationship_type": "references"
            })
    if rels:
        # Delete old relationships first
        _db.table("circular_relationships").delete()\
            .eq("from_document_id", doc_id).execute()
        _db.table("circular_relationships").insert(rels).execute()


def already_ingested(url) -> int | None:
    res = _db.table("documents").select("id").eq("url", url).execute().data
    return res[0]["id"] if res else None


def has_full_text(doc_id) -> bool:
    res = _db.table("documents").select("full_text")\
        .eq("id", doc_id).execute().data
    if not res:
        return False
    return bool(res[0].get("full_text"))


# ── Content extraction ────────────────────────────────────────────────────────

def extract_text_from_page(context, url) -> str:
    """Extract clean text from circular page using table.tablebg selector."""
    page = context.new_page()
    text = ""
    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        time.sleep(1.5)

        # Primary: table.tablebg (confirmed working across all circular types)
        el = page.query_selector("table.tablebg")
        if el:
            raw = el.inner_text()
            text = clean_text(raw)

        # Fallback: if content too short, try PDF link
        if len(text) < 300:
            pdf_link = page.query_selector(
                "a[href$='.pdf'], a[href$='.PDF'], "
                "a[href*='/rdocs/'], a[href*='rbidocs']"
            )
            if pdf_link:
                href = pdf_link.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = "https://www.rbi.org.in" + href
                pdf_text = extract_pdf_text(href)
                if pdf_text and len(pdf_text) > len(text):
                    text = clean_text(pdf_text)

        # Last resort: full body text
        if len(text) < 300:
            raw = page.inner_text("body")
            text = clean_text(raw)

    except Exception as e:
        print(f"   ! extraction error {url}: {e}")
    finally:
        page.close()

    return text


def extract_pdf_text(pdf_url: str) -> str:
    """Download and extract text from PDF."""
    try:
        data = httpx.get(pdf_url, timeout=60, follow_redirects=True).content
        with pdfplumber.open(BytesIO(data)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        print(f"   ! pdf error {pdf_url}: {e}")
        return ""


# ── Index navigation ──────────────────────────────────────────────────────────

def select_month(page, year, month_name):
    page.get_by_role("link", name=str(year), exact=True).first.click()
    page.wait_for_timeout(800)
    page.get_by_role("link", name=month_name, exact=True).first.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)


def parse_rows(page) -> list[dict]:
    out = []
    for row in page.query_selector_all("table tr"):
        cols = row.query_selector_all("td")
        if len(cols) < 4:
            continue
        link_el = cols[0].query_selector("a")
        if not link_el:
            continue
        href = link_el.get_attribute("href") or ""
        if "BS_CircularIndexDisplay.aspx?Id=" not in href and "Id=" not in href:
            continue
        if not href.startswith("http"):
            href = "https://www.rbi.org.in/scripts/" + href.lstrip("/")
        date_text = cols[1].inner_text().strip()
        try:
            pub = dt.datetime.strptime(date_text, "%d.%m.%Y").date()
        except ValueError:
            continue
        title = cols[3].inner_text().strip() or cols[0].inner_text().strip()
        out.append({"url": href, "date": pub, "title": title})
    return out


def months_to_cover(years_back=None, since=None):
    today = dt.date.today()
    if since is None:
        since = today.replace(year=today.year - (years_back or 1))
    y, m = since.year, since.month
    while (y, m) <= (today.year, today.month):
        yield y, MONTHS[m - 1]
        m += 1
        if m > 12:
            m, y = 1, y + 1


# ── Core ingestion ────────────────────────────────────────────────────────────

def process_circular(context, row, force_rescrape=False) -> tuple[str, int]:
    """
    Full pipeline for one circular.
    Returns (status, chunk_count).
    status: 'new' | 'updated' | 'skipped' | 'failed'
    """
    url   = row["url"]
    title = row["title"]
    date  = row["date"]

    existing_id = already_ingested(url)

    # In daily mode, skip if already fully embedded
    if existing_id and not force_rescrape:
        if has_full_text(existing_id):
            return "skipped", 0

    # ── Step 1: Extract text ──────────────────────────────────────────────────
    print(f"   → scraping...")
    text = extract_text_from_page(context, url)
    if len(text) < 100:
        print(f"   ✗ insufficient content ({len(text)} chars)")
        return "failed", 0

    # ── Step 2: LLM metadata extraction ──────────────────────────────────────
    print(f"   → extracting metadata (LLM)...")
    metadata = extract_metadata_llm(title, str(date), text)

    # Fallback circular number from regex if LLM missed it
    if not metadata.get("circular_number"):
        metadata["circular_number"] = extract_circular_number_regex(text)

    print(f"   → category: {metadata['category']}")
    print(f"   → circular_number: {metadata.get('circular_number')}")
    print(f"   → entities: {metadata.get('applicable_entities', [])}")

    # ── Step 3: Upsert document with all metadata ─────────────────────────────
    doc_id = upsert_document(title, url, date, text, metadata)

    # ── Step 4: Save circular relationships ───────────────────────────────────
    save_relationships(doc_id, metadata)

    # ── Step 5: Build identity anchor for chunks ──────────────────────────────
    circ_num = metadata.get("circular_number") or "RBI"
    entities = ", ".join(metadata.get("applicable_entities", [])[:3])
    identity = (
        f"[Circular: {circ_num} | Date: {date} | "
        f"Category: {metadata['category']} | "
        f"Applies to: {entities or 'All Regulated Entities'} | "
        f"Title: {title}]"
    )
    if metadata.get("amendment_of"):
        identity = identity.rstrip("]") + f" | Amends: {metadata['amendment_of']}]"
    if metadata.get("is_master_direction"):
        identity = identity.rstrip("]") + " | TYPE: Master Direction]"

    # ── Step 6: Chunk ─────────────────────────────────────────────────────────
    chunks = structural_chunk(text, identity)
    print(f"   → {len(chunks)} chunks")

    # ── Step 7: Embed ─────────────────────────────────────────────────────────
    print(f"   → embedding...")
    vectors = embed_batch(chunks)

    # ── Step 8: Save chunks ───────────────────────────────────────────────────
    n = save_chunks(
        doc_id, title, url, date,
        metadata["category"],
        metadata.get("circular_number"),
        chunks, vectors
    )

    status = "new" if not existing_id else "updated"
    print(f"   ✓ {status} | {n} chunks | {metadata['category']}")
    return status, n


# ── Re-embed from stored full_text (no scraping) ──────────────────────────────

def run_reembed():
    """
    Re-embed all documents from stored full_text.
    Never touches the RBI website.
    """
    print("=== Re-embed from stored full_text ===")
    docs = _db.table("documents")\
        .select("id, title, url, published_date, full_text, category, "
                "circular_number, applicable_entities, amendment_of, "
                "is_master_direction")\
        .not_.is_("full_text", "null")\
        .order("published_date")\
        .execute().data

    print(f"Found {len(docs)} documents with full_text")
    total_chunks = 0
    failed = 0

    for i, doc in enumerate(docs, 1):
        title  = doc["title"]
        url    = doc["url"]
        date   = doc["published_date"]
        text   = doc["full_text"]
        cat    = doc.get("category", "Banking Regulation")
        circ   = doc.get("circular_number")
        ents   = doc.get("applicable_entities") or []

        print(f"\n[{i}/{len(docs)}] {title[:60]}")

        try:
            entities_str = ", ".join(ents[:3]) if ents else "All Regulated Entities"
            identity = (
                f"[Circular: {circ or 'RBI'} | Date: {date} | "
                f"Category: {cat} | "
                f"Applies to: {entities_str} | "
                f"Title: {title}]"
            )
            if doc.get("amendment_of"):
                identity = identity.rstrip("]") + f" | Amends: {doc['amendment_of']}]"
            if doc.get("is_master_direction"):
                identity = identity.rstrip("]") + " | TYPE: Master Direction]"

            chunks  = structural_chunk(text, identity)
            vectors = embed_batch(chunks)
            n = save_chunks(
                doc["id"], title, url, date,
                cat, circ, chunks, vectors
            )
            total_chunks += n
            print(f"   ✓ {n} chunks")

        except Exception as e:
            print(f"   ✗ failed: {e}")
            failed += 1
            continue

        time.sleep(2)  # rate limit for embedding API

    print(f"\n=== Re-embed done: {len(docs)-failed} docs, "
          f"{total_chunks} total chunks, {failed} failed ===")


# ── Single URL test mode ──────────────────────────────────────────────────────

def run_test(url: str):
    """Test full pipeline on a single URL without saving to DB."""
    print(f"=== TEST MODE: {url} ===\n")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (AgentOS RBI ingest; contact: admin@paperlight.in)"
        )
        page = context.new_page()
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        time.sleep(1.5)

        # Get title from page
        rows = parse_rows(page)
        title = rows[0]["title"] if rows else "Test Circular"
        date = rows[0]["date"] if rows else dt.date.today()
        page.close()

        # Extract
        text = extract_text_from_page(context, url)
        print(f"Extracted text length: {len(text)} chars")
        print(f"\nFirst 500 chars:\n{text[:500]}")
        print(f"\nLast 200 chars:\n{text[-200:]}")

        # Metadata
        print("\n=== LLM METADATA ===")
        metadata = extract_metadata_llm(title, str(date), text)
        print(json.dumps(metadata, indent=2))

        # Chunks
        circ_num = metadata.get("circular_number") or "RBI"
        identity = f"[Circular: {circ_num} | Date: {date} | {metadata['category']} | {title}]"
        chunks = structural_chunk(text, identity)
        print(f"\n=== CHUNKS ({len(chunks)} total) ===")
        for i, chunk in enumerate(chunks):
            print(f"\n--- Chunk {i+1} ({len(chunk)} chars) ---")
            print(chunk[:400])

        browser.close()


# ── Orchestration ─────────────────────────────────────────────────────────────

def run(mode, years_back, since, debug):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not debug, slow_mo=50 if debug else 0)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (AgentOS RBI ingest; contact: admin@paperlight.in)"
        )
        page = context.new_page()
        page.goto(INDEX_URL, timeout=60000, wait_until="domcontentloaded")

        if mode == "daily":
            print("=== Daily incremental ===")
            rows = parse_rows(page)
            new_count = upd_count = skip_count = fail_count = 0
            for row in rows:
                print(f"\n• {row['title'][:65]}")
                status, n = process_circular(context, row, force_rescrape=False)
                if status == "new":    new_count += 1
                elif status == "updated": upd_count += 1
                elif status == "skipped": skip_count += 1
                else: fail_count += 1
                if status not in ("skipped",):
                    time.sleep(8)
            print(f"\n=== Done: {new_count} new, {upd_count} updated, "
                  f"{skip_count} skipped, {fail_count} failed ===")

        else:  # backfill
            print(f"=== Backfill ({'since '+str(since) if since else str(years_back)+'y'}) ===")
            total_new = total_upd = total_fail = 0

            for year, month in months_to_cover(years_back, since):
                try:
                    select_month(page, year, month)
                except Exception as e:
                    print(f"\n! Could not open {month} {year}: {e}")
                    continue

                rows = parse_rows(page)
                print(f"\n── {month} {year}: {len(rows)} circulars ──")

                for row in rows:
                    print(f"\n• {row['title'][:65]}")
                    status, n = process_circular(context, row, force_rescrape=True)
                    if status == "new":    total_new += 1
                    elif status == "updated": total_upd += 1
                    elif status == "failed":  total_fail += 1
                    time.sleep(8)

            print(f"\n=== Done: {total_new} new, {total_upd} updated, "
                  f"{total_fail} failed ===")

        browser.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="RBI Circular Scraper v2")
    sub = ap.add_subparsers(dest="mode", required=True)

    b = sub.add_parser("backfill", help="Historical load")
    b.add_argument("--years", type=int, default=1)
    b.add_argument("--since", type=str, help="YYYY-MM-DD")
    b.add_argument("--debug", action="store_true")

    d = sub.add_parser("daily", help="Today's new circulars")
    d.add_argument("--debug", action="store_true")

    r = sub.add_parser("reembed", help="Re-embed from stored full_text (no scraping)")

    t = sub.add_parser("test", help="Test single circular")
    t.add_argument("--url", required=True)

    args = ap.parse_args()

    if args.mode == "reembed":
        run_reembed()
    elif args.mode == "test":
        run_test(args.url)
    else:
        since = dt.date.fromisoformat(args.since) if getattr(args, "since", None) else None
        run(args.mode, getattr(args, "years", None), since, getattr(args, "debug", False))


if __name__ == "__main__":
    main()
