# AgentOS

A 9-layer stack for building and running production-grade AI agents on free-tier infrastructure. Includes LLM gateway with fallback routing, cost controls, observability and eval gates — the layers that separate a demo from a real system.

---

## The Stack

| Layer | What | Purpose |
|---|---|---|
| Compute | Oracle Cloud Always-Free VMs | Always-on, zero cost |
| Models | Groq Llama 3.1 8B (default) | Free tier, ~250ms, no GPU needed |
| LLM Gateway | LiteLLM | Fallback routing, budget cap, guardrails |
| Orchestration | n8n | Visual workflows, 400+ integrations |
| Cache | Redis | Session management |
| Memory | PostgreSQL + Supabase | Operational data + RAG |
| Observability | Langfuse | Every LLM call traced |
| Evaluation | Promptfoo | Pass/fail before anything ships |
| Channels | Evolution API + n8n | WhatsApp + web chat |

---

## Agents

### Document Chaser
Reads CRM for pending documents, follows up on WhatsApp automatically, validates submissions, updates CRM.
See [agents/document-chaser](agents/document-chaser)

### Grocery Price Agent
Send a grocery list on WhatsApp, get back the cheapest option per item across Blinkit, Zepto and Instamart.
See [agents/grocery-price-agent](agents/grocery-price-agent)

### RBI Circular Intelligence Agent
RAG-based compliance agent that ingests RBI circulars and answers queries in plain English. 273 circulars (July 2025–July 2026), updated daily by a Playwright scraper. Hybrid vector + BM25 search via Supabase pgvector. Handles compliance questions, recency queries, and out-of-scope rejection cleanly. Live at https://strong-dieffenbachia-bdb5ac.netlify.app
See [agents/rbi-circular-assistant](agents/rbi-circular-assistant)

### RBI Circular Voice Agent
Converts the RBI Circular Intelligence Agent into a real-time voice interface. Ask any question about RBI circulars by voice — in Hindi, English, or Hinglish — and get a spoken answer in under 1.5 seconds. Built on LiveKit with Deepgram multilingual STT, Groq LLM, and Sarvam Hindi TTS. Handles language switching, noise cancellation, barge-in, and direct RAG lookup bypassing n8n for sub-500ms retrieval.
See [agents/rbi-voice-agent](agents/rbi-voice-agent)

---

## Utilities

### Error Handler
Catches errors from any workflow and sends a WhatsApp alert to the admin. Set this as the Error Workflow in any agent to get instant WhatsApp notifications when something fails.
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

## Why Groq Instead of Ollama

Groq hosts Llama 3.1 8B on GPU infrastructure for free. No laptop running 24/7, no tunnel, no cold starts. Faster than both Claude Haiku and Gemini Flash at a fraction of the cost.

See [docs/OLLAMA.md](docs/OLLAMA.md) if you want to run locally instead.

---

## License

MIT