"""
API — FastAPI backend serving the RAG pipeline and web chatbot.
Provides endpoints for chat, persona info, sources, and session export.
Also serves the static web frontend.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

import config
import vector_store
import llm_client
import session_manager
from system_prompt import get_persona_info, load_persona

logger = logging.getLogger(__name__)


# ── Lifespan ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    print("\n🗄️  Loading vector store...")
    vector_store.initialize()
    if vector_store.is_ingested():
        stats = vector_store.get_source_stats()
        print(f"  ✓ {stats['total_chunks']} chunks from: {', '.join(stats['books'])}")
    else:
        print("  ⚠ No sources ingested yet. Run 'python ingest.py' first.")
    yield
    print("\n👋 Shutting down...")


# ── App ──────────────────────────────────────────────────

app = FastAPI(
    title="Resurrection Agent",
    description="Historical Persona RAG Chatbot",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ────────────────────────────

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class Citation(BaseModel):
    book: str = ""
    chapter: str = ""
    page_number: str = ""
    quote: str = ""


class ChatResponse(BaseModel):
    answer_text: str
    can_answer: bool
    citations: list[Citation] = Field(default_factory=list)
    follow_up: str = ""
    closing: str = ""
    session_id: str = ""
    persona_name: str = ""


class ExportRequest(BaseModel):
    session_id: str
    format: str = "json"  # "json" or "markdown"


# ── Endpoints ────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Health check."""
    return {"status": "ok", "provider": config.LLM_PROVIDER}


@app.get("/api/persona")
async def persona():
    """Return persona info for frontend display."""
    return get_persona_info()


@app.get("/api/sources")
async def sources():
    """Return list of ingested sources."""
    stats = vector_store.get_source_stats()
    return stats


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main chat endpoint — runs the RAG pipeline:
    1. Get/create session
    2. Retrieve relevant chunks
    3. Generate persona-voiced answer
    4. Verify grounding
    5. Store in session memory
    """
    # Session management
    session_id = session_manager.get_or_create_session(req.session_id)
    history = session_manager.get_history(session_id)

    # Get persona info
    try:
        persona = load_persona()
        persona_name = persona.get("name_display", persona.get("name", "Persona"))
    except Exception:
        persona_name = "Persona"

    # Check if sources are ingested
    if not vector_store.is_ingested():
        return ChatResponse(
            answer_text="No source texts have been loaded yet. The administrator needs to run the ingestion script first.",
            can_answer=False,
            session_id=session_id,
            persona_name=persona_name,
        )

    try:
        # Retrieve relevant chunks
        retrieved_chunks = vector_store.query(req.query, top_k=config.TOP_K)

        if not retrieved_chunks:
            refusal = persona.get("refusal_style", "I cannot address this query from my documented works.")
            return ChatResponse(
                answer_text=refusal,
                can_answer=False,
                session_id=session_id,
                persona_name=persona_name,
            )

        # Generate answer with conversation history
        result = llm_client.generate_answer(req.query, retrieved_chunks, history)

        # Verify grounding
        if result.get("can_answer") and config.ENABLE_VERIFICATION:
            is_grounded = llm_client.verify_answer(retrieved_chunks, result)
            if not is_grounded:
                result["can_answer"] = False
                result["answer_text"] = (
                    "I found some relevant passages, but I could not verify that my "
                    "response is strictly grounded in the source texts. "
                    "I prefer not to provide an unverified answer."
                )
                result["citations"] = []

        # Store turns in session memory
        session_manager.add_turn(session_id, "user", req.query)
        session_manager.add_turn(session_id, "assistant", result.get("answer_text", ""))

        # Periodic cleanup
        session_manager.cleanup_expired()

        return ChatResponse(
            answer_text=result.get("answer_text", ""),
            can_answer=result.get("can_answer", False),
            citations=[Citation(**c) for c in result.get("citations", [])],
            follow_up=result.get("follow_up", ""),
            closing=result.get("closing", ""),
            session_id=session_id,
            persona_name=persona_name,
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return ChatResponse(
            answer_text="An error occurred while processing your question. Please try again.",
            can_answer=False,
            session_id=session_id,
            persona_name=persona_name,
        )


@app.post("/api/export")
async def export_chat(req: ExportRequest):
    """Export a chat session as JSON or Markdown."""
    try:
        persona = load_persona()
        persona_name = persona.get("name_display", persona.get("name", "Persona"))
    except Exception:
        persona_name = "Persona"

    if req.format == "markdown":
        md_text = session_manager.export_session_markdown(req.session_id, persona_name)
        return PlainTextResponse(md_text, media_type="text/markdown")
    else:
        data = session_manager.export_session(req.session_id, persona_name)
        return JSONResponse(data)


# ── Serve Static Frontend ────────────────────────────────
# Must be added LAST so it doesn't catch API routes
import os
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
