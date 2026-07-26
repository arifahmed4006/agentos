# RBI Circular Voice Agent

A real-time voice agent that answers questions about RBI circulars (last 3 years) in Hindi, English, or Hinglish. Built on the AgentOS stack.

Callers speak naturally — the agent transcribes, looks up the relevant circular from the Supabase knowledge base, and speaks back an answer in under 1.5 seconds.

---

## How It Works

```
Caller speaks
    │
    ▼
Deepgram Nova-3 STT (Hindi + English in one stream, ~200ms)
    │
    ▼
Silero VAD + Multilingual Turn Detector (knows when you've finished speaking)
    │
    ▼
Groq LLM (llama-3.1-8b-instant, ~200ms first token)
    │  └── if data needed:
    │       Gemini embedding (~200ms) → Supabase hybrid_search_rbi (~200ms)
    ▼
Sarvam Bulbul TTS — kavya voice (~400ms first audio)
    │
    ▼
Caller hears the answer
Total: ~1–1.5 seconds
```

---

## Stack

| Layer | Tool | Why |
|---|---|---|
| Voice orchestration | LiveKit Agents | Open source, Mumbai edge, built-in barge-in and noise cancellation |
| Speech-to-text | Deepgram Nova-3 (`language=multi`) | Single stream for Hindi + English code-switching |
| Turn detection | Silero VAD + Multilingual Model | Tells a mid-thought pause from a finished sentence |
| LLM | Groq `llama-3.1-8b-instant` | ~200ms first token, free tier |
| Text-to-speech | Sarvam Bulbul v3, kavya voice | Natural Indian Hindi/Hinglish pronunciation |
| RAG — embedding | Google Gemini `gemini-embedding-001` at 1536 dimensions | Same model used during ingestion |
| RAG — search | Supabase `hybrid_search_rbi` RPC | Vector + full-text hybrid, direct API call |
| Noise cancellation | LiveKit Krisp BVC | Handles traffic, fans, background noise |

---

## Edge Cases Handled

| Situation | What happens |
|---|---|
| Caller switches Hindi ↔ English mid-sentence | Deepgram Nova-3 `multi` handles it in one stream |
| Caller says "hello? hello?" | Agent immediately reassures: "हाँ, मैं सुन रही हूँ" |
| Caller pauses mid-thought | Turn detector waits — does not interrupt |
| Caller interrupts agent | Barge-in stops TTS within ~200ms |
| Background noise | Krisp noise cancellation active on every call |
| RAG lookup fails or times out | Agent apologises and offers a callback — never freezes |
| Groq free tier rate limit hit | Switch to `llama-3.1-8b-instant` (lower token usage than 70B) |

---

## Prerequisites

Before starting, you need accounts and API keys from these services. All have free tiers sufficient for development and testing.

| Service | What for | Free tier |
|---|---|---|
| LiveKit Cloud | Voice orchestration, WebRTC | Generous free minutes |
| Deepgram | Speech-to-text | $200 free credit (~46,000 mins) |
| Groq | LLM inference | Free tier with rate limits |
| Sarvam AI | Hindi/Hinglish TTS | Free credits on signup |
| Google AI Studio | Gemini embeddings for RAG | 1,500 requests/day free |
| Supabase | Vector database (already set up in AgentOS) | Already running |

---

## Step 1 — Create API Keys

### 1.1 LiveKit
1. Go to **cloud.livekit.io** → Sign up (use Google/GitHub login)
2. Create a project → choose region **Asia Pacific (Singapore)** for lowest India latency
3. Left sidebar → **Settings → Keys** → note down:
   - `LIVEKIT_URL` (starts with `wss://`)
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`

### 1.2 Deepgram
1. Go to **console.deepgram.com** → Sign up
2. Left sidebar → **API Keys** → **Create a New API Key** → name it `voice-agent`
3. Copy the key — shown only once
   - `DEEPGRAM_API_KEY`

### 1.3 Groq
1. Go to **console.groq.com** → Sign up
2. Left sidebar → **API Keys** → **Create API Key** → name it `voice-agent`
3. Copy the key
   - `GROQ_API_KEY`

### 1.4 Sarvam AI
1. Go to **dashboard.sarvam.ai** → Sign up
2. Go to API Keys → Create → copy the key
   - `SARVAM_API_KEY`

### 1.5 Google AI Studio (Gemini)
1. Go to **aistudio.google.com** → Sign in with Google account
2. Left sidebar → **API Keys** → **Create API Key**
3. Copy the key
   - `GEMINI_API_KEY`

### 1.6 Supabase
Your Supabase project is already running as part of AgentOS. You need:
- `RAG_SUPABASE_KEY` — the service role key from Supabase dashboard → Settings → API → `service_role` key

---

## Step 2 — Set Up Your Machine

These instructions are for **Windows**. Mac/Linux notes in brackets.

### 2.1 Install Python 3.11+
1. Go to **python.org/downloads** → Download Python 3.12
2. Run installer — on the **first screen**, tick **"Add python.exe to PATH"** before clicking Install
3. Verify:
```
python --version
```
You should see `Python 3.12.x`

*(Mac: `brew install python@3.12` or use the python.org installer)*

### 2.2 Install Git
1. Go to **git-scm.com** → Download → Run installer with all defaults
2. Verify:
```
git --version
```

### 2.3 Clone the repo
```
cd "%USERPROFILE%\OneDrive\Desktop"
git clone https://github.com/arifahmed4006/agentos.git
cd agentos\agents\rbi-voice-agent
```

*(Mac/Linux: `cd ~/Desktop && git clone ... && cd agentos/agents/rbi-voice-agent`)*

### 2.4 Create a virtual environment
```
python -m venv venv
venv\Scripts\activate
```

*(Mac/Linux: `source venv/bin/activate`)*

Your prompt should now start with `(venv)`.

**If you see "running scripts is disabled" on Windows**, run this first then retry:
```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 2.5 Install dependencies
```
pip install "livekit-agents[deepgram,groq,silero,turn-detector,noise-cancellation]~=1.0" livekit-plugins-sarvam "livekit-plugins-noise-cancellation==0.3.0" python-dotenv httpx
```

This takes 3–5 minutes. Yellow warnings are fine. Only red `ERROR` lines matter.

---

## Step 3 — Configure Your Keys

### 3.1 Create the .env file

The easiest way on Windows (avoids encoding issues with Notepad):

```
python -c "open('.env','w',encoding='utf-8').write('')"
notepad .env
```

Paste this block and fill in all your real keys:

```
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
DEEPGRAM_API_KEY=your_deepgram_key
GROQ_API_KEY=your_groq_key
SARVAM_API_KEY=your_sarvam_key
GEMINI_API_KEY=your_gemini_key
RAG_SUPABASE_URL=https://your-project-id.supabase.co
RAG_SUPABASE_KEY=your_supabase_service_role_key
N8N_POSTCALL_WEBHOOK=
```

Save: File → Save As → **Encoding: UTF-8** → save as `.env` with **Save as type: All Files**.

### 3.2 Verify keys loaded correctly
```
python -c "from dotenv import load_dotenv; load_dotenv(); import os; [print(k,'=','SET' if os.getenv(k) else 'MISSING') for k in ['LIVEKIT_URL','DEEPGRAM_API_KEY','GROQ_API_KEY','SARVAM_API_KEY','GEMINI_API_KEY','RAG_SUPABASE_URL','RAG_SUPABASE_KEY']]"
```

All six should say `SET`. If any say `MISSING`, the `.env` file has an encoding or naming issue.

### 3.3 Test RAG connection
```
python -c "
from dotenv import load_dotenv; load_dotenv()
import os, httpx

key = os.getenv('GEMINI_API_KEY')
supa_key = os.getenv('RAG_SUPABASE_KEY')
supa_url = os.getenv('RAG_SUPABASE_URL')

r1 = httpx.post(
    f'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={key}',
    headers={'Content-Type': 'application/json'},
    json={'model': 'models/gemini-embedding-001', 'content': {'parts': [{'text': 'CKYC circular'}]}, 'outputDimensionality': 1536},
    timeout=10
)
embedding = r1.json()['embedding']['values']
print('Embedding OK, length:', len(embedding))

r2 = httpx.post(
    f'{supa_url}/rest/v1/rpc/hybrid_search_rbi',
    headers={'apikey': supa_key, 'Authorization': f'Bearer {supa_key}', 'Content-Type': 'application/json'},
    json={'query_embedding': embedding, 'query_text': 'CKYC circular', 'match_threshold': 0.25, 'match_count': 2},
    timeout=10
)
print('Search status:', r2.status_code)
results = r2.json()
if results:
    print('RAG working — found', len(results), 'results')
    print('First result:', results[0].get('title','')[:80])
else:
    print('No results found')
"
```

You should see `RAG working — found X results`.

---

## Step 4 — Download the Turn Detection Model

This is a one-time download of a small local model that runs on your machine (~25ms, free):

```
python agent.py download-files
```

Wait for it to complete and return to the `(venv)` prompt.

---

## Step 5 — Run the Agent

```
python agent.py dev
```

Leave this window open. Within 30 seconds you should see:
```
registered worker ... url: wss://your-project.livekit.cloud ... region: India West
```

This means the agent is live and connected to LiveKit.

---

## Step 6 — Test in Browser

1. Open Chrome and go to your LiveKit Cloud dashboard: **cloud.livekit.io**
2. Left sidebar → **Agents** → click your agent → **Test in Console** (top right)
3. In the Console page → click **Start a session**
4. Allow microphone access when Chrome asks
5. Speak: *"Namaste"* or *"CKYC ke baare mein latest circular kya hai?"*

### What to test
| Test | Expected behaviour |
|---|---|
| Say "Namaste" | Agent greets in Hinglish within 1-2 seconds |
| Ask in Hindi: "CKYC circular क्या है?" | Agent looks up and explains in Hindi |
| Ask in English: "What are the latest KYC norms?" | Agent replies in English |
| Mix: "Mera sawaal hai about NPA provisioning" | Agent replies in natural Hinglish |
| Say "hello? hello?" | Agent immediately says "हाँ, मैं सुन रही हूँ" |
| Interrupt the agent mid-sentence | Agent stops within ~200ms and listens |
| Pause mid-thought | Agent waits — does not jump in |

---

## Step 7 — Deploy to a VM (Always-On)

When you're ready to run 24/7, SSH into any Ubuntu 22.04 VM and run:

```bash
# Clone the repo
git clone https://github.com/arifahmed4006/agentos.git
cd agentos/agents/rbi-voice-agent

# Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install "livekit-agents[deepgram,groq,silero,turn-detector,noise-cancellation]~=1.0" livekit-plugins-sarvam "livekit-plugins-noise-cancellation==0.3.0" python-dotenv httpx

# Download turn detection model
python agent.py download-files

# Create and fill in your keys
cp .env.example .env
nano .env   # fill in all keys, save with Ctrl+X

# Test it runs
python agent.py start
```

To keep it running 24/7 with systemd:

```bash
sudo nano /etc/systemd/system/rbi-voice-agent.service
```

Paste this (replace `/home/ubuntu` with your actual home directory):

```
[Unit]
Description=RBI Voice Agent
After=network.target

[Service]
WorkingDirectory=/home/ubuntu/agentos/agents/rbi-voice-agent
ExecStart=/home/ubuntu/agentos/agents/rbi-voice-agent/venv/bin/python agent.py start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rbi-voice-agent
sudo systemctl status rbi-voice-agent
```

Check logs anytime:
```bash
journalctl -u rbi-voice-agent -f
```

---

## Customising the Agent

Open `agent.py` — the only things you ever need to edit are at the top:

```python
SYSTEM_PROMPT = """You are Priya..."""   # Change name, rules, tone
GREETING = "Namaste! Main Priya..."      # Change the opening line
```

Everything else — STT, LLM, TTS, RAG — is wired and working. Prompt changes take effect on the next `python agent.py dev` restart.

**Common prompt tweaks:**
- Change agent name: replace `Priya` with your preferred name
- Change language default: add "Always reply in English unless the caller speaks Hindi"
- Restrict scope: add "Only answer questions about RBI circulars from 2023 onwards"

---

## Latency Budget

| Stage | Target | Notes |
|---|---|---|
| Turn detection (caller stops → agent starts processing) | 400–800ms | Tunable via `min_endpointing_delay` |
| Deepgram STT | ~200ms | Streaming — overlaps with turn detection |
| Groq LLM first token | ~200ms | Use `llama-3.1-8b-instant` not 70B |
| Gemini embedding (if RAG needed) | ~200ms | Runs in parallel with filler line |
| Supabase search (if RAG needed) | ~200ms | Direct RPC, no n8n hop |
| Sarvam TTS first audio | ~400ms | Starts on first sentence, not full reply |
| **Total caller experience** | **~1–1.5s** | |

**Note:** RAG adds ~400ms but is covered by the spoken filler line ("एक second, main check करती हूँ") so the caller never hears silence.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python not recognized` | Reinstall Python with "Add to PATH" ticked; reopen terminal |
| `(venv)` not showing | Run `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac/Linux) |
| `.env` keys show as MISSING | File saved as `.env.txt` — rename to `.env`; or encoding is wrong — resave as UTF-8 |
| Agent starts but no audio | Check `SARVAM_API_KEY` is set; check LiveKit Console for errors |
| Agent hears you but doesn't respond | Check `GROQ_API_KEY`; check for 429 rate limit errors in the terminal |
| RAG returns wrong results | Check `GEMINI_API_KEY` and `RAG_SUPABASE_KEY`; run the Step 3.3 test |
| Agent cuts off mid-sentence | Raise `min_endpointing_delay` to `0.8` in `agent.py` |
| Agent too slow to reply | Confirm model is `llama-3.1-8b-instant` not 70B; shorten `SYSTEM_PROMPT` |
| Hindi sounds robotic/accent changes | Confirm Sarvam speaker is `kavya`; ensure Hindi in `SYSTEM_PROMPT` is written in Devanagari |
| 429 rate limit from Groq | You've hit the free daily token limit; wait until midnight UTC or use a separate Groq key |

---

## How This Relates to the RBI RAG Agent

The RBI Circular RAG agent (in n8n) does: classify query → expand synonyms → embed → hybrid search → LLM answer → return JSON.

This voice agent does the same thing but:
- Takes speech input instead of text
- Calls Gemini and Supabase directly (bypassing n8n to eliminate the 10s latency)
- Returns spoken audio instead of JSON
- Handles real-world voice conditions (noise, interruptions, language switching)

The n8n workflow is still used for post-call automation — transcript logging, Langfuse observability, CRM updates — triggered by a webhook when the call ends.

---

## What's Next

- [ ] Wire `N8N_POSTCALL_WEBHOOK` to log transcripts to Langfuse and your CRM
- [ ] Add phone number via SIP trunk (Plivo or Exotel) for real inbound calls
- [ ] Add outbound calling for proactive circular alerts
- [ ] Warm handoff to human agent when the caller is frustrated
- [ ] Nightly eval gates on call transcripts (hallucination checks, language mirroring score)