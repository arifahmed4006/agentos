# Grocery Price Agent

Send a grocery list on WhatsApp. Llama 3.1 8B parses the items. Parallel price checks run across Blinkit, Zepto and Instamart. Cheapest option per item is returned as a formatted WhatsApp report.

## What the LLM Does

One step only — parsing a natural language grocery list into structured items. Everything else is deterministic workflow.

## Note on Scrapers

The scraper nodes in the workflow point at placeholder URLs. You need to replace these with your own scraping service endpoints for Blinkit, Zepto and Instamart.

## How to Use

1. Open n8n on your VM
2. Go to Workflows > Import from File
3. Select workflow.json from this folder
4. Replace the three scraper placeholder URLs with your actual endpoints
5. Update the LiteLLM URL to http://92.4.73.211:4000
6. Activate the workflow

## Required Variables in .env

- LITELLM_MASTER_KEY
- GROQ_API_KEY
- EVOLUTION_AUTH_TOKEN
