import asyncio
import os
import time
import httpx
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions, function_tool, RunContext
from livekit.plugins import deepgram, groq, silero, noise_cancellation
from livekit.plugins import sarvam
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv()

SYSTEM_PROMPT = """You are Priya, a knowledgeable RBI compliance assistant. You help bankers, finance professionals and businesses understand RBI circulars issued in the last 3 years.

Voice rules (critical):
- You are on a PHONE CALL. Replies must be 1-2 short sentences maximum. Never use lists, bullet points, numbers or emojis.
- Always look up the knowledge base before answering — never guess or invent RBI circular details.
- Mirror the caller's language instantly. Hindi reply in Hindi. English reply in English. Hinglish reply in Hinglish.
- Write Hindi words in Devanagari script so they are pronounced correctly.
- For complex regulatory answers, give the key point first, then offer to send details in writing.
- If the caller says "hello? hello?" immediately say: "Haan, main sun rahi hoon" or "Yes, I'm here, please go ahead."
- If you didn't catch something, say: "Sorry, could you repeat that?" or "Thoda repeat kar sakte hain?"
- Never invent circular numbers, dates or policy details. If unsure, say: "Main abhi check karti hoon" and use the lookup tool.
- If the lookup fails or returns nothing, say: "Mujhe is circular ki details abhi nahi mil rahi — main aapko callback arrange kar sakti hoon."
- When you find a circular, briefly explain what it SAYS in 2 sentences — not just its number and date. The caller wants the substance, not the reference.
""".format(date=__import__('datetime').date.today())

GREETING = "Namaste! Main Priya bol rahi hoon, RBI circular assistant. Aap koi bhi RBI circular se related sawaal pooch sakte hain — main help karungi."


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)

@function_tool()
async def lookup_knowledge(self, context: RunContext, question: str) -> str:
    """Look up RBI circular information to answer the caller's question.
    Use for any question about RBI circulars, policies, regulations, or guidelines."""

    supabase_url = "https://qiapockxvamsnpcylcvn.supabase.co"
    supabase_key = os.getenv("RAG_SUPABASE_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    if not supabase_key or not gemini_key:
        return "Knowledge base not connected. Apologise briefly and offer a callback."

    # Expand common RBI abbreviations (same as your n8n classify node)
    synonyms = {
        "ckyc": "CKYC Central KYC Registry centralised Know Your Customer",
        "kyc": "KYC Know Your Customer norms requirements compliance",
        "nbfc": "NBFC Non-Banking Financial Company guidelines directions",
        "npa": "NPA Non-Performing Asset classification provisioning",
        "lcr": "LCR Liquidity Coverage Ratio liquidity risk management",
        "upi": "UPI Unified Payments Interface payment system",
        "aml": "AML Anti-Money Laundering prevention detection",
        "msme": "MSME Micro Small Medium Enterprises lending priority sector",
        "psl": "PSL Priority Sector Lending targets",
        "ecb": "ECB External Commercial Borrowing foreign currency loan",
        "fema": "FEMA Foreign Exchange Management Act regulations",
        "lrs": "LRS Liberalised Remittance Scheme foreign exchange",
        "digital lending": "digital lending fintech NBFC LSP guidelines directions",
    }
    q_lower = question.lower()
    extras = [exp for abbr, exp in synonyms.items() if abbr in q_lower]
    expanded_query = question + " " + " ".join(extras) if extras else question

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:

            # Step 1: Embed using Gemini directly (~200ms)
            embed_resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-001:embedContent?key={gemini_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "model": "models/text-embedding-001",
                    "content": {"parts": [{"text": expanded_query}]},
                    "outputDimensionality": 1536
                }
            )
            embed_resp.raise_for_status()
            embedding = embed_resp.json()["embedding"]["values"]

            # Step 2: Hybrid search on Supabase (~200ms)
            search_resp = await client.post(
                f"{supabase_url}/rest/v1/rpc/hybrid_search_rbi",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "query_embedding": embedding,
                    "query_text": expanded_query,
                    "match_threshold": 0.25,
                    "match_count": 3
                }
            )
            search_resp.raise_for_status()
            results = search_resp.json()

            if not results:
                return "No matching RBI circulars found for this query."

            # Format results concisely for the LLM
            snippets = []
            for r in results[:3]:
                num = r.get("circular_number", "")
                date = r.get("published_date", "")[:10]
                title = r.get("title", "")
                content = r.get("content", r.get("summary", ""))[:400]
                snippets.append(f"{num} ({date}) — {title}: {content}")

            return " || ".join(snippets)

    except Exception as e:
        print(f"RAG lookup failed: {e}")
        return "Lookup failed. Apologise briefly and offer a callback."

    
async def send_to_n8n(session: AgentSession, room_name: str, started_at: float):
    webhook = os.getenv("N8N_POSTCALL_WEBHOOK", "")
    if not webhook:
        return
    try:
        payload = {
            "room": room_name,
            "duration_seconds": round(time.time() - started_at),
            "transcript": session.history.to_dict(),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(webhook, json=payload)
    except Exception as e:
        print(f"n8n webhook failed: {e}")


async def entrypoint(ctx: agents.JobContext):
    started_at = time.time()

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=groq.LLM(model="llama-3.1-8b-instant", temperature=0.3),
        tts=sarvam.TTS(target_language_code="hi-IN", speaker="kavya"),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
        allow_interruptions=True,
        min_interruption_duration=0.4,
        min_endpointing_delay=0.4,
        max_endpointing_delay=3.0,
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await session.say(GREETING, allow_interruptions=True)

    async def on_shutdown():
        await send_to_n8n(session, ctx.room.name, started_at)
    ctx.add_shutdown_callback(on_shutdown)


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))