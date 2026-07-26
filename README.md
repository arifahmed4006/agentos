# AgentOS

A 9-layer stack for building and running production-grade AI agents on free-tier infrastructure. Includes LLM gateway with fallback routing, cost controls, observability and eval gates — the layers that separate a demo from a real system.

3 agents included, more coming.

---

## The Stack

| Layer | What | Purpose |
|---|---|---|
| Compute | Oracle Cloud Always-Free VMs | Always-on, zero cost |
| Models | Groq Llama 3.1 8B (default) | Free tier, ~250ms, no GPU needed |
| LLM Gateway | LiteLLM | Fallback routing, budget cap, guardrails |
| Orchestration | n8n | Visual workflows, 400+ integrations |
| Cache | Redis | Session management, LLM response caching |
| Memory | PostgreSQL + Supabase pgvector | Operational data + RAG vector search |
| Observability | Langfuse | Every LLM call traced, latency + cost tracked |
| Evaluation | Promptfoo | Pass/fail gates before anything ships |
| Channels | Evolution API + n8n | WhatsApp + web chat + voice |

---

## Architecture

```
                        ┌─────────────────────────────────────────┐
                        │           CHANNELS (inbound)            │
                        │  WhatsApp · Web Chat · Voice · API      │
                        └────────────────┬────────────────────────┘
                                         │
                        ┌────────────────▼────────────────────────┐
                        │         ORCHESTRATION (n8n)             │
                        │  Classify → Route → Execute → Respond   │
                        └──────┬──────────────────┬───────────────┘
                               │                  │
              ┌────────────────▼───┐    ┌─────────▼──────────────┐
              │   LLM GATEWAY      │    │   MEMORY & RAG         │
              │   LiteLLM          │    │   Supabase pgvector    │
              │   Groq / Gemini    │    │   Redis cache          │
              │   Fallback routing │    │   PostgreSQL           │
              └────────────────────┘    └────────────────────────┘
                               │
              ┌────────────────▼────────────────────────────────┐
              │           OBSERVABILITY & EVAL                  │
              │   Langfuse (traces) · Promptfoo (eval gates)    │
              └─────────────────────────────────────────────────┘
```

Every agent in this repo runs on this stack. The stack provides the infrastructure — agents provide the business logic.

---

## Infrastructure

```
VM1 (Oracle Cloud, 1GB RAM, always-free)
├── n8n (orchestration)
├── Evolution API (WhatsApp channel)
└── Cloudflare tunnel (public HTTPS endpoint)

VM2 (Oracle Cloud, 1GB RAM, always-free)
├── LiteLLM (LLM gateway)
└── Redis (cache + session)

Supabase (free tier)
├── PostgreSQL (operational data)
└── pgvector (RAG embeddings)

Langfuse Cloud (free tier)
└── Observability + eval traces
```

---

## Agents

### Document Chaser
Reads CRM for pending documents, follows up on WhatsApp automatically, validates submissions, updates CRM. Fully autonomous — runs on a schedule, no human in the loop.

**Flow:** CRM poll → find pending docs → WhatsApp follow-up → validate submission → update CRM → notify team

See [agents/document-chaser](agents/document-chaser)

---

### Grocery Price Agent
Send a grocery list on WhatsApp, get back the cheapest option per item across Blinkit, Zepto and Instamart. Real-time price scraping, not cached data.

**Flow:** WhatsApp message → parse items → scrape 3 platforms → compare prices → reply with cheapest per item

See [agents/grocery-price-agent](agents/grocery-price-agent)

---

### RBI Circular Intelligence Agent
RAG-based compliance agent that ingests RBI circulars and answers queries in plain English. 273 circulars (July 2025–July 2026), updated daily by a Playwright scraper. Hybrid vector + BM25 search. Handles compliance questions, recency queries, meta queries, and rejects out-of-scope questions cleanly.

**Flow:** Query → classify type → expand synonyms → embed (Gemini) → hybrid search (pgvector) → generate answer (Groq 70B) → return with citations

**Live demo:** https://strong-dieffenbachia-bdb5ac.netlify.app

**Knowledge base:**
- 273 RBI circulars, 1,038 chunks
- Hybrid search: vector 0.7 weight + BM25 0.3 weight
- Daily scraper at 00:30 UTC
- Embedding: Gemini gemini-embedding-001 at 1536 dimensions

See [agents/rbi-circular-assistant](agents/rbi-circular-assistant)

---

### RBI Circular Voice Agent
Converts the RBI Circular Intelligence Agent into a real-time voice interface. Ask any question about RBI circulars by voice — in Hindi, English, or Hinglish — and get a spoken answer in under 1.5 seconds.

**Flow:** Caller speaks → Deepgram STT (multilingual) → turn detection → Groq LLM → Gemini embed + Supabase search → Sarvam TTS → caller hears answer

**Latency budget per turn:**
| Stage | Time |
|---|---|
| Turn detection | ~500ms |
| Deepgram STT | ~200ms |
| Groq LLM first token | ~200ms |
| Gemini embed + Supabase search | ~400ms (covered by filler line) |
| Sarvam TTS first audio | ~400ms |
| **Total** | **~1–1.5s** |

**Edge cases handled:** Hindi↔English mid-sentence switching · "hello? hello?" reassurance · barge-in interruption · pause detection · background noise (Krisp) · RAG timeout fallback

See [agents/rbi-voice-agent](agents/rbi-voice-agent)

---

## Utilities

### Error Handler
Catches errors from any workflow and sends a WhatsApp alert to the admin. Set this as the Error Workflow in any n8n workflow to get instant notifications when something fails.
See [agents/error-handler](agents/error-handler)

---

## Quick Start

Full setup guide: see [DEPLOYMENT.md](DEPLOYMENT.md)

For local testing only (no WhatsApp):

```bash
git clone https://github.com/arifahmed4006/agentos.git
cd agentos/stack
cp .env.example .env
# Fill in your keys
docker compose up -d
```

Open n8n at http://localhost:5678 and import a workflow from the agents folder.

---

## Why This Stack

**Why Groq instead of Ollama?**
Groq hosts Llama 3.1 8B on GPU infrastructure for free. No laptop running 24/7, no tunnel, no cold starts. Faster than Claude Haiku and Gemini Flash at a fraction of the cost. See [docs/OLLAMA.md](docs/OLLAMA.md) to run locally instead.

**Why n8n instead of code?**
Visual workflows mean non-engineers can read, modify, and debug agent logic. 400+ built-in integrations. Runs self-hosted on the free VM — no SaaS subscription.

**Why Oracle Cloud?**
The Always-Free tier gives 2x AMD VMs (1GB RAM each) that never expire. No credit card traps. Enough compute to run n8n, LiteLLM, Redis, and Evolution API simultaneously.

**Why Supabase?**
PostgreSQL + pgvector in one place. The free tier handles millions of vector operations. No separate vector database to manage.

---

## License

MIT