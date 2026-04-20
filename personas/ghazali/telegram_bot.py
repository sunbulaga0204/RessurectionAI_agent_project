"""
Telegram Bot — handles user interactions via Telegram.
Acts as a frontend client for the Core API SaaS.
"""

import os
import json
import logging
import aiohttp

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
TENANT_ID = "ghazali"
DEATH_DATE_AH = "505"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Helpers ──────────────────────────────────────────────

def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#',
               '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special:
        text = text.replace(char, f'\\{char}')
    return text

def _format_response(result: dict) -> str:
    """Format the API JSON response into a Telegram message."""
    parts = []

    answer = result.get("answer_text", "")
    if answer:
        parts.append(_escape_md(answer))

    citations = result.get("citations", [])
    if citations:
        parts.append(f"\n📄 *Sources:*")
        for i, c in enumerate(citations, 1):
            book = _escape_md(c.get("book", "Unknown"))
            chapter = _escape_md(c.get("chapter", ""))
            page = _escape_md(str(c.get("page_number", "")))
            quote = _escape_md(c.get("quote", ""))

            ref_parts = [f"*{book}*"]
            if chapter:
                ref_parts.append(f"Ch\\. {chapter}")
            if page:
                ref_parts.append(f"p\\. {page}")

            parts.append(f"\n\\[{i}\\] {', '.join(ref_parts)}")
            if quote:
                parts.append(f"  _\\\"{quote}\\\"_")

    follow_up = result.get("follow_up", "")
    if follow_up:
        parts.append(f"\n💡 {_escape_md(follow_up)}")

    closing = result.get("closing", "")
    if closing:
        parts.append(f"\n__{_escape_md(closing)}__")

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

    payload = {
        "query": query,
        "system_prompt": prompt,
        "death_date_ah": DEATH_DATE_AH,
        "session_id": telegram_user_id
    }

    # 2. Sent POST request to Core SaaS Endpoint
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{API_BASE_URL}/{TENANT_ID}/chat", json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    await update.message.reply_text(f"❌ Core API Error: {resp.status} - {text}")
                    return
                
                result = await resp.json()
                
                # 3. Handle response formatting
                formatted = _format_response(result)
                await _send_long(update, formatted)

        except Exception as e:
            logger.error(f"Error calling Core API: {e}", exc_info=True)
            await update.message.reply_text("❌ An error occurred connecting to the backend.")

# ── Bot Builder ──────────────────────────────────────────

def create_bot() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set.")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
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
    )

if __name__ == "__main__":
    run_bot()
