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
5. Update the LiteLLM URL to http://YOUR_WHATSAPP_VM_IP:4000
6. Activate the workflow

## Required Variables in .env

- LITELLM_MASTER_KEY
- GROQ_API_KEY
- EVOLUTION_AUTH_TOKEN

## Required Credentials and Tokens

- LITELLM_MASTER_KEY — your LiteLLM gateway key
- GROQ_API_KEY — from console.groq.com
- EVOLUTION_AUTH_TOKEN — your Evolution API key
- Apify API Token — from console.apify.com, needed for the Blinkit and Zepto scrapers
  - Sign up at console.apify.com
  - Go to Settings > API tokens > Create new token
  - Replace YOUR_APIFY_API_TOKEN in the workflow URLs with your actual token

## Scraper Actors Used

- Blinkit: shahidirfan~blinkit-price-scraper
- Zepto: shahidirfan~zepto-product-scraper

These are third party Apify actors. Check their current status and pricing on apify.com before use.
