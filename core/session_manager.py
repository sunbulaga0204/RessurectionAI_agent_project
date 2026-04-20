"""
Session Manager — handles conversation memory with TTL expiry
and chat export functionality.

Each session stores conversation turns and expires after SESSION_TTL_HOURS.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Optional

import core.config as config


# ── In-memory session store ──────────────────────────────
# {session_id: {"turns": [...], "created_at": float, "last_active": float}}
_sessions: dict[str, dict] = {}


def create_session(tenant_id: str) -> str:
    """Create a new session sandboxed to a specific tenant."""
    session_id = f"{tenant_id}_{str(uuid.uuid4())[:8]}"
    _sessions[session_id] = {
        "tenant_id": tenant_id,
        "turns": [],
        "created_at": time.time(),
        "last_active": time.time(),
    }
    return session_id


def get_or_create_session(tenant_id: str, session_id: Optional[str] = None) -> str:
    """Get an existing session or create a new one, verifying tenant boundaries."""
    if session_id and session_id in _sessions:
        session = _sessions[session_id]
        if session["tenant_id"] == tenant_id:
            # Check TTL
            age_hours = (time.time() - session["created_at"]) / 3600
            if age_hours < config.SESSION_TTL_HOURS:
                session["last_active"] = time.time()
                return session_id
            else:
                # Session expired
                del _sessions[session_id]

    return create_session(tenant_id)


def add_turn(session_id: str, role: str, content: str):
    """
    Add a conversation turn to the session.
    Trims old turns if exceeding MAX_MEMORY_TURNS.
    """
    if session_id not in _sessions:
        return

    session = _sessions[session_id]
    session["turns"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    })
    session["last_active"] = time.time()

    # Trim to max turns (keep most recent)
    max_turns = config.MAX_MEMORY_TURNS * 2  # user + assistant = 2 entries per turn
    if len(session["turns"]) > max_turns:
        session["turns"] = session["turns"][-max_turns:]


def get_history(session_id: str) -> list[dict]:
    """
    Get conversation history for the session.
    Returns list of {"role": str, "content": str} dicts.
    """
    if session_id not in _sessions:
        return []

    return [
        {"role": t["role"], "content": t["content"]}
        for t in _sessions[session_id]["turns"]
    ]


def export_session(session_id: str, persona_name: str = "Persona") -> dict:
    """
    Export a session as a downloadable JSON structure.
    """
    if session_id not in _sessions:
        return {"error": "Session not found"}

    session = _sessions[session_id]
    created = datetime.fromtimestamp(session["created_at"]).isoformat()

    return {
        "session_id": session_id,
        "persona": persona_name,
        "created_at": created,
        "exported_at": datetime.now().isoformat(),
        "turns": session["turns"],
        "total_turns": len(session["turns"]),
    }


def export_session_markdown(session_id: str, persona_name: str = "Persona") -> str:
    """
    Export a session as readable Markdown text.
    """
    if session_id not in _sessions:
        return "Session not found."

    session = _sessions[session_id]
    created = datetime.fromtimestamp(session["created_at"]).strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# Conversation with {persona_name}",
        f"*Session: {session_id} | Started: {created}*\n",
        "---\n",
    ]

    for turn in session["turns"]:
        if turn["role"] == "user":
            lines.append(f"**You:** {turn['content']}\n")
        else:
            lines.append(f"**{persona_name}:** {turn['content']}\n")
        lines.append("")

    lines.append("---")
    lines.append(f"*Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


def cleanup_expired():
    """Remove all expired sessions. Call periodically."""
    now = time.time()
    ttl_seconds = config.SESSION_TTL_HOURS * 3600
    expired = [
        sid for sid, session in _sessions.items()
        if now - session["created_at"] > ttl_seconds
    ]
    for sid in expired:
        del _sessions[sid]

    if expired:
        print(f"  🧹 Cleaned up {len(expired)} expired sessions")


def get_session_count() -> int:
    """Return number of active sessions."""
    return len(_sessions)
