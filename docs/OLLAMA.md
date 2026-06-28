# Optional: Local Ollama Setup

By default AgentOS uses Groq free tier for Llama 3.1 8B inference. Use this guide only if you want to run the model locally on your own hardware.

## When to Use Ollama Instead of Groq

- You have a GPU and want zero per token cost at high volume
- Your data cannot leave your own environment

## Latency Expectations

| Hardware | Expected latency |
|---|---|
| Laptop CPU (no GPU) | 7,000 to 24,000ms |
| Consumer GPU | 500 to 1,500ms |
| Groq hosted (for comparison) | 200 to 400ms |

CPU inference is slow and unstable. If latency matters, use Groq.

## Setup

Install Ollama on your machine:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
ollama serve
```

Then tunnel it to your VM using Cloudflare:

```bash
cloudflared tunnel --url http://localhost:11434
```

Copy the URL it gives you and set OLLAMA_URL in your .env file.

Then uncomment the llama-local section in stack/litellm-config.yaml and restart LiteLLM.
