"""
Telegram Bot — handles user interactions via Telegram.
Uses python-telegram-bot v20+ with long-polling.
Persona-voiced responses with page-level citations.
"""

import json
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode, ChatAction

import config
import vector_store
import llm_client
import session_manager
from system_prompt import get_persona_info, load_persona

logger = logging.getLogger(__name__)

# Telegram user_id → session_id mapping
_user_sessions: dict[int, str] = {}

TELEGRAM_MAX_LENGTH = 4096


# ── Helpers ──────────────────────────────────────────────

def _get_session(user_id: int) -> str:
    """Get or create a session for a Telegram user."""
    existing = _user_sessions.get(user_id)
    session_id = session_manager.get_or_create_session(existing)
    _user_sessions[user_id] = session_id
    return session_id


def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#',
               '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special:
        text = text.replace(char, f'\\{char}')
    return text


def _format_response(result: dict, persona_name: str) -> str:
    """Format the LLM JSON response into a Telegram message."""
    parts = []

    # Answer
    answer = result.get("answer_text", "")
    if answer:
        parts.append(_escape_md(answer))

    # Citations
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

    # Follow-up
    follow_up = result.get("follow_up", "")
    if follow_up:
        parts.append(f"\n💡 {_escape_md(follow_up)}")

    # Closing
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
    """Handle /start — welcome in persona voice."""
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
    msg += f"/export — Download this conversation\n"
    msg += f"/newsession — Start a fresh conversation\n\n"
    if disclaimer:
        msg += f"⚠️ _{_escape_md(disclaimer)}_"

    try:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        await update.message.reply_text(msg)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""
    msg = (
        "📖 *How to use this bot*\n\n"
        "Simply type your question, and I will search my documented works "
        "to provide a cited answer in the persona's own voice\\.\n\n"
        "*Features:*\n"
        "• Every answer cites specific page numbers from source texts\n"
        "• Conversation context is maintained within your session\n"
        "• Use /export to download the conversation as text\n"
        "• Use /newsession to start fresh\n\n"
        "⚠️ This is an AI reconstruction for research purposes only\\."
    )
    try:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        await update.message.reply_text(msg)


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about — persona bio."""
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
    """Handle /sources — list loaded source books."""
    stats = vector_store.get_source_stats()
    if stats["total_chunks"] > 0:
        books_list = "\n".join(f"  • {_escape_md(b)}" for b in stats["books"])
        msg = f"📚 *Loaded Sources* \\({stats['total_chunks']} chunks\\)\n\n{books_list}"
    else:
        msg = "📚 No sources loaded yet\\. Run `python ingest\\.py` first\\."

    try:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception:
        await update.message.reply_text(msg)


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /export — send conversation as downloadable text."""
    user_id = update.effective_user.id
    session_id = _user_sessions.get(user_id)

    if not session_id:
        await update.message.reply_text("No active conversation to export.")
        return

    try:
        persona = load_persona()
        persona_name = persona.get("name_display", "Persona")
    except Exception:
        persona_name = "Persona"

    md_text = session_manager.export_session_markdown(session_id, persona_name)

    if "Session not found" in md_text:
        await update.message.reply_text("No conversation found for this session.")
        return

    # Send as a document
    import io
    file_bytes = md_text.encode("utf-8")
    doc = io.BytesIO(file_bytes)
    doc.name = f"conversation_{session_id}.md"

    await update.message.reply_document(
        document=doc,
        caption="📥 Your conversation transcript",
    )


async def newsession_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /newsession — start a fresh conversation."""
    user_id = update.effective_user.id
    new_id = session_manager.create_session()
    _user_sessions[user_id] = new_id
    await update.message.reply_text("🔄 New session started. Previous context cleared.")


# ── Message Handler ──────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages — run the RAG pipeline."""
    user_id = update.effective_user.id
    query = update.message.text.strip()

    if not query:
        return

    if not vector_store.is_ingested():
        await update.message.reply_text(
            "⚠️ No source texts have been loaded yet. "
            "The administrator needs to run the ingestion script first."
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        # Session management
        session_id = _get_session(user_id)
        history = session_manager.get_history(session_id)

        # Get persona name
        try:
            persona = load_persona()
            persona_name = persona.get("name_display", "Persona")
        except Exception:
            persona_name = "Persona"

        # Retrieve
        retrieved_chunks = vector_store.query(query, top_k=config.TOP_K)

        if not retrieved_chunks:
            refusal = persona.get("refusal_style", "I cannot address this from my documented works.")
            await update.message.reply_text(f"🔍 {refusal}")
            return

        # Generate
        await update.message.chat.send_action(ChatAction.TYPING)
        result = llm_client.generate_answer(query, retrieved_chunks, history)

        if not result.get("can_answer", False):
            answer = result.get("answer_text", "I cannot address this query.")
            await update.message.reply_text(f"🔍 {answer}")
            session_manager.add_turn(session_id, "user", query)
            session_manager.add_turn(session_id, "assistant", answer)
            return

        # Verify
        if config.ENABLE_VERIFICATION:
            await update.message.chat.send_action(ChatAction.TYPING)
            is_grounded = llm_client.verify_answer(retrieved_chunks, result)
            if not is_grounded:
                msg = ("⚠️ I found relevant passages, but could not verify "
                       "that my response is strictly grounded in sources.")
                await update.message.reply_text(msg)
                return

        # Format and send
        formatted = _format_response(result, persona_name)
        await _send_long(update, formatted)

        # Store in session
        session_manager.add_turn(session_id, "user", query)
        session_manager.add_turn(session_id, "assistant", result.get("answer_text", ""))

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ An error occurred while processing your question. Please try again."
        )


# ── Bot Builder ──────────────────────────────────────────

def create_bot() -> Application:
    """Build and return the Telegram bot Application."""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("sources", sources_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("newsession", newsession_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


def run_bot():
    """Start the bot with long-polling."""
    print("\n🤖 Starting Telegram bot (polling mode)...")
    print("   Press Ctrl+C to stop.\n")

    app = create_bot()
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    run_bot()
