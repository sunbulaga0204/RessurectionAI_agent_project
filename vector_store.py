"""
Vector Store — manages ChromaDB for embedding storage and retrieval.
Uses Voyage AI (voyage-3.5-lite) for embeddings.

Key advantages over the previous Gemini embedding setup:
  - input_type="document" vs "query" distinction improves retrieval accuracy
  - 32,000-token context window handles long classical text passages
  - 5x cheaper than Google text-embedding at $0.02/1M tokens
  - 200M free tokens for new Voyage accounts
  - Supports MRL: flexible output dimensions (256 / 512 / 1024 / 2048)

Collection name is derived from persona for multi-persona support.
"""

from __future__ import annotations

import json
import time
from typing import Optional

import chromadb
import voyageai

import config


# ── Module-level state ───────────────────────────────────
_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[chromadb.Collection] = None
_voyage_client: Optional[voyageai.Client] = None


def _get_collection_name() -> str:
    """Derive collection name from persona file for multi-persona support."""
    try:
        with open(config.PERSONA_FILE, 'r', encoding='utf-8') as f:
            persona = json.load(f)
        name = persona.get("name_display", persona.get("name", "persona"))
        # Sanitize for ChromaDB (alphanumeric + underscores, 3-63 chars)
        sanitized = "".join(c if c.isalnum() else "_" for c in name)
        sanitized = sanitized.strip("_")[:63]
        if len(sanitized) < 3:
            sanitized = "persona_sources"
        return sanitized
    except Exception:
        return "persona_sources"


def _get_voyage_client() -> voyageai.Client:
    """Lazy-initialize the Voyage AI client."""
    global _voyage_client
    if _voyage_client is None:
        if not config.VOYAGE_API_KEY:
            raise ValueError(
                "VOYAGE_API_KEY is not set. "
                "Add it to your .env file. Get a free key at https://www.voyageai.com"
            )
        _voyage_client = voyageai.Client(api_key=config.VOYAGE_API_KEY)
    return _voyage_client


def initialize():
    """Create or load the persistent ChromaDB collection."""
    global _client, _collection

    _client = chromadb.PersistentClient(path=config.CHROMA_DIR)
    collection_name = _get_collection_name()
    _collection = _client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"  ✓ ChromaDB initialized at {config.CHROMA_DIR}")
    print(f"    Collection '{collection_name}' has {_collection.count()} documents")


def is_ingested() -> bool:
    """Check if the collection already has data."""
    if _collection is None:
        initialize()
    return _collection.count() > 0


def get_existing_ids() -> list[str]:
    """Return all chunk IDs currently stored (batched for large collections)."""
    if _collection is None:
        initialize()

    all_ids = []
    batch_size = 10000
    offset = 0

    while True:
        results = _collection.get(limit=batch_size, offset=offset)
        batch_ids = results["ids"]
        if not batch_ids:
            break
        all_ids.extend(batch_ids)
        offset += batch_size

    return all_ids


def _embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """
    Embed a batch of texts using Voyage AI.

    Args:
        texts: List of text strings to embed.
        input_type: "document" during ingestion, "query" during retrieval.
                    Voyage prepends task-specific prompts based on this, which
                    significantly improves retrieval accuracy.
    """
    client = _get_voyage_client()
    result = client.embed(
        texts,
        model=config.EMBEDDING_MODEL,
        input_type=input_type,
        output_dimension=config.VOYAGE_OUTPUT_DIMENSION,
    )
    return result.embeddings


def ingest(chunks: list[dict]):
    """
    Embed and store source chunks in ChromaDB.
    Voyage supports batches of up to 128 texts and imposes no artificial rate limit.
    """
    if _collection is None:
        initialize()

    total = len(chunks)
    batch_size = config.EMBED_BATCH_SIZE
    delay = config.EMBED_DELAY_SECONDS

    print(f"\n📥 Ingesting {total} chunks (batch={batch_size})...")

    for i in range(0, total, batch_size):
        batch = chunks[i:i + batch_size]
        batch_texts = [c["text"] for c in batch]
        batch_ids = [c["chunk_id"] for c in batch]
        batch_metadatas = [c["metadata"] for c in batch]

        # Convert metadata values to strings (ChromaDB requirement)
        for meta in batch_metadatas:
            for key, value in meta.items():
                meta[key] = str(value)

        try:
            # Use input_type="document" so Voyage optimizes for passage retrieval
            embeddings = _embed_texts(batch_texts, input_type="document")

            _collection.upsert(
                ids=batch_ids,
                embeddings=embeddings,
                documents=batch_texts,
                metadatas=batch_metadatas,
            )

            progress = min(i + batch_size, total)
            print(f"  [{progress}/{total}] chunks embedded and stored")

        except Exception as e:
            print(f"  ✗ Error at batch {i // batch_size + 1}: {e}")
            wait = max(delay * 2, 5)
            print(f"    Retrying after {wait}s...")
            time.sleep(wait)
            try:
                embeddings = _embed_texts(batch_texts, input_type="document")
                _collection.upsert(
                    ids=batch_ids,
                    embeddings=embeddings,
                    documents=batch_texts,
                    metadatas=batch_metadatas,
                )
                progress = min(i + batch_size, total)
                print(f"  [{progress}/{total}] chunks embedded (retry succeeded)")
            except Exception as retry_err:
                print(f"  ✗ Retry failed: {retry_err}. Skipping batch.")

        if delay > 0 and i + batch_size < total:
            time.sleep(delay)

    print(f"\n✅ Ingestion complete. Collection has {_collection.count()} documents.")


def query(text: str, top_k: int = None) -> list[dict]:
    """
    Embed the query and perform similarity search.

    Uses input_type="query" so Voyage prepends a search-query-specific prompt,
    which is tuned to find relevant document passages — distinct from "document"
    embeddings created during ingestion.

    Returns:
        List of dicts with: text, metadata (including page_number), distance
    """
    if _collection is None:
        initialize()

    top_k = top_k or config.TOP_K

    # Embed with query-specific prompt type for better retrieval accuracy
    query_embedding = _embed_texts([text], input_type="query")[0]

    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    if results and results["documents"]:
        for i in range(len(results["documents"][0])):
            chunks.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })

    return chunks


def get_source_stats() -> dict:
    """Get statistics about all ingested sources."""
    if _collection is None:
        initialize()

    all_metadatas = []
    batch_size = 10000
    offset = 0

    while True:
        results = _collection.get(
            include=["metadatas"],
            limit=batch_size,
            offset=offset,
        )
        batch_metas = results["metadatas"]
        if not batch_metas:
            break
        all_metadatas.extend(batch_metas)
        offset += batch_size

    count = len(all_metadatas)
    if count == 0:
        return {"total_chunks": 0, "books": []}

    books = set()
    for meta in all_metadatas:
        books.add(meta.get("book_name", "Unknown"))

    return {
        "total_chunks": count,
        "books": sorted(books),
    }


def clear():
    """Delete ALL data from the collection."""
    global _collection
    if _client is not None:
        collection_name = _get_collection_name()
        _client.delete_collection(collection_name)
        _collection = _client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        print("  ✓ Collection cleared")
