"""
Data Loader — loads source files (JSON, TXT, Markdown) from the sources directory.
Returns a list of Document dicts: {"text": str, "metadata": dict}

JSON is the canonical format. Use txt_to_json.py to convert TXT files first.
"""

import json
import os
import re
from pathlib import Path

import core.openiti_client as openiti_client

def load_json(filepath: str) -> list[dict]:
    """
    Load a JSON source file.
    Expects an array of objects with: text, page_number, book_name, chapter, etc.
    """
    documents = []
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict) and "entries" in data:
        entries = data["entries"]
    else:
        entries = [data]

    for entry in entries:
        text = entry.get("text", "").strip()
        if not text:
            continue
        documents.append({
            "text": text,
            "metadata": {
                "book_name": entry.get("book_name", "Unknown"),
                "chapter": entry.get("chapter", ""),
                "section": entry.get("section", ""),
                "volume": entry.get("volume", ""),
                "page_number": str(entry.get("page_number", "")),
                "source_file": entry.get("source_file", os.path.basename(filepath)),
            },
        })
    return documents


def load_txt(filepath: str) -> list[dict]:
    """
    Load a plain .txt file as a single document.
    For page-level metadata, convert to JSON first with txt_to_json.py.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    if not content:
        return []

    return [{
        "text": content,
        "metadata": {
            "book_name": Path(filepath).stem.replace('_', ' ').title(),
            "chapter": "",
            "section": "",
            "volume": "",
            "page_number": "",
            "source_file": os.path.basename(filepath),
        },
    }]


def load_markdown(filepath: str) -> list[dict]:
    """
    Load a Markdown file. Extracts metadata from [TAG: value] markers if present.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    if not content:
        return []

    metadata = {
        "book_name": Path(filepath).stem.replace('_', ' ').title(),
        "chapter": "",
        "section": "",
        "volume": "",
        "page_number": "",
        "source_file": os.path.basename(filepath),
    }

    # Try to extract [TAG: value] style metadata
    for tag in ("BOOK_NAME", "CHAPTER", "SECTION", "VOLUME", "PAGE"):
        match = re.search(rf'\[{tag}:\s*(.+?)\]', content)
        if match:
            key = tag.lower()
            if key == "page":
                key = "page_number"
            metadata[key] = match.group(1).strip()

    # Remove tag lines from text
    clean_text = re.sub(
        r'\[(SOURCE_START|SOURCE_END|BOOK_NAME|CHAPTER|SECTION|VOLUME|PAGE):?\s*[^\]]*\]',
        '',
        content,
    ).strip()

    if not clean_text:
        return []

    return [{"text": clean_text, "metadata": metadata}]


# ── Loader registry ─────────────────────────────────────
LOADERS = {
    ".json": load_json,
    ".txt": load_txt,
    ".md": load_markdown,
}


def load_all_sources(sources_dir: str) -> list[dict]:
    """
    Load all supported files from the sources directory.
    Returns a flat list of Document dicts.
    """
    if not os.path.isdir(sources_dir):
        raise FileNotFoundError(f"Sources directory not found: {sources_dir}")

    documents = []
    supported = set(LOADERS.keys())

    for filename in sorted(os.listdir(sources_dir)):
        ext = Path(filename).suffix.lower()
        if ext not in supported:
            continue

        filepath = os.path.join(sources_dir, filename)
        if not os.path.isfile(filepath):
            continue

        loader = LOADERS[ext]

        try:
            docs = loader(filepath)
            documents.extend(docs)
            print(f"  ✓ Loaded {len(docs)} entries from {filename}")
        except Exception as e:
            print(f"  ✗ Error loading {filename}: {e}")

    if not documents:
        raise ValueError(
            f"No documents found in {sources_dir}. "
            "Add JSON source files (convert TXT first with txt_to_json.py)."
        )

    return documents


def load_from_text(raw_text: str, book_name: str) -> list[dict]:
    """
    Load a document from a raw text string (e.g., pasted in chat).
    """
    clean_text = raw_text.strip()
    if not clean_text:
        return []
    return [{
        "text": clean_text,
        "metadata": {
            "book_name": book_name,
            "chapter": "",
            "section": "",
            "volume": "",
            "page_number": "",
            "source_file": "(pasted text)",
        },
    }]


def load_from_openiti(url: str) -> list[dict]:
    """
    Download and parse a document from an OpenITI raw GitHub URL.
    Returns a list of Document dicts ready for chunking.
    """
    try:
        raw_text = openiti_client.fetch_openiti_text(url)
        return openiti_client.parse_openiti(raw_text, url)
    except Exception as e:
        print(f"  ✗ Failed to load OpenITI source: {e}")
        return []
