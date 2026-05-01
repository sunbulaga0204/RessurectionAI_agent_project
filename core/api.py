"""
API — FastAPI backend serving the RAG pipeline and web chatbot.
Provides endpoints for chat, persona info, sources, and session export.
Also serves the static web frontend.

Pipeline flow:
  analyze_intent (Router / fast model)
    ├─ casual query → generate_direct_answer (120b, no RAG, no Verifier)
    └─ rag query    → vector retrieval → generate_answer → verify_answer
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

import core.config as config
import core.vector_store as vector_store
import core.llm_client as llm_client
import core.session_manager as session_manager

logger = logging.getLogger(__name__)


# ── Lifespan ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize core services on startup."""
    store_type = config.VECTOR_STORE_TYPE.capitalize()
    print(f"\n🗄️  Initializing {store_type} Vector Store...")
    vector_store.initialize()
    yield
    print("\n👋 Resurrection Agent shutting down...")


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
    system_prompt: str
    death_date_ah: str
    session_id: Optional[str] = None


class Citation(BaseModel):
    book: str = ""
    volume: str = ""   # e.g. "Vol. 1" for multi-volume works like the Ihya'
    chapter: str = ""  # may be omitted by the LLM
    page_number: str = ""
    quote: str = ""    # may be omitted by the LLM

    @classmethod
    def from_llm(cls, data: dict) -> "Citation":
        """Construct from LLM output, coercing None fields to empty strings."""
        return cls(
            book=data.get("book") or "",
            volume=str(data.get("volume") or ""),
            chapter=data.get("chapter") or "",
            page_number=str(data.get("page_number") or ""),
            quote=data.get("quote") or "",
        )


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
    return {"status": "ok", "provider": config.OPENROUTER_MODEL}


@app.get("/api/persona")
async def persona():
    """Return empty persona info for headless mode."""
    return {"name": "SaaS Platform", "description": "Core routing backend"}


@app.get("/api/v1/{tenant_id}/sources")
async def sources(tenant_id: str):
    """Return list of ingested sources for a specific tenant."""
    stats = vector_store.get_source_stats(tenant_id)
    return stats


@app.post("/api/v1/{tenant_id}/chat", response_model=ChatResponse)
async def chat(tenant_id: str, req: ChatRequest):
    """
    SaaS Chat endpoint — runs the isolated RAG pipeline.

    Flow:
      1. analyze_intent  → determines intent, language, search_string, requires_rag
      2a. casual intent  → generate_answer with no sources (fast path, no RAG/Verifier)
      2b. rag intent     → vector retrieval → generate_answer → verify_answer
    """
    # Session management sandboxed by tenant
    session_id = session_manager.get_or_create_session(tenant_id, req.session_id)
    history = session_manager.get_history(session_id)

    try:
        # ── Step 1: Intent Routing ────────────────────────────────
        # Analyzes query to get intent, language, search_string, requires_rag.
        # Always runs regardless of ingestion state — casual queries need no corpus.
        router_output = llm_client.analyze_intent(req.query, history)
        intent = router_output.get("intent", "general_question")
        requires_rag = router_output.get("requires_rag", True)
        search_query = router_output.get("search_string", req.query)

        # ── Step 2a: Casual Fast Path (no RAG, no Verifier) ──────
        if not requires_rag:
            print(f"  ⚡ Casual fast path: intent='{intent}' — skipping RAG and Verifier")
            result = llm_client.generate_answer(
                req.query,
                retrieved_chunks=[],        # No sources needed for casual chat
                system_prompt=req.system_prompt,
                conversation_history=history,
                intent=intent,
            )
            session_manager.add_turn(session_id, "user", req.query)
            session_manager.add_turn(session_id, "assistant", result.get("answer_text", ""))
            session_manager.cleanup_expired()
            return ChatResponse(
                answer_text=result.get("answer_text", ""),
                can_answer=result.get("can_answer", True),
                citations=[],
                follow_up=result.get("follow_up", ""),
                closing=result.get("closing", ""),
                session_id=session_id,
            )

        # ── Step 2b: RAG Path ─────────────────────────────────────
        # Only check ingestion state when we actually need the corpus.
        if not vector_store.is_ingested(tenant_id):
            return ChatResponse(
                answer_text="No source texts have been linked to this persona. The administrator needs to run the ingestion script.",
                can_answer=False,
                session_id=session_id,
            )

        # Retrieve with appropriate strategy based on search query complexity
        is_complex = len(search_query) > 60
        if is_complex:
            print(f"  🔍 Multi-layer retrieval (complex query, {len(search_query)} chars)")
            retrieved_chunks = vector_store.query_multilayer(
                tenant_id=tenant_id,
                text=search_query,
                death_date_ah=req.death_date_ah,
                top_k=config.TOP_K
            )
        else:
            retrieved_chunks = vector_store.query(
                tenant_id=tenant_id,
                text=search_query,
                death_date_ah=req.death_date_ah,
                top_k=config.TOP_K
            )

        if not retrieved_chunks:
            return ChatResponse(
                answer_text="I cannot address this query from my documented works.",
                can_answer=False,
                session_id=session_id,
            )

        # Generate answer with provided system prompt and history.
        # Pass the ORIGINAL user query (not the search string) so the bot
        # answers naturally and in the user's own language.
        result = llm_client.generate_answer(
            req.query, retrieved_chunks, req.system_prompt, history, intent=intent
        )

        # Verify grounding
        if result.get("can_answer") and config.ENABLE_VERIFICATION:
            is_grounded = llm_client.verify_answer(retrieved_chunks, result)
            if not is_grounded:
                result["can_answer"] = False
                result["answer_text"] = "I prefer not to provide an unverified answer."
                result["citations"] = []

        # Store turns in sandboxed session memory
        session_manager.add_turn(session_id, "user", req.query)
        session_manager.add_turn(session_id, "assistant", result.get("answer_text", ""))
        session_manager.cleanup_expired()

        return ChatResponse(
            answer_text=result["answer_text"],
            can_answer=result["can_answer"],
            citations=[Citation.from_llm(c) for c in result["citations"]],
            follow_up=result["follow_up"],
            closing=result["closing"],
            session_id=session_id,
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return ChatResponse(
            answer_text="An error occurred while processing your question. Please try again.",
            can_answer=False,
            session_id=session_id,
        )


@app.post("/api/v1/export")
async def export_chat(req: ExportRequest):
    """Export a chat session as JSON or Markdown."""
    if req.format == "markdown":
        md_text = session_manager.export_session_markdown(req.session_id, "Persona")
        return PlainTextResponse(md_text, media_type="text/markdown")
    else:
        data = session_manager.export_session(req.session_id, "Persona")
        return JSONResponse(data)
