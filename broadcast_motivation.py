"""
Broadcast Script — sends a language-aware randomized motivation from Al-Ghazali
to SUBSCRIBED users when it hits 08:00 AM in their specific timezone.
"""

import os
import random
import asyncio
import datetime
import httpx
from dotenv import load_dotenv

# Load core modules
import core.config as config
import core.vector_store as vector_store
import core.llm_client as llm_client
from personas.ghazali.system_prompt import build_system_prompt

load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TENANT_ID = "ghazali"
DEATH_DATE_AH = "505"

# Multi-lingual queries
QUERIES = {
    "EN": [
        "Give me a profound motivation for improving my connection with Allah based on your works.",
        "Give me a motivation for improving my manners and relationships with other humans.",
        "Give me a motivation for caring for the environment and Allah's creation."
    ],
    "ID": [
        "Berikan motivasi mendalam untuk memperbaiki hubungan dengan Allah (Hablu Minallah) berdasarkan karya-karyamu.",
        "Berikan motivasi untuk memperbaiki adab dan hubungan dengan sesama manusia (Hablu Minannas).",
        "Berikan motivasi untuk menjaga lingkungan dan alam ciptaan Allah."
    ]
}

async def send_telegram_message(chat_id, text):
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload)
            return resp.status_code == 200
        except Exception:
            return False

def escape_md(t):
    for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        t = t.replace(char, f'\\{char}')
    return t

async def run_broadcast_for_hour(current_hour_utc: int):
    """Run broadcast only for users where it is 08:00 AM local time."""
    if not TELEGRAM_BOT_TOKEN: return

    vector_store.initialize()
    
    # 1. Get users whose local time is currently 08:00 AM
    users = vector_store.get_subscribed_users_for_hour(TENANT_ID, current_hour_utc)
    if not users:
        print(f"⏰ Hour {current_hour_utc} UTC: No users are at 08:00 AM right now. Skipping.")
        return
    
    print(f"📊 Hour {current_hour_utc} UTC: Found {len(users)} users at 08:00 AM local time.")

    # 2. Group by language to save LLM tokens (generate once per language)
    by_lang = {"EN": [], "ID": []}
    for u in users:
        by_lang[u["lang"]].append(u["chat_id"])

    system_prompt = build_system_prompt()

    for lang, chat_ids in by_lang.items():
        if not chat_ids: continue
        
        print(f"📝 Generating {lang} motivation for {len(chat_ids)} users...")
        query_text = random.choice(QUERIES[lang])
        
        chunks = vector_store.query_multilayer(TENANT_ID, query_text, DEATH_DATE_AH)
        result = llm_client.generate_answer(query_text, chunks, system_prompt, intent="motivation_blast")
        
        if not result.get("can_answer"): continue

        header = "✨ *Daily Wisdom*" if lang == "EN" else "✨ *Hikmah Harian*"
        msg = f"{header} from Imam Al\\-Ghazali\n\n"
        msg += f"{escape_md(result.get('answer_text', ''))}\n\n"
        msg += f"_{escape_md(result.get('closing', ''))}_"

        # 3. Send to all users in this language group
        for chat_id in chat_ids:
            await send_telegram_message(chat_id, msg)
            await asyncio.sleep(0.05)

if __name__ == "__main__":
    now_utc = datetime.datetime.now(datetime.timezone.utc).hour
    asyncio.run(run_broadcast_for_hour(now_utc))
