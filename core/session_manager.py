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
# format: {session_id: {"turns": [...], "created_at": float, "last_active": float}}
_sessions: dict[str, dict] = {}


def create_session(tenant_id: str) -> str:
    """
    Spawns a new session memory space sandboxed to a specific tenant identity.
    
    Args:
        tenant_id: The scoping identifier (e.g. 'ghazali').
    Returns:
        str: Generated session key.
    """
    session_id = f"{tenant_id}_{str(uuid.uuid4())[:8]}"
    _sessions[session_id] = {
        "tenant_id": tenant_id,
        "turns": [],
        "created_at": time.time(),
        "last_active": time.time(),
    }
    return session_id


def get_or_create_session(tenant_id: str, session_id: Optional[str] = None) -> str:
    """
    Fetches an existing active session or bootstraps a fresh session.
    Validates tenant scopes and enforces lifetime TTL expiration settings.
    
    Args:
        tenant_id: The scoping identifier.
        session_id: Optional existing session key.
    Returns:
        str: Active valid session key.
    """
    if session_id and session_id in _sessions:
        session = _sessions[session_id]
        if session["tenant_id"] == tenant_id:
            # Check if session has exceeded configured hours
            age_hours = (time.time() - session["created_at"]) / 3600
            if age_hours < config.SESSION_TTL_HOURS:
                session["last_active"] = time.time()
                return session_id
            else:
                # Evict expired session from store
                del _sessions[session_id]

    return create_session(tenant_id)


def add_turn(session_id: str, role: str, content: str):
    """
    Appends a user/assistant dialog turn to the session logs.
    Automatically clips old turns to respect configured sliding context window lengths.
    
    Args:
        session_id: target context key.
        role: Message author ('user' vs 'assistant').
        content: Text content of the turn.
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

    # Apply sliding window logic: user turn + assistant response = 2 items per dialog
    max_turns = config.MAX_MEMORY_TURNS * 2
    if len(session["turns"]) > max_turns:
        session["turns"] = session["turns"][-max_turns:]


def get_history(session_id: str) -> list[dict]:
    """
    Retrieves the active sliding dialog window history formatted for LLM client integration.
    
    Args:
        session_id: Target context key.
    Returns:
        List of dict elements matching structure {"role": str, "content": str}
    """
    if session_id not in _sessions:
        return []

    return [
        {"role": t["role"], "content": t["content"]}
        for t in _sessions[session_id]["turns"]
    ]


def export_session(session_id: str, persona_name: str = "Persona") -> dict:
    """
    Serializes a session conversation logs into a standard structured JSON dictionary.
    
    Args:
        session_id: Target context key.
        persona_name: Style name injected into metadata attributes.
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
    Formats the conversation logs into a beautiful, human-readable Markdown document.
    
    Args:
        session_id: Target context key.
        persona_name: The display name of the classical character.
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
    """
    Evicts all expired sessions from memory based on creation date offsets.
    Should be run periodically during transaction turns.
    """
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
    """
    Returns telemetry details outlining total active tracking nodes in memory.
    """
    return len(_sessions)

