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

from core import config
from core import vector_store


def main():
    parser = argparse.ArgumentParser(description="Resurrection Agent — SaaS API Backend Node")
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    print("=" * 60)
    print("  🚀  Resurrection Agent — SaaS Core API Started")
    print("=" * 60)

    # Validate API keys
    if config.LLM_PROVIDER == "claude":
        if not config.ANTHROPIC_API_KEY:
            print("\n✗ ANTHROPIC_API_KEY not set (LLM_PROVIDER=claude)")
            sys.exit(1)
        if not config.GEMINI_API_KEY:
            print("\n⚠ GEMINI_API_KEY not set — embeddings require Gemini/Voyage API")
            sys.exit(1)
    else:
        if not config.GEMINI_API_KEY:
            print("\n✗ GEMINI_API_KEY not set. Create a .env file from .env.example")
            sys.exit(1)

    # Prepare vector store client (lazy load on requests)
    print("\n🗄️  Connecting to ChromaDB Engine...")
    vector_store.initialize()

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

    # ── Start SaaS API Server ───────────────────────────────────
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
