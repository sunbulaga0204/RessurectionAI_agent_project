"""
System Prompt Builder — dynamically constructs the system prompt
from persona.json and research_notes.md.

This is the core persona engine: it transforms static configuration
into the LLM's behavioral identity.
"""

import json
import os
from typing import Optional

import config


_cached_prompt: Optional[str] = None
_cached_persona: Optional[dict] = None


def load_persona() -> dict:
    """Load and validate persona.json."""
    global _cached_persona
    if _cached_persona is not None:
        return _cached_persona

    if not os.path.isfile(config.PERSONA_FILE):
        raise FileNotFoundError(
            f"Persona file not found: {config.PERSONA_FILE}\n"
            "Create a persona.json defining your historical figure."
        )

    with open(config.PERSONA_FILE, 'r', encoding='utf-8') as f:
        persona = json.load(f)

    # Validate required fields
    required = ["name", "communication_style"]
    for field in required:
        if field not in persona:
            raise ValueError(f"persona.json missing required field: '{field}'")

    _cached_persona = persona
    return persona


def load_research_notes() -> str:
    """Load research_notes.md if it exists."""
    if not os.path.isfile(config.RESEARCH_NOTES_FILE):
        return ""

    with open(config.RESEARCH_NOTES_FILE, 'r', encoding='utf-8') as f:
        return f.read().strip()


def build_system_prompt() -> str:
    """
    Build the complete system prompt from persona + research notes.
    Cached after first call.
    """
    global _cached_prompt
    if _cached_prompt is not None:
        return _cached_prompt

    persona = load_persona()
    research_notes = load_research_notes()

    # Extract persona fields
    name = persona.get("name", "Historical Figure")
    name_display = persona.get("name_display", name)
    era = persona.get("era", "")
    field = persona.get("field", "")
    bio = persona.get("bio_summary", "")

    style = persona.get("communication_style", {})
    tone = style.get("tone", "scholarly, analytical")
    hallmarks = style.get("hallmarks", [])
    avoids = style.get("avoids", [])

    refusal = persona.get("refusal_style", "I cannot speak to this matter based on my documented works.")
    greeting = persona.get("greeting", "")
    closing = persona.get("closing", "")
    disclaimer = persona.get("disclaimer", "")

    # Build hallmarks text
    hallmarks_text = "\n".join(f"  • {h}" for h in hallmarks) if hallmarks else "  • (none specified)"
    avoids_text = "\n".join(f"  • {a}" for a in avoids) if avoids else "  • (none specified)"

    prompt = f"""\
You are {name} ({era}), a historical figure known for work in {field}.

BIOGRAPHICAL CONTEXT:
{bio}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PERSONA VOICE & COMMUNICATION STYLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tone: {tone}

Rhetorical hallmarks (YOU MUST exhibit these patterns):
{hallmarks_text}

You AVOID:
{avoids_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT GROUNDING RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Answer ONLY from the PROVIDED SOURCE documents. You are FORBIDDEN from using external knowledge.
2. Maintain the persona's voice, tone, and rhetorical patterns at ALL times.
3. Every claim MUST cite the source: book name, chapter, and PAGE NUMBER.
4. If you cannot answer from the provided sources, respond with: "{refusal}"
5. You may contextualize and explain the sources, but NEVER fabricate content.
6. When quoting directly from sources, use quotation marks and cite precisely.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE JSON FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You MUST respond in this JSON format:
{{
  "can_answer": true,
  "answer_text": "Your response in the persona's voice, with inline source references.",
  "citations": [
    {{
      "book": "Title of the book",
      "chapter": "Chapter name",
      "page_number": "Page number or range",
      "quote": "Direct quote from the source text"
    }}
  ],
  "follow_up": "An optional follow-up question or suggestion for further reading from the persona's perspective.",
  "closing": "{closing}"
}}

If you CANNOT answer (no relevant sources):
{{
  "can_answer": false,
  "answer_text": "{refusal}",
  "citations": [],
  "follow_up": "",
  "closing": "{closing}"
}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESEARCH NOTES FROM BIOGRAPHERS & SCHOLARS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{research_notes if research_notes else "(No additional research notes provided.)"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DISCLAIMER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{disclaimer if disclaimer else "This is an AI reconstruction for research purposes only."}
"""

    _cached_prompt = prompt
    return prompt


def get_persona_info() -> dict:
    """Return persona info for frontend display (safe subset)."""
    persona = load_persona()
    return {
        "name": persona.get("name", ""),
        "name_display": persona.get("name_display", persona.get("name", "")),
        "era": persona.get("era", ""),
        "field": persona.get("field", ""),
        "bio_summary": persona.get("bio_summary", ""),
        "greeting": persona.get("greeting", ""),
        "disclaimer": persona.get("disclaimer", ""),
        "major_works": persona.get("major_works", []),
    }


def reset_cache():
    """Force reload of persona and prompt (useful for hot-reloading)."""
    global _cached_prompt, _cached_persona
    _cached_prompt = None
    _cached_persona = None
