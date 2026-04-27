"""
System Prompt Builder — dynamically constructs the system prompt
from persona.json and research_notes.md.

This is the core persona engine: it transforms static configuration
into the LLM's behavioral identity.
"""

import json
import os
from typing import Optional


_cached_prompt: Optional[str] = None
_cached_persona: Optional[dict] = None


def load_persona() -> dict:
    """Load and validate persona.json."""
    global _cached_persona
    if _cached_persona is not None:
        return _cached_persona

    persona_path = os.path.join(os.path.dirname(__file__), "persona.json")
    if not os.path.isfile(persona_path):
        raise FileNotFoundError(
            f"Persona file not found: {persona_path}\n"
            "Ensure persona.json exists in this folder."
        )

    with open(persona_path, 'r', encoding='utf-8') as f:
        persona = json.load(f)

    # Validate required fields
    required = ["name", "communication_style"]
    for field in required:
        if field not in persona:
            raise ValueError(f"persona.json missing required field: '{field}'")

    _cached_persona = persona
    return persona


def load_research_notes() -> str:
    """Load research_notes.md if it exists in this folder."""
    notes_path = os.path.join(os.path.dirname(__file__), "research_notes.md")
    if not os.path.isfile(notes_path):
        return ""

    with open(notes_path, 'r', encoding='utf-8') as f:
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
    keywords = persona.get("specialized_keywords", [])

    refusal_style = persona.get("refusal_style", "")
    greeting = persona.get("greeting", "")
    closing = persona.get("closing", "")
    disclaimer = persona.get("disclaimer", "")

    # Derive a clean first-person refusal message.
    # refusal_style is a third-person meta-description; use a simple default instead.
    refusal_message = "Accept Allah's actions and remain calm — this matter lies beyond what I may reveal to all seekers."

    # Build hallmarks text
    hallmarks_text = "\n".join(f"  • {h}" for h in hallmarks) if hallmarks else "  • (none specified)"
    avoids_text = "\n".join(f"  • {a}" for a in avoids) if avoids else "  • (none specified)"

    # Build keywords block (up to 100)
    keywords_capped = keywords[:100]
    if keywords_capped:
        keywords_text = ", ".join(f"`{k}`" for k in keywords_capped)
    else:
        keywords_text = "(none specified)"

    prompt = f"""\
You are {name} ({era}), {field}.

BIOGRAPHICAL CONTEXT:
{bio}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PERSONA VOICE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tone: {tone}

Rhetorical hallmarks (MUST be exhibited):
{hallmarks_text}

Avoid:
{avoids_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GROUNDING RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Prioritize the PROVIDED SOURCE documents above all else. Synthesize your answer primarily from them.
2. Maintain the persona voice at ALL times — speak as {name} in first person.
3. Cite every claim with: book title and page number ONLY (e.g. "Ihyā', p. 45").
4. Set can_answer=false ONLY when the source documents contain zero relevant information. If there is ANY partial match, answer from it.
5. Never fabricate quotes or page numbers that do not appear in the sources.
6. Use the SPECIALIZED KEYWORDS naturally when they appear in context:
   {keywords_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT RULES — STRICT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• TOTAL response (answer_text + citations combined) MUST NOT exceed 300 words.
• answer_text must be one focused paragraph in the persona's voice.
• Lead with the single strongest quote from the sources, then elaborate in 2-3 sentences maximum.
• Citation format: only "book_title" and "page_number". Omit chapter and full quote fields.
• Do NOT pad with summaries, lists, or meta-commentary.
• IMPORTANT FORMATTING: Any Arabic text MUST be isolated on its own line. Always insert a double newline (\n\n) before and after any Arabic words or quotes to prevent right-to-left text from mixing with English.
• closing field: one short sentence only.
• follow_up: omit unless specifically prompted.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE JSON FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond ONLY in this compact JSON:
{{
  "can_answer": true,
  "answer_text": "One focused paragraph in my voice, opening with the strongest source quote in quotation marks, followed by at most 2-3 sentences of elaboration. Total: under 200 words.",
  "citations": [
    {{
      "book": "Short book title",
      "page_number": "p. X"
    }}
  ],
  "closing": "{closing}"
}}

If the sources truly contain NO relevant information on this query:
{{
  "can_answer": false,
  "answer_text": "{refusal_message}",
  "citations": [],
  "closing": "{closing}"
}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESEARCH NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{research_notes if research_notes else "(None provided.)"}

DISCLAIMER: {disclaimer if disclaimer else "AI reconstruction for research purposes only."}
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
