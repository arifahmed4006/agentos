# Deployment Guide

## Two Ways to Run AgentOS

| | Local | Always-On VM |
|---|---|---|
| WhatsApp works | No | Yes |
| Cost | Zero | Zero (Oracle Free Tier) |
| Setup time | 10 minutes | 45-60 minutes |

## Why Local Does Not Work for WhatsApp

WhatsApp sends messages to your server as inbound webhooks. A laptop has no stable public address for this. Everything that calls outward works fine locally — LiteLLM calling Groq, writes to Supabase, traces to Langfuse. Only the inbound webhook needs an always-on server.

## Option A — Local Testing Only

```bash
git clone https://github.com/arifahmed4006/agentos.git
cd agentos/stack
cp .env.example .env
nano .env
docker compose up -d
```

Open n8n at http://localhost:5678 and import a workflow from the agents folder.

## Option B — Always-On VM Setup

### What You Need

- Oracle Cloud Free Tier account: oracle.com/cloud/free
- Groq account: console.groq.com (free, no card)
- Langfuse account: cloud.langfuse.com (free tier)
- Supabase account: supabase.com (free tier)
- Cloudflare account: cloudflare.com (free, for permanent HTTPS tunnel)
- A WhatsApp number to link

### Step 1 — Create Two VMs on Oracle Cloud

1. Log into cloud.oracle.com
2. Go to Compute > Instances > Create Instance
3. Create VM 1 — shape VM.Standard.E2.1.Micro, Ubuntu 22.04
4. Create VM 2 — same settings
5. Note both public IPs

### Step 2 — Bootstrap Both VMs

SSH into each VM and run:

```bash
git clone https://github.com/arifahmed4006/agentos.git
cd agentos
chmod +x scripts/sanitize-workflow.sh
```

Then on VM 1 (n8n):
```bash
./scripts/setup.sh vm1
```

Then on VM 2 (gateway):
```bash
./scripts/setup.sh vm2
```

Then open these ports in Oracle Cloud Console under Security Lists:
- VM 1: port 5678
- VM 2: ports 4000 and 8080

### Step 3 — Fill in Environment Variables

On both VMs:
```bash
cd agentos/stack
cp .env.example .env
nano .env
```

Fill in all values. Where to get each key:

| Variable | Where to get it |
|---|---|
| GROQ_API_KEY | console.groq.com > API Keys |
| ANTHROPIC_API_KEY | console.anthropic.com > API Keys |
| GEMINI_API_KEY | aistudio.google.com > Get API Key |
| LANGFUSE_PUBLIC_KEY | cloud.langfuse.com > Project > Settings > API Keys |
| LANGFUSE_SECRET_KEY | Same as above |
| LITELLM_MASTER_KEY | Generate: openssl rand -hex 32 |
| EVOLUTION_AUTH_TOKEN | Generate: openssl rand -hex 32 |
| POSTGRES_PASSWORD | Choose any password |

### Step 4 — Start Services

On VM 2 first:
```bash
cd agentos/stack
docker compose -f docker-compose.vm2.yml up -d
```

Then VM 1:
```bash
cd agentos/stack
docker compose -f docker-compose.vm1.yml up -d
```

### Step 5 — Test the Gateway

From VM 2:
```bash
curl -s -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "llama-groq", "messages": [{"role":"user","content":"reply ok only"}]}'
```

Should return a response with model showing groq/llama-3.1-8b-instant.

### Step 6 — Set Up Cloudflare Tunnel for WhatsApp

WhatsApp requires HTTPS. Set up a permanent named tunnel on VM 1:

```bash
curl -L https://pkg.cloudflare.com/cloudflared-stable-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
cloudflared tunnel login
cloudflared tunnel create agentos
cloudflared tunnel route dns agentos n8n.yourdomain.com
sudo cloudflared service install
sudo systemctl start cloudflared
```

### Step 7 — Link WhatsApp

On VM 2:
```bash
docker logs agentos-evolution -f
```

Scan the QR code from WhatsApp on your phone:
Settings > Linked Devices > Link a Device

### Step 8 — Import an Agent

1. Open n8n at https://n8n.yourdomain.com
2. Workflows > Import from File
3. Import agents/document-chaser/workflow.json
4. Update the LiteLLM URL in the HTTP Request node to your VM 2 IP
5. Activate the workflow

### Step 9 — Verify

Send a WhatsApp message to the linked number. Check:
1. n8n execution log shows the message
2. Langfuse shows a trace
3. Reply arrives on WhatsApp

## Troubleshooting

| Problem | Likely cause |
|---|---|
| Containers keep restarting | No swap — run setup.sh |
| No WhatsApp response | Port not open in Oracle Security List |
| LiteLLM auth error | Key not set or container not restarted |
| No Langfuse traces | Wrong LANGFUSE_HOST or keys swapped |
| n8n cannot reach LiteLLM | Wrong VM 2 IP in workflow |
