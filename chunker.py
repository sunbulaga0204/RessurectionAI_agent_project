"""
Chunker — splits documents into retrieval-friendly chunks
using sentence-aware splitting with configurable size and overlap.
Preserves page_number metadata through each chunk for citation.
"""

import re
import hashlib
import config


def _split_sentences(text: str) -> list[str]:
    """
    Split text into sentences. Handles English periods, Arabic full stops,
    and common abbreviations.
    """
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def _make_chunk_id(text: str, metadata: dict, index: int = 0) -> str:
    """Create a deterministic unique chunk ID."""
    book = metadata.get('book_name', 'Unknown')
    page = metadata.get('page_number', '')
    chapter = metadata.get('chapter', '')
    content = f"{book}-{page}-{chapter}-{index}-{text}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def chunk_document(document: dict, chunk_size: int = None, chunk_overlap: int = None) -> list[dict]:
    """
    Split a single document into chunks, preserving page metadata.

    Args:
        document: {"text": str, "metadata": dict}
        chunk_size: max characters per chunk (default from config)
        chunk_overlap: overlap characters between chunks (default from config)

    Returns:
        List of chunk dicts with text, metadata (including page_number), and chunk_id.
    """
    chunk_size = chunk_size or config.CHUNK_SIZE
    chunk_overlap = chunk_overlap or config.CHUNK_OVERLAP

    text = document["text"]
    metadata = document["metadata"]

    if len(text) <= chunk_size:
        return [{
            "chunk_id": _make_chunk_id(text, metadata, index=0),
            "text": text,
            "metadata": {**metadata, "chunk_index": 0},
        }]

    sentences = _split_sentences(text)
    chunks = []
    current_chunk_sentences = []
    current_length = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        # If a single sentence exceeds chunk_size, hard-split it
        if sentence_len > chunk_size:
            if current_chunk_sentences:
                chunk_text = " ".join(current_chunk_sentences)
                chunks.append(chunk_text)
                current_chunk_sentences = []
                current_length = 0

            for i in range(0, sentence_len, chunk_size - chunk_overlap):
                chunks.append(sentence[i:i + chunk_size])
            continue

        # Check if adding this sentence exceeds the limit
        if current_length + sentence_len + 1 > chunk_size:
            chunk_text = " ".join(current_chunk_sentences)
            chunks.append(chunk_text)

            # Calculate overlap: keep trailing sentences that fit
            overlap_sentences = []
            overlap_length = 0
            for s in reversed(current_chunk_sentences):
                if overlap_length + len(s) + 1 <= chunk_overlap:
                    overlap_sentences.insert(0, s)
                    overlap_length += len(s) + 1
                else:
                    break

            current_chunk_sentences = overlap_sentences
            current_length = overlap_length

        current_chunk_sentences.append(sentence)
        current_length += sentence_len + 1

    # Last chunk
    if current_chunk_sentences:
        chunk_text = " ".join(current_chunk_sentences)
        chunks.append(chunk_text)

    # Convert to chunk dicts with metadata (page_number preserved)
    result = []
    for i, chunk_text in enumerate(chunks):
        result.append({
            "chunk_id": _make_chunk_id(chunk_text, metadata, index=i),
            "text": chunk_text,
            "metadata": {**metadata, "chunk_index": i},
        })

    return result


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
