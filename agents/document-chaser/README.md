# Document Chaser Agent

Reads a CRM for documents pending from each customer, follows up on WhatsApp automatically, validates submissions against a checklist, and updates the CRM. Chases only what is still missing.

## What the LLM Does

Only three steps — everything else is deterministic workflow:
- Interprets the customer message
- Matches the submission to a checklist item
- Drafts a friendly reply

Default model: Llama 3.1 8B via Groq (249ms, free tier)

## Performance

| Model | Latency | Cost per 1,000 conversations |
|---|---|---|
| Llama 3.1 8B via Groq | 249ms | $0.011 |
| Claude Haiku 4.5 | 1,261ms | $0.44 |
| Gemini 2.5 Flash | 1,723ms | $0.27 |

All three models passed the same eval suite. This task does not need a frontier model.

## How to Use

1. Open n8n on your VM
2. Go to Workflows > Import from File
3. Select workflow.json from this folder
4. Update the LiteLLM URL in the HTTP Request node to http://92.4.73.211:4000
5. Activate the workflow

## Required Variables in .env

- LITELLM_MASTER_KEY
- GROQ_API_KEY
- SUPABASE_URL and SUPABASE_ANON_KEY
- EVOLUTION_AUTH_TOKEN
