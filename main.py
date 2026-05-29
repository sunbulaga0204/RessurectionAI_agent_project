"""
Main Entry Point — starts the Resurrection Agent.

This module acts as the bootsrapper for the Resurrection Agent SaaS Node.
It handles CLI parameter parsing, global logging initialization, credentials
validation, vector store pre-warming, and manages process execution by either
spinning up the Telegram bot, the FastAPI uvicorn server, or both in tandem.

Usage:
    python main.py                  # Web UI + API only
    python main.py --telegram       # Web UI + API + Telegram bot
    python main.py --telegram-only  # Telegram bot only
"""

import sys
import argparse
import logging
import threading

from core import config
from core import vector_store


def main():
    """
    Main orchestration routine.
    1. Parses command line arguments to determine execution mode.
    2. Configures standard output logging.
    3. Validates essential API keys for LLMs and embeddings.
    4. Initializes the vector store.
    5. Optionally spawns a background thread for the Telegram Bot.
    6. Starts the uvicorn server to host the REST API endpoints.
    """
    # ── 1. Parse Command Line Arguments ───────────────────────────
    parser = argparse.ArgumentParser(description="Resurrection Agent — SaaS API Backend Node")
    parser.add_argument("--telegram", action="store_true", help="Start the Telegram bot along with the API.")
    parser.add_argument("--telegram-only", action="store_true", help="Start only the Telegram bot.")
    args = parser.parse_args()

    # ── 2. Configure Logging ──────────────────────────────────────
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    print("=" * 60)
    print("  🚀  Resurrection Agent — SaaS Core API Started")
    print("=" * 60)

    # ── 3. Validate Credentials & Key Environments ────────────────
    # OpenRouter serves as the LLM completion gateway
    if not config.OPENROUTER_API_KEY:
        print("\n✗ OPENROUTER_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    # Voyage AI is required for embedding generation
    if not config.VOYAGE_API_KEY:
        print("\n✗ VOYAGE_API_KEY not set. Required for embeddings.")
        sys.exit(1)

    # ── 4. Warm-up Vector Database ────────────────────────────────
    # Pre-selects and tests connections to either local ChromaDB or pgvector
    store_type = config.VECTOR_STORE_TYPE.capitalize()
    print(f"\n🗄️  Initializing {store_type} Vector Store...")
    vector_store.initialize()

    # ── 5. Spawn Telegram Bot Thread ──────────────────────────────
    if args.telegram or args.telegram_only:
        from personas.ghazali.telegram_bot import run_bot as start_telegram_bot
        print("\n🤖 Starting Telegram Bot thread...")
        # Start bot in a background daemon thread to not block the main FastAPI process
        bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
        bot_thread.start()

    # ── 6. Handle Telegram-only Execution ─────────────────────────
    if args.telegram_only:
        print("\n⏳ Running in Telegram-only mode. Press Ctrl+C to stop.")
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping...")
            sys.exit(0)

    # ── 7. Print Active Runtime Config ────────────────────────────
    print(f"\n⚙️  Configuration:")
    print(f"  Provider:        OpenRouter")
    print(f"  Generator:       {config.OPENROUTER_MODEL}")
    print(f"  Router:          {config.ROUTER_MODEL}")
    print(f"  Embeddings:      {config.EMBEDDING_MODEL}")
    print(f"  Top-K retrieval: {config.TOP_K}")
    print(f"  Temperature:     {config.TEMPERATURE}")
    print(f"  Max Tokens:      {config.MAX_OUTPUT_TOKENS}")
    print(f"  Verification:    {'Enabled' if config.ENABLE_VERIFICATION else 'Disabled'}")
    print(f"  Session TTL:     {config.SESSION_TTL_HOURS}h")

    # ── 8. Boot SaaS HTTP API Server ──────────────────────────────
    import uvicorn
    print(f"\n🌐 Serving SaaS API at http://{config.HOST}:{config.PORT}")
    uvicorn.run(
        "core.api:app",
        host=config.HOST,
        port=config.PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()

