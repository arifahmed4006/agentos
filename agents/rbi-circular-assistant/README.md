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

## Knowledge Base
- 273 RBI circulars (July 2025 to July 2026)
- 1,038 chunks with identity anchors
- Hybrid search: vector 0.7 weight + BM25 0.3 weight
- Daily scraper at 00:30 UTC

## Query Types
- RAG: compliance questions with citations
- Recency: latest circulars, this month, last week
- Meta: how many circulars do you have
- Out-of-scope: non-RBI queries rejected

## Files
| File | Purpose |
|------|---------|
| workflow.json | n8n workflow - import into n8n UI |
| rbi_scraper_v2.py | Scraper for ingesting circulars |
| frontend.html | Single-file frontend for Netlify |
| .env.example | Scraper environment variables |
| .env.n8n.example | n8n environment variables |
| .env.litellm.example | LiteLLM environment variables |

## Setup

### 1. Infrastructure
- VM1: n8n + Cloudflare tunnel (1GB RAM, Ubuntu 22.04)
- VM2: LiteLLM + Redis (1GB RAM, Ubuntu 22.04)
- Supabase: free tier with pgvector extension

### 2. LiteLLM on VM2
cp .env.litellm.example .env
Fill in API keys then run: docker compose up -d

### 3. n8n on VM1
cp .env.n8n.example .env_rbi
Fill in keys then run: docker compose up -d
Import workflow.json into n8n UI and activate.

### 4. Scraper
pip install playwright python-dotenv supabase
playwright install chromium
cp .env.example .env
Fill in keys then run: python3 rbi_scraper_v2.py backfill --since 2025-07-01
Daily cron: 30 0 * * * python3 /path/to/rbi_scraper_v2.py daily

### 5. Frontend
Deploy frontend.html on Netlify via drag and drop.
Update the API URL inside the file if using a different endpoint.

## API Usage
curl -X POST https://rbi-api.paperlight.in/webhook/rbi-query \
  -H "Content-Type: application/json" \
  -d '{"query": "what are the KYC norms for opening a bank account?"}'

Response format:
{"answer": "...", "sources": [{"title": "...", "url": "...", "date": "..."}]}
