"""
Main Entry Point — starts the Resurrection Agent.

Usage:
    python main.py                  # Web UI + API only
    python main.py --telegram       # Web UI + API + Telegram bot
    python main.py --telegram-only  # Telegram bot only
"""

import sys
import argparse
import logging
import threading

import config
from system_prompt import load_persona, build_system_prompt
import vector_store


def main():
    parser = argparse.ArgumentParser(description="Resurrection Agent — Historical Persona RAG")
    parser.add_argument('--telegram', action='store_true', help='Also start Telegram bot')
    parser.add_argument('--telegram-only', action='store_true', help='Only start Telegram bot')
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    # Load and validate persona
    try:
        persona = load_persona()
        name = persona.get("name_display", persona.get("name", "Unknown"))
    except Exception as e:
        print(f"\n✗ Persona error: {e}")
        sys.exit(1)

    print("=" * 60)
    print(f"  🎭  Resurrection Agent — {name}")
    print("=" * 60)

    # Validate API keys
    if config.LLM_PROVIDER == "claude":
        if not config.ANTHROPIC_API_KEY:
            print("\n✗ ANTHROPIC_API_KEY not set (LLM_PROVIDER=claude)")
            sys.exit(1)
        if not config.GEMINI_API_KEY:
            print("\n⚠ GEMINI_API_KEY not set — embeddings require Gemini API")
            sys.exit(1)
    else:
        if not config.GEMINI_API_KEY:
            print("\n✗ GEMINI_API_KEY not set. Create a .env file from .env.example")
            sys.exit(1)

    if (args.telegram or args.telegram_only) and not config.TELEGRAM_BOT_TOKEN:
        print("\n✗ TELEGRAM_BOT_TOKEN not set.")
        sys.exit(1)

    # Initialize vector store
    print("\n🗄️  Loading vector store...")
    vector_store.initialize()

    if not vector_store.is_ingested():
        print("\n⚠ No source texts found. Run 'python ingest.py' first.")
        print("  The agent will start but cannot answer questions yet.\n")

    else:
        stats = vector_store.get_source_stats()
        print(f"  ✓ {stats['total_chunks']} chunks from: {', '.join(stats['books'])}")

    # Build system prompt (validates persona + research notes)
    print("\n🎭 Building persona prompt...")
    try:
        prompt = build_system_prompt()
        print(f"  ✓ System prompt built ({len(prompt)} chars)")
    except Exception as e:
        print(f"  ✗ Prompt build error: {e}")
        sys.exit(1)

    # Print config summary
    print(f"\n⚙️  Configuration:")
    print(f"  LLM Provider:    {config.LLM_PROVIDER}")
    if config.LLM_PROVIDER == "claude":
        print(f"  Model:           {config.CLAUDE_MODEL}")
    else:
        print(f"  Model:           {config.GEMINI_MODEL}")
    print(f"  Embeddings:      {config.EMBEDDING_MODEL}")
    print(f"  Top-K retrieval: {config.TOP_K}")
    print(f"  Temperature:     {config.TEMPERATURE}")
    print(f"  Verification:    {'Enabled' if config.ENABLE_VERIFICATION else 'Disabled'}")
    print(f"  Session TTL:     {config.SESSION_TTL_HOURS}h")

    # ── Start services ───────────────────────────────────
    if args.telegram_only:
        from telegram_bot import run_bot
        run_bot()

    elif args.telegram:
        # Run Telegram bot in a separate thread
        from telegram_bot import run_bot
        telegram_thread = threading.Thread(target=run_bot, daemon=True)
        telegram_thread.start()
        print("  ✓ Telegram bot started in background thread")

        # Run FastAPI in main thread
        import uvicorn
        print(f"\n🌐 Starting web server at http://{config.HOST}:{config.PORT}")
        uvicorn.run(
            "api:app",
            host=config.HOST,
            port=config.PORT,
            log_level="info",
        )

    else:
        # Web only
        import uvicorn
        print(f"\n🌐 Starting web server at http://{config.HOST}:{config.PORT}")
        uvicorn.run(
            "api:app",
            host=config.HOST,
            port=config.PORT,
            log_level="info",
        )


if __name__ == "__main__":
    main()
