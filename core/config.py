"""
Configuration for the Resurrection Agent.
Reads settings from environment variables / .env file.
Supports dual LLM providers (Gemini / Claude).
Embedding: Voyage AI (voyage-4-lite).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM Provider ─────────────────────────────────────────
# "gemini", "claude", or "openrouter"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").lower()

# ── API Keys ─────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Voyage AI — used exclusively for embeddings
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

# ── Vector Store ─────────────────────────────────────────
# "chroma" (local) or "postgres" (cloud/Railway)
VECTOR_STORE_TYPE = os.getenv("VECTOR_STORE_TYPE", "chroma").lower()
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
DATABASE_URL = os.getenv("DATABASE_URL", "") # For Railway PostgreSQL

# ── Paths ────────────────────────────────────────────────
SOURCES_DIR = os.getenv("SOURCES_DIR", "./sources")
PERSONA_FILE = os.getenv("PERSONA_FILE", "./persona.json")
RESEARCH_NOTES_FILE = os.getenv("RESEARCH_NOTES_FILE", "./research_notes.md")

# ── Chunking ─────────────────────────────────────────────
# Token-approximation based (1 token ≈ 4 chars for mixed Arabic/English)
# 800 tokens → ~3200 chars; well within Voyage's 32k-token context window
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

# ── Retrieval ────────────────────────────────────────────
TOP_K = int(os.getenv("TOP_K", "8"))

# ── Model Settings ───────────────────────────────────────
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-4-lite")
# MRL output dimension: 256 | 512 | 1024 | 2048
VOYAGE_OUTPUT_DIMENSION = int(os.getenv("VOYAGE_OUTPUT_DIMENSION", "1024"))
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "750"))
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", "128000"))

# ── Verification ─────────────────────────────────────────
ENABLE_VERIFICATION = os.getenv("ENABLE_VERIFICATION", "true").lower() == "true"

# ── Rate Limiting ────────────────────────────────────────
# Voyage supports batches of up to 128 texts with no free-tier throttling
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "128"))
EMBED_DELAY_SECONDS = float(os.getenv("EMBED_DELAY_SECONDS", "0"))

# ── Session Memory ───────────────────────────────────────
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "24"))
MAX_MEMORY_TURNS = int(os.getenv("MAX_MEMORY_TURNS", "20"))

# ── Web Server ───────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
