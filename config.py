"""
Configuration for the Resurrection Agent.
Reads settings from environment variables / .env file.
Supports dual LLM providers (Gemini / Claude).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM Provider ─────────────────────────────────────────
# "gemini" or "claude"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

# ── API Keys ─────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Paths ────────────────────────────────────────────────
SOURCES_DIR = os.getenv("SOURCES_DIR", "./sources")
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
PERSONA_FILE = os.getenv("PERSONA_FILE", "./persona.json")
RESEARCH_NOTES_FILE = os.getenv("RESEARCH_NOTES_FILE", "./research_notes.md")

# ── Chunking ─────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# ── Retrieval ────────────────────────────────────────────
TOP_K = int(os.getenv("TOP_K", "10"))

# ── Model Settings ───────────────────────────────────────
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "8192"))

# ── Verification ─────────────────────────────────────────
ENABLE_VERIFICATION = os.getenv("ENABLE_VERIFICATION", "true").lower() == "true"

# ── Rate Limiting (free tier) ────────────────────────────
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "5"))
EMBED_DELAY_SECONDS = float(os.getenv("EMBED_DELAY_SECONDS", "4"))

# ── Session Memory ───────────────────────────────────────
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "24"))
MAX_MEMORY_TURNS = int(os.getenv("MAX_MEMORY_TURNS", "20"))

# ── Web Server ───────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
