# RBI Circular Intelligence Agent

An RAG-based agent that ingests RBI circulars and answers compliance queries in plain English. Built on Oracle Cloud free tier.

## Live Demo
- Frontend: https://strong-dieffenbachia-bdb5ac.netlify.app/
- API: POST https://rbi-api.paperlight.in/webhook/rbi-query

## Architecture
User -> Netlify (frontend.html) -> Cloudflare Tunnel -> n8n (VM1) -> LiteLLM Gateway (VM2) -> Groq + Gemini -> Supabase pgvector + Redis + Langfuse

## Stack
| Layer | Tool |
|-------|------|
| Orchestration | n8n v6 workflow |
| LLM generation | Groq llama-3.3-70b-versatile via LiteLLM |
| Embeddings | Gemini gemini-embedding-001 (1536 dims) |
| Vector search | Supabase pgvector hybrid search |
| Caching | Redis via LiteLLM (TTL 3600s) |
| Observability | Langfuse |
| Scraper | Playwright + Python |
| Frontend | Single HTML file on Netlify |
| Tunnel | Cloudflare tunnel |

## Infrastructure
- VM1: n8n + Cloudflare tunnel (1GB RAM, Ubuntu 22.04) — Oracle Cloud free tier
- VM2: LiteLLM + Redis (1GB RAM, Ubuntu 22.04) — Oracle Cloud free tier
- Supabase: free tier with pgvector extension
- Netlify: free tier for frontend

## Knowledge Base
- 273 RBI circulars (July 2025 to July 2026)
- 1,038 chunks with identity anchors
- Hybrid search: vector 0.7 weight + BM25 0.3 weight
- Daily scraper at 00:30 UTC

## Query Types
- RAG: compliance questions answered from circulars with citations
- Recency: latest circulars, this month, last week
- Meta: how many circulars do you have
- Out-of-scope: non-RBI queries rejected cleanly

## Files
| File | Purpose |
|------|---------|
| workflow.json | n8n workflow - import into n8n UI |
| rbi_scraper_v2.py | Scraper for ingesting circulars |
| schema.sql | Supabase schema - run before scraper |
| frontend.html | Single-file frontend for Netlify |
| .env.example | Scraper environment variables |
| .env.n8n.example | n8n environment variables |
| .env.litellm.example | LiteLLM environment variables |

## Prerequisites — Accounts to Create First
1. Supabase — https://supabase.com (free tier)
2. Groq — https://console.groq.com (free tier)
3. Gemini — https://aistudio.google.com (free tier)
4. Langfuse — https://cloud.langfuse.com (free tier, optional but recommended)
5. Cloudflare — https://cloudflare.com (free tier, for tunnel)
6. Netlify — https://netlify.com (free tier, for frontend)

## Setup

### Step 1 — Supabase
1. Create a new Supabase project
2. Go to SQL Editor and run schema.sql (this creates all tables and the hybrid search function)
3. Go to Settings -> API Keys and note your service role key (sb_secret_... format)
4. Note your project URL (https://yourproject.supabase.co)

### Step 2 — LiteLLM on VM2
1. Provision a Ubuntu 22.04 VM (1GB RAM minimum)
2. Install Docker and Docker Compose
3. Clone this repo
4. Copy .env.litellm.example to .env and fill in all API keys
5. Run: docker compose up -d
6. Verify: curl http://localhost:4000/health

### Step 3 — n8n on VM1
1. Provision a second Ubuntu 22.04 VM (1GB RAM minimum)
2. Install Docker and Docker Compose
3. Copy .env.n8n.example to .env_rbi and fill in keys
4. Make sure LITELLM_MASTER_KEY matches exactly what you set on VM2
5. Make sure SUPABASE_SERVICE_KEY is your sb_secret_... key from Step 1
6. Run: docker compose up -d
7. Open n8n UI at http://YOUR_VM1_IP:5678
8. Go to Workflows -> Import from file -> upload workflow.json
9. Open the workflow and update these node URLs:
   - Embed Query: change YOUR_LITELLM_HOST to VM2 IP
   - Generate Answer: change YOUR_LITELLM_HOST to VM2 IP
   - Get Circular Stats, Hybrid Search, Get Recent Circulars: change YOUR_SUPABASE_URL to your project URL
10. Activate the workflow

### Step 4 — Cloudflare Tunnel (VM1)
1. Install cloudflared on VM1
2. Run: cloudflared tunnel login
3. Create tunnel: cloudflared tunnel create rbi-agent
4. Configure /etc/cloudflared/config.yml to point to http://localhost:5678
5. Point your domain DNS to the tunnel
6. Start tunnel: sudo systemctl enable --now cloudflared

### Step 5 — Scraper
1. On VM1, install dependencies:
   pip install playwright python-dotenv supabase groq google-generativeai
   playwright install chromium
2. Copy .env.example to .env and fill in keys
3. Run initial backfill:
   python3 rbi_scraper_v2.py backfill --since 2025-07-01
4. Set up daily cron (00:30 UTC):
   30 0 * * * cd /path/to/agent && python3 rbi_scraper_v2.py daily >> scraper.log 2>&1

### Step 6 — Frontend
1. Open frontend.html and update the API URL to your endpoint
2. Go to https://netlify.com and drag and drop the file to deploy
3. Your frontend is live instantly

## API Usage
curl -X POST https://your-endpoint/webhook/rbi-query \
  -H "Content-Type: application/json" \
  -d '{"query": "what are the KYC norms for opening a bank account?"}'

Response:
{"answer": "...", "sources": [{"title": "...", "url": "...", "date": "..."}]}

## Scraper Modes
- python3 rbi_scraper_v2.py daily — scrape today's new circulars
- python3 rbi_scraper_v2.py backfill --since YYYY-MM-DD — historical load
- python3 rbi_scraper_v2.py reembed — re-embed from stored full_text
- python3 rbi_scraper_v2.py test --url URL — test single circular
