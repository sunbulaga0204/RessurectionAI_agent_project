# 🎭 Resurrection Agent

**Converse with historical figures through their documented works.**

A replicable RAG-based framework for creating AI chatbot personas of historical scholars and figures, strictly grounded in their primary source texts. Every response cites specific pages and sources — no hallucination, no fabrication.

Built with Python · ChromaDB · Gemini/Claude · FastAPI · Telegram

---

# 📖 For End Users

## What Is This?

The Resurrection Agent allows you to have a conversation with a historical figure — but unlike generic AI chatbots, this one **only speaks from their actual documented works**. Every answer comes with page-level citations so you can verify every claim against the original sources.

This is a **research assistant**, not an entertainment bot. It is designed for academics, students, and researchers studying a particular historical figure.

## How to Use (Web Interface)

1. Open the chatbot URL in your browser
2. You'll see a welcome message from the persona with their greeting
3. Type your question in the input field and press Enter
4. The persona will respond **in their own voice** with citations
5. Click on any citation card to expand and see the direct quote
6. Use the 💡 follow-up suggestions to explore further

### Understanding Citations

Every response includes source citations like:

```
📄 Sources:
  [1] Mekka in the Latter Part of the 19th Century, Ch. Religious Learning, p. 3
      "The Great Mosque serves not only as the center of worship but also as
       the principal institution of learning..."
```

The **page number** refers to the original source text, so you can look it up yourself.

### Session & Export

- Your conversation context is maintained within a session (up to 24 hours)
- Click the ⬇️ **download** button to save your conversation as a `.md` file
- Click the 🔄 **refresh** button to start a new session

## How to Use (Telegram)

1. Find the bot on Telegram and send `/start`
2. Type your question directly
3. Available commands:
   - `/help` — Usage guide
   - `/about` — Who is this persona
   - `/sources` — View loaded source books
   - `/export` — Download conversation transcript
   - `/newsession` — Clear context, start fresh

## Important Disclaimers

> ⚠️ **This is an AI reconstruction** based on the documented writings of the historical figure. It does not represent the actual views or opinions of the real person.

> ⚠️ **Always verify** citations against the original source texts. While the system is designed to prevent fabrication, no AI system is perfect.

> ⚠️ **Research use only.** This tool is designed to assist scholarly inquiry, not to replace it.

---

# 🛠️ For Developers

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                   FRONTENDS                      │
│  ┌──────────────┐    ┌────────────────────────┐  │
│  │ Telegram Bot  │    │  Web Chatbot (FastAPI)  │  │
│  └──────┬───────┘    └──────────┬─────────────┘  │
│         │                       │                 │
│         └──────────┬────────────┘                 │
│                    ▼                              │
│         ┌─────────────────────┐                   │
│         │    api.py (FastAPI)   │                   │
│         │  Session Manager     │                   │
│         └─────────┬───────────┘                   │
│                   ▼                              │
│  ┌────────────────────────────────────────────┐  │
│  │              RAG PIPELINE                   │  │
│  │  ┌─────────────┐  ┌───────────────────┐   │  │
│  │  │ vector_store │  │   llm_client.py   │   │  │
│  │  │  (ChromaDB)  │  │ (Claude / Gemini) │   │  │
│  │  └──────┬──────┘  └────────┬──────────┘   │  │
│  │         │                  │               │  │
│  │         └──────┬───────────┘               │  │
│  │                ▼                           │  │
│  │    ┌──────────────────────┐                │  │
│  │    │  system_prompt.py     │                │  │
│  │    │  persona.json         │                │  │
│  │    │  research_notes.md    │                │  │
│  │    └──────────────────────┘                │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │            INGESTION PIPELINE               │  │
│  │  txt_to_json.py → data_loader → chunker    │  │
│  │        → vector_store.ingest()              │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Clone and install
cd "Ressurection Agent"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env: add GEMINI_API_KEY (required), optionally ANTHROPIC_API_KEY and TELEGRAM_BOT_TOKEN

# 3. Prepare sources
# Option A: Convert TXT files with page markers
python txt_to_json.py --input sources/raw/ --output sources/

# Option B: Place JSON files directly in sources/

# 4. Ingest sources (one-time)
python ingest.py

# 5. Start the agent
python main.py                  # Web UI only (http://localhost:8000)
python main.py --telegram       # Web UI + Telegram bot
python main.py --telegram-only  # Telegram only
```

## Creating a New Persona

This is the core replicability feature. To create an agent for a different historical figure:

### Step 1: Edit `persona.json`

```json
{
  "name": "Ibn Khaldun",
  "name_display": "Ibn Khaldun",
  "era": "1332–1406 CE",
  "field": "Historiography, Sociology, Economics",
  "language": "Arabic",
  "bio_summary": "North African polymath, considered the founder of sociology...",
  "major_works": ["Muqaddimah", "Kitab al-Ibar"],
  "communication_style": {
    "tone": "philosophical, analytical, observational",
    "hallmarks": [
      "Grounds arguments in cyclical theory of civilization (asabiyyah)",
      "Draws on extensive historical examples to support theoretical claims",
      "Uses 'It should be known that...' as a characteristic opener"
    ],
    "avoids": [
      "Speculation beyond documented positions",
      "References to events after 1406 CE"
    ]
  },
  "refusal_style": "This matter falls outside the scope of my investigations...",
  "greeting": "In the name of God. I am prepared to discuss matters of history and civilization.",
  "closing": "God knows best.",
  "disclaimer": "AI reconstruction for research purposes."
}
```

### Step 2: Write `research_notes.md`

Add notes from biographers and scholars about the figure's rhetorical style:

```markdown
# Research Notes: Ibn Khaldun

## Communication Style
- Opens chapters with "It should be known that..." (اعلم أن)
- Builds arguments inductively from historical evidence
- Frequently critiques earlier historians for lack of methodology
```

### Step 3: Prepare and Ingest Sources

```bash
# Convert TXT source files (with ### PAGE N ### markers)
python txt_to_json.py --input sources/raw/ --output sources/

# Ingest into ChromaDB
python ingest.py
```

### Step 4: Run

```bash
python main.py
```

That's it. The entire RAG pipeline, citation engine, and frontends adapt automatically.

## Source File Format

### TXT Files (for conversion)

Place page markers in your `.txt` files:

```
### PAGE 1 ###
Content of page 1...

### PAGE 2 ###
Content of page 2...
```

Supported delimiters: `### PAGE N ###`, `--- page N ---`, `[PAGE N]`, form feeds (`\f`).

### JSON Schema (canonical format)

```json
[
  {
    "text": "Full text content of this page/section...",
    "page_number": 42,
    "volume": "3",
    "chapter": "Chapter Title",
    "section": "Section Name",
    "source_file": "original_filename.txt",
    "book_name": "Full Book Title"
  }
]
```

## LLM Provider Configuration

| Provider | Env Variable | Best For | Cost |
|----------|-------------|----------|------|
| Gemini 2.5 Flash | `LLM_PROVIDER=gemini` | Free tier, large corpora | Free (rate-limited) |
| Claude Sonnet | `LLM_PROVIDER=claude` | Superior persona fidelity | Paid |

**Note:** Embeddings always use Gemini (free tier) regardless of the generation provider.

Set in `.env`:
```
LLM_PROVIDER=gemini          # or "claude"
GEMINI_API_KEY=your-key       # Always required (for embeddings)
ANTHROPIC_API_KEY=your-key    # Only if using Claude
```

## Project Structure

```
Ressurection Agent/
├── .env.example              # API key template
├── .gitignore
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── persona.json              # 🎭 Persona definition (EDIT THIS)
├── research_notes.md         # 📝 Biographer insights (EDIT THIS)
│
├── main.py                   # Entry point (web / telegram / both)
├── config.py                 # Environment-based settings
├── system_prompt.py          # Dynamic prompt builder
├── llm_client.py             # Dual LLM client (Claude / Gemini)
├── session_manager.py        # Conversation memory + export
├── data_loader.py            # JSON/TXT source loading
├── chunker.py                # Sentence-aware text splitting
├── vector_store.py           # ChromaDB + Gemini embeddings
├── txt_to_json.py            # TXT → JSON converter tool
├── api.py                    # FastAPI backend
├── telegram_bot.py           # Telegram bot handlers
├── ingest.py                 # One-time source ingestion
│
├── static/                   # Web chatbot UI
│   ├── index.html
│   ├── style.css
│   └── app.js
│
├── sources/                  # Source files (JSON)
│   ├── raw/                  # Original TXT files (pre-conversion)
│   └── sample.json           # Example data
│
└── chroma_db/                # Auto-created by ChromaDB
```

## API Endpoints

| Method | Endpoint | Description |
|--------|---------|-------------|
| `POST` | `/api/chat` | Send a query, get persona-voiced cited response |
| `GET` | `/api/persona` | Get persona display info |
| `GET` | `/api/sources` | Get ingested source statistics |
| `POST` | `/api/export` | Export session as JSON or Markdown |
| `GET` | `/api/health` | Health check |

### Chat Request

```json
POST /api/chat
{
  "query": "What did you observe about religious education in Mecca?",
  "session_id": "abc12345"   // optional, auto-created if omitted
}
```

### Chat Response

```json
{
  "answer_text": "During my stay in Mecca in 1884-1885, I had occasion to observe...",
  "can_answer": true,
  "citations": [
    {
      "book": "Mekka in the Latter Part of the 19th Century",
      "chapter": "Religious Learning in Mekka",
      "page_number": "3",
      "quote": "The Great Mosque serves not only as the center of worship..."
    }
  ],
  "follow_up": "You may also wish to inquire about the Jawi student community...",
  "closing": "I trust these observations may prove of some service.",
  "session_id": "abc12345",
  "persona_name": "C. Snouck Hurgronje"
}
```

## Extending the Framework

### Adding New Source Formats
Edit `data_loader.py` — add a new loader function and register it in the `LOADERS` dict.

### Custom Citation Format
Edit the `_format_response()` function in `telegram_bot.py` and the `appendAssistantMessage()` function in `static/app.js`.

### Multiple Personas
Each persona uses a different ChromaDB collection (derived from `persona.json`'s `name_display`). To switch personas, simply swap the `persona.json`, `research_notes.md`, and source files, then re-ingest.

### Deployment
- **Local**: `python main.py`
- **Docker**: Create a `Dockerfile` with the Python image, copy project files, install requirements, expose port 8000
- **Cloud**: Deploy to any platform supporting Python (Railway, Render, Fly.io, GCP Cloud Run)
- **Telegram-only** (cheapest): `python main.py --telegram-only` on any VPS

## License

This is a research tool framework. The source texts and persona configurations are the responsibility of the deployer to ensure proper attribution and rights.
