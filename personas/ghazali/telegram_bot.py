"""
Telegram Bot — handles user interactions via Telegram.
Acts as a frontend client for the Core API SaaS.
"""

import asyncio
import os
import json
import logging
import aiohttp
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure local directory is in path for relative imports
sys.path.append(str(Path(__file__).parent))

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode, ChatAction

from system_prompt import get_persona_info, build_system_prompt

logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4096

# Base configuration for the Persona Client
TENANT_ID = os.getenv("TENANT_ID", "ghazali")
DEATH_DATE_AH = os.getenv("DEATH_DATE_AH", "505")

# Safely compute API_BASE_URL to handle dynamic ports from cloud providers (e.g. Railway)
raw_api_url = os.getenv("API_BASE_URL", f"http://127.0.0.1:{os.getenv('PORT', '8000')}/api/v1")
if "${PORT}" in raw_api_url or "${{PORT}}" in raw_api_url:
    # If the user literally copy-pasted the string with the variable syntax, fix it for them
    raw_api_url = f"http://127.0.0.1:{os.getenv('PORT', '8000')}/api/v1"

API_BASE_URL = raw_api_url
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Helpers ──────────────────────────────────────────────

def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#',
               '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special:
        text = text.replace(char, f'\\{char}')
    return text


def _detect_language(text: str) -> str:
    """
    Detect whether the user's message is in Indonesian, Malay, or English.
    Returns one of: 'Indonesian', 'Malay', 'Arabic', 'English'.
    Uses vocabulary heuristics — no external libraries needed.
    """
    t = text.lower()

    # Common Indonesian markers (words not found or rare in Malay)
    id_markers = [
        'apa', 'bagaimana', 'kenapa', 'mengapa', 'jelaskan', 'ceritakan',
        'tolong', 'saya', 'adalah', 'dengan', 'tidak', 'sudah', 'bisa',
        'dalam', 'untuk', 'yang', 'itu', 'ini', 'juga', 'seperti',
        'menurut', 'tentang', 'apakah', 'bagaimana', 'bahwa',
    ]
    # Common Malay markers (words not found or rare in Indonesian)
    my_markers = [
        'apa', 'bagaimana', 'kenapa', 'mengapa', 'jelaskan', 'ceritakan',
        'tolong', 'saya', 'ialah', 'dengan', 'tidak', 'sudah', 'boleh',
        'dalam', 'untuk', 'yang', 'itu', 'ini', 'juga', 'seperti',
        'menurut', 'tentang', 'adakah', 'bagaimanakah', 'bahawa',
    ]
    # Arabic markers
    arabic_markers = ['ما', 'كيف', 'لماذا', 'من', 'هل', 'اشرح']

    id_score = sum(1 for w in id_markers if w in t.split())
    my_score = sum(1 for w in my_markers if w in t.split())
    ar_score = sum(1 for w in arabic_markers if w in t)

    # Malay-specific differentiators
    if any(w in t for w in ['bahawa', 'adakah', 'bagaimanakah', 'boleh', 'ialah']):
        my_score += 3
    # Indonesian-specific differentiators  
    if any(w in t for w in ['bahwa', 'apakah', 'bisa', 'adalah', 'kenapa']):
        id_score += 3

    if ar_score >= 2:
        return 'Arabic'
    if id_score == 0 and my_score == 0:
        return 'English'
    if my_score > id_score:
        return 'Malay'
    if id_score > 0:
        return 'Indonesian'
    return 'English'


def _add_language_instruction(prompt: str, language: str) -> str:
    """Append a language override rule to the end of the system prompt."""
    if language == 'English':
        return prompt  # default — no injection needed
    lang_instruction = (
        f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"LANGUAGE OVERRIDE — HIGHEST PRIORITY\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"The user has written in {language}. You MUST write your "
        f"answer_text and closing entirely in {language}. "
        f"Book titles and Arabic terms may remain in their original script. "
        f"Do NOT switch to English in your response."
    )
    return prompt + lang_instruction

def _format_response(result: dict) -> str:
    """Format the compact API JSON response into a Telegram message."""
    parts = []

    answer = result.get("answer_text", "")
    if answer:
        parts.append(_escape_md(answer))

    citations = result.get("citations", [])
    if citations:
        parts.append(f"\n📖 *Sources:*")
        for i, c in enumerate(citations, 1):
            book = _escape_md(c.get("book", "Unknown"))
            page = _escape_md(str(c.get("page_number", "")))
            line = f"\\[{i}\\] *{book}*"
            if page:
                line += f", {page}"
            parts.append(line)

    closing = result.get("closing", "")
    if closing:
        parts.append(f"\n_{_escape_md(closing)}_")

    return "\n".join(parts)

async def _send_long(update: Update, text: str):
    """Send a message, splitting if it exceeds Telegram's limit."""
    if len(text) <= TELEGRAM_MAX_LENGTH:
        try:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            await update.message.reply_text(text)
        return

    sections = text.split("\n\n")
    current = ""
    for section in sections:
        candidate = (current + "\n\n" + section).strip() if current else section
        if len(candidate) <= TELEGRAM_MAX_LENGTH:
            current = candidate
        else:
            if current:
                try:
                    await update.message.reply_text(current, parse_mode=ParseMode.MARKDOWN_V2)
                except Exception:
                    await update.message.reply_text(current)
            current = section
    if current:
        try:
            await update.message.reply_text(current, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            await update.message.reply_text(current)


# ── Commands ─────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_persona_info()
    name = info.get("name_display", info.get("name", "Historical Figure"))
    greeting = info.get("greeting", "Greetings.")
    disclaimer = info.get("disclaimer", "")

    msg = f"🎭 *{_escape_md(name)}*\n\n"
    msg += f"_{_escape_md(greeting)}_\n\n"
    msg += f"*Commands:*\n"
    msg += f"/help — How to use this bot\n"
    msg += f"/about — About this persona\n"
    msg += f"/sources — View loaded source texts\n"
    if disclaimer:
        msg += f"\n⚠️ _{_escape_md(disclaimer)}_"

    try:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        await update.message.reply_text(msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 *How to use this bot*\n\n"
        "Simply type your question, and I will search my documented works "
        "to provide a cited answer in the persona's own voice\\.\n\n"
        "⚠️ This is an AI reconstruction for research purposes only\\."
    )
    try:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        await update.message.reply_text(msg)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = get_persona_info()
    name = info.get("name_display", "Unknown")
    era = info.get("era", "")
    field = info.get("field", "")
    bio = info.get("bio_summary", "")
    works = info.get("major_works", [])

    msg = f"🎭 *{_escape_md(name)}*\n"
    if era:
        msg += f"📅 {_escape_md(era)}\n"
    if field:
        msg += f"📚 {_escape_md(field)}\n"
    if bio:
        msg += f"\n{_escape_md(bio)}\n"
    if works:
        msg += f"\n*Major Works:*\n"
        for w in works:
            msg += f"  • {_escape_md(w)}\n"

    try:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        await update.message.reply_text(msg)

async def sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_BASE_URL}/{TENANT_ID}/sources") as resp:
                if resp.status == 200:
                    stats = await resp.json()
                    if stats.get("total_chunks", 0) > 0:
                        books_list = "\n".join(f"  • {_escape_md(b)}" for b in stats["books"])
                        msg = f"📚 *Loaded Sources* \\({stats['total_chunks']} chunks\\)\n\n{books_list}"
                    else:
                        msg = "📚 No sources loaded yet\\."
                else:
                    msg = "📚 Failed to fetch sources from the Core Engine\\."
        except Exception as e:
            msg = f"📚 API connection error: {_escape_md(str(e))}"

    try:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        await update.message.reply_text(msg)


# ── Message Handler ──────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        return

    # User ID acts as the session_id to maintain memory via the SaaS
    telegram_user_id = str(update.effective_user.id)
    
    await update.message.chat.send_action(ChatAction.TYPING)

    # 1. Build persona properties locally to send to SaaS
    try:
        prompt = build_system_prompt()
    except Exception as e:
        logger.error(f"Failed to build prompt: {e}")
        await update.message.reply_text("❌ Error loading persona memory.")
        return

    # Detect user language and inject an override instruction into the prompt
    detected_lang = _detect_language(query)
    if detected_lang != 'English':
        logger.info(f"Language detected: {detected_lang}")
    prompt_with_lang = _add_language_instruction(prompt, detected_lang)

    payload = {
        "query": query,
        "system_prompt": prompt_with_lang,
        "death_date_ah": DEATH_DATE_AH,
        "session_id": telegram_user_id
    }

    # 2. Send POST request to Core SaaS Endpoint
    # 180s total timeout, 15s for connection start
    timeout = aiohttp.ClientTimeout(total=180, connect=15, sock_read=180)
    
    # Use a connector that keeps the connection alive
    connector = aiohttp.TCPConnector(keepalive_timeout=30)
    
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        try:
            async with session.post(f"{API_BASE_URL}/{TENANT_ID}/chat", json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    await update.message.reply_text(f"❌ Core API Error: {resp.status} - {text}")
                    return

                result = await resp.json()

                # Debug log so we can see what the bot receives
                can_ans = result.get("can_answer", False)
                preview = result.get("answer_text", "")[:80]
                logger.info(f"Response: can_answer={can_ans} | preview='{preview}'")

                # 3. Handle response formatting
                if not can_ans:
                    # Show the refusal in plain text (no Markdown parse issues)
                    await update.message.reply_text(result.get("answer_text", "I cannot address this from my documented works."))
                    return

                formatted = _format_response(result)
                await _send_long(update, formatted)

        except (aiohttp.ServerTimeoutError, asyncio.TimeoutError, asyncio.exceptions.CancelledError):
            logger.warning("API request timed out or was cancelled — LLM may be slow")
            await update.message.reply_text(
                "⏳ The scholar is deep in contemplation... The response took too long. "
                "Please send your question again."
            )
        except Exception as e:
            logger.error(f"Error calling Core API: {e}", exc_info=True)
            await update.message.reply_text("❌ An error occurred connecting to the backend.")


# ── Bot Builder ──────────────────────────────────────────

def create_bot() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set.")

    # High-patience connection settings for slow networks
    from telegram.request import HTTPXRequest
    request = HTTPXRequest(
        connection_pool_size=10,
        connect_timeout=60.0,  # Wait up to 1 minute to connect
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=60.0,
    )

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request)
        .get_updates_request(HTTPXRequest(connect_timeout=60.0, read_timeout=60.0))
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("sources", sources_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app

def run_bot():
    print(f"\n🤖 Starting {TENANT_ID} Persona Bot (polling mode)...")
    print(f"   Target API: {API_BASE_URL}")
    print("   Press Ctrl+C to stop.\n")
    app = create_bot()
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        stop_signals=None,  # Needed when running in a background thread
    )

if __name__ == "__main__":
    run_bot()
