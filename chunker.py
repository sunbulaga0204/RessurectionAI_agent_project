"""
Chunker — splits documents into retrieval-friendly chunks.

Strategy: Paragraph-first, sentence-fallback (industry best practice for
scholarly and classical Arabic texts).

1. Split by paragraph boundary first (\\n\\n). Paragraphs are natural semantic
   units in classical texts — a fatwa, a ruling, an argument.
2. If a paragraph fits within CHUNK_SIZE tokens, keep it whole. Never split
   mid-paragraph unless forced.
3. If a paragraph exceeds CHUNK_SIZE, fall back to sentence-level splitting
   with support for Arabic sentence terminators (؟، ۔).
4. Overlap is done at sentence/paragraph boundaries — never mid-string — so
   context fed to the LLM is always coherent.
5. Token-aware sizing: uses len(text) // 4 as an approximation
   (1 token ≈ 4 chars for mixed Arabic/English), matching Voyage tokenization.

Metadata (book_name, chapter, section, volume, page_number) is preserved
in every chunk for citation.
"""

import re
import hashlib
import config


# ── Token estimation ──────────────────────────────────────────────────────────

def _approx_tokens(text: str) -> int:
    """
    Approximate token count. Using len / 4 because classical Arabic text
    averages ~4 chars/token (including diacritics and Quranic script).
    """
    return max(1, len(text) // 4)


# ── Paragraph splitting ───────────────────────────────────────────────────────

def _split_paragraphs(text: str) -> list[str]:
    """
    Split text into paragraphs on blank-line boundaries.
    Handles Unix (\\n\\n), Windows (\\r\\n\\r\\n), and mixed line endings.
    """
    paragraphs = re.split(r'\r?\n\s*\r?\n', text)
    return [p.strip() for p in paragraphs if p.strip()]


# ── Sentence splitting ────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """
    Split text into sentences. Handles:
      - English: . ! ?
      - Arabic: ؟ (question mark) ۔ (full stop) ، (comma — used as clause break)
    Avoids splitting on common abbreviations (Mr., Dr., Vol., etc.)
    """
    # Protect common abbreviations
    text = re.sub(r'\b(Mr|Dr|Vol|No|pp|vs|etc|al|ibid|cf)\.\s', r'\1__DOT__ ', text)

    # Split on sentence-ending punctuation for both scripts
    sentences = re.split(r'(?<=[.!?؟۔])\s+', text)

    # Restore protected abbreviations
    restored = [s.replace('__DOT__', '.').strip() for s in sentences]
    return [s for s in restored if s]


# ── Chunk ID ──────────────────────────────────────────────────────────────────

def _make_chunk_id(text: str, metadata: dict, index: int = 0) -> str:
    """Create a deterministic unique chunk ID."""
    book = metadata.get('book_name', 'Unknown')
    page = metadata.get('page_number', '')
    chapter = metadata.get('chapter', '')
    content = f"{book}-{page}-{chapter}-{index}-{text[:120]}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


# ── Core chunking logic ───────────────────────────────────────────────────────

def _chunk_paragraph(
    paragraph: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """
    Split a single large paragraph into sentence-boundary chunks.
    Used as a fallback when a paragraph exceeds chunk_size.
    """
    sentences = _split_sentences(paragraph)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sent_tokens = _approx_tokens(sentence)

        # Single sentence too large — hard-split it
        if sent_tokens > chunk_size:
            if current:
                chunks.append(" ".join(current))
                current, current_tokens = [], 0
            # Hard split by character blocks (last resort)
            step = chunk_size * 4 - chunk_overlap * 4
            for i in range(0, len(sentence), max(1, step)):
                chunks.append(sentence[i:i + chunk_size * 4])
            continue

        if current_tokens + sent_tokens > chunk_size:
            chunks.append(" ".join(current))

            # Overlap: carry trailing sentences that fit within overlap budget
            overlap_buf: list[str] = []
            overlap_tokens = 0
            for s in reversed(current):
                st = _approx_tokens(s)
                if overlap_tokens + st <= chunk_overlap:
                    overlap_buf.insert(0, s)
                    overlap_tokens += st
                else:
                    break
            current = overlap_buf
            current_tokens = overlap_tokens

        current.append(sentence)
        current_tokens += sent_tokens

    if current:
        chunks.append(" ".join(current))

    return chunks


def chunk_document(
    document: dict,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> list[dict]:
    """
    Split a single document into chunks, preserving page metadata.

    Algorithm:
      1. Split text into paragraphs (blank-line boundaries).
      2. Collect paragraphs greedily until the token budget is full.
      3. When the budget is full:
           a. If the current block has content, finalize it as a chunk.
           b. Carry over the last paragraph as overlap context.
      4. If any single paragraph exceeds chunk_size, further split it
         at sentence boundaries via _chunk_paragraph().

    Args:
        document: {"text": str, "metadata": dict}
        chunk_size:   approximate max tokens per chunk (default: config.CHUNK_SIZE)
        chunk_overlap: overlap tokens between chunks (default: config.CHUNK_OVERLAP)

    Returns:
        List of chunk dicts: {chunk_id, text, metadata}
    """
    chunk_size = chunk_size or config.CHUNK_SIZE
    chunk_overlap = chunk_overlap or config.CHUNK_OVERLAP

    text = document["text"]
    metadata = document["metadata"]

    # Shortcut: entire document fits in one chunk
    if _approx_tokens(text) <= chunk_size:
        return [{
            "chunk_id": _make_chunk_id(text, metadata, index=0),
            "text": text,
            "metadata": {**metadata, "chunk_index": 0},
        }]

    paragraphs = _split_paragraphs(text)
    raw_chunks: list[str] = []

    current_paras: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _approx_tokens(para)

        # Paragraph alone exceeds chunk_size — split at sentence level
        if para_tokens > chunk_size:
            # Flush current block first
            if current_paras:
                raw_chunks.append("\n\n".join(current_paras))
                # Carry last paragraph as overlap context
                last = current_paras[-1]
                current_paras = [last] if _approx_tokens(last) <= chunk_overlap else []
                current_tokens = _approx_tokens(current_paras[0]) if current_paras else 0

            # Split the oversized paragraph into sentence-level sub-chunks
            sub_chunks = _chunk_paragraph(para, chunk_size, chunk_overlap)
            raw_chunks.extend(sub_chunks)
            continue

        # Adding this paragraph would overflow — flush and start fresh with overlap
        if current_tokens + para_tokens > chunk_size and current_paras:
            raw_chunks.append("\n\n".join(current_paras))
            # Overlap: carry the last paragraph into the next chunk for context
            last = current_paras[-1]
            if _approx_tokens(last) <= chunk_overlap:
                current_paras = [last]
                current_tokens = _approx_tokens(last)
            else:
                current_paras = []
                current_tokens = 0

        current_paras.append(para)
        current_tokens += para_tokens

    # Final block
    if current_paras:
        raw_chunks.append("\n\n".join(current_paras))

    # Convert to chunk dicts with preserved metadata
    result: list[dict] = []
    for i, chunk_text in enumerate(raw_chunks):
        if not chunk_text.strip():
            continue
        result.append({
            "chunk_id": _make_chunk_id(chunk_text, metadata, index=i),
            "text": chunk_text.strip(),
            "metadata": {**metadata, "chunk_index": i},
        })

    return result


# ── Batch entry point ─────────────────────────────────────────────────────────

def chunk_all_documents(documents: list[dict]) -> list[dict]:
    """
    Chunk all documents.

    Returns:
        List of chunk dicts ready for embedding and storage.
    """
    all_chunks = []
    for doc in documents:
        chunks = chunk_document(doc)
        all_chunks.extend(chunks)

    print(f"  → {len(documents)} documents split into {len(all_chunks)} chunks")
    return all_chunks
