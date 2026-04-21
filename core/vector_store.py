"""
Vector Store — manages ChromaDB for embedding storage and retrieval.
Uses Voyage AI (voyage-4-lite) for embeddings.

Refactored for Multi-Tenant SaaS Architecture:
Each persona relies on their specific tenant_id to create isolated collections.
Queries are additionally locked by death_date_ah (Anno Hegirae) to ensure accuracy.
"""

from __future__ import annotations

import json
import time
from typing import Optional

import chromadb
import voyageai

import core.config as config


# ── Module-level state ───────────────────────────────────
_client: Optional[chromadb.PersistentClient] = None
_voyage_client: Optional[voyageai.Client] = None


def _get_collection_name(tenant_id: str) -> str:
    """Sanitize tenant_id for ChromaDB collection naming."""
    sanitized = "".join(c if c.isalnum() else "_" for c in tenant_id)
    sanitized = sanitized.strip("_")[:63]
    if len(sanitized) < 3:
        sanitized = "tenant_sources"
    return f"tenant_{sanitized}"


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
    """Load the persistent ChromaDB client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=config.CHROMA_DIR)
        print(f"  ✓ ChromaDB client initialized at {config.CHROMA_DIR}")


def _get_collection(tenant_id: str) -> chromadb.Collection:
    """Get or create the collection for a specific tenant."""
    initialize()
    collection_name = _get_collection_name(tenant_id)
    return _client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def is_ingested(tenant_id: str) -> bool:
    """Check if the tenant collection already has data."""
    coll = _get_collection(tenant_id)
    return coll.count() > 0


def get_existing_ids(tenant_id: str) -> list[str]:
    """Return all chunk IDs currently stored for a tenant."""
    coll = _get_collection(tenant_id)
    all_ids = []
    batch_size = 10000
    offset = 0

    while True:
        results = coll.get(limit=batch_size, offset=offset)
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


def ingest(tenant_id: str, death_date_ah: str, chunks: list[dict]):
    """
    Embed and store source chunks in ChromaDB for a specific tenant.
    Attaches death_date_ah to ensure chronological accuracy locking.
    """
    coll = _get_collection(tenant_id)

    total = len(chunks)
    batch_size = config.EMBED_BATCH_SIZE
    delay = config.EMBED_DELAY_SECONDS

    print(f"\n📥 Ingesting {total} chunks for '{tenant_id}' (batch={batch_size})...")

    for i in range(0, total, batch_size):
        batch = chunks[i:i + batch_size]
        batch_texts = [c["text"] for c in batch]
        batch_ids = [c["chunk_id"] for c in batch]
        batch_metadatas = [c["metadata"] for c in batch]

        # Convert metadata values to strings and inject death date lock
        for meta in batch_metadatas:
            for key, value in meta.items():
                meta[key] = str(value)
            meta["death_date_ah"] = str(death_date_ah)

        try:
            embeddings = _embed_texts(batch_texts, input_type="document")
            coll.upsert(
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
                coll.upsert(
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

    print(f"\n✅ Ingestion complete. Collection '{tenant_id}' has {coll.count()} documents.")


def query(tenant_id: str, text: str, death_date_ah: str, top_k: int = None) -> list[dict]:
    """
    Layer 1: Embed the query and perform similarity search on a specific tenant.
    Filters exclusively by death_date_ah to lock chronological accuracy.
    """
    coll = _get_collection(tenant_id)
    top_k = top_k or config.TOP_K

    query_embedding = _embed_texts([text], input_type="query")[0]

    results = coll.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"death_date_ah": str(death_date_ah)},
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


def query_multilayer(
    tenant_id: str,
    text: str,
    death_date_ah: str,
    top_k: int = None,
    distance_threshold: float = 0.65,
) -> list[dict]:
    """
    Multi-layer retrieval pipeline for long, complex, or highly specific queries.

    Layer 1 — Broad Fetch:
      Retrieves 3x top_k candidates to cast a wide semantic net.

    Layer 2 — Distance Re-ranking:
      Drops chunks whose cosine distance exceeds `distance_threshold`
      (Voyage cosine distances: 0.0 = perfect, 1.0 = orthogonal).
      Keeps the top_k closest after filtering.

    Layer 3 — Sub-query Expansion:
      If the query is long (>80 chars), splits it into two sub-queries:
      the first half and the second half. Each sub-query is run independently
      and results are merged & deduplicated by chunk_id. This handles cases
      where a complex multi-part question has components that map to different
      source regions.

    Returns deduplicated, re-ranked chunks sorted by ascending distance.
    """
    top_k = top_k or config.TOP_K
    coll = _get_collection(tenant_id)

    def _fetch(query_text: str, n: int) -> list[dict]:
        emb = _embed_texts([query_text], input_type="query")[0]
        results = coll.query(
            query_embeddings=[emb],
            n_results=n,
            where={"death_date_ah": str(death_date_ah)},
            include=["documents", "metadatas", "distances"],
        )
        out = []
        if results and results["documents"]:
            for i in range(len(results["documents"][0])):
                out.append({
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                })
        return out

    # ── Layer 1: Broad Fetch ──────────────────────────────────────
    broad_n = min(top_k * 3, 30)  # cap at 30 to avoid token overload
    candidates = _fetch(text, broad_n)

    # ── Layer 3: Sub-query Expansion for complex queries ──────────
    words = text.split()
    if len(text) > 80 and len(words) >= 6:
        mid = len(words) // 2
        sub_a = " ".join(words[:mid])
        sub_b = " ".join(words[mid:])
        for sub in [sub_a, sub_b]:
            sub_chunks = _fetch(sub, top_k)
            candidates.extend(sub_chunks)

    # ── Layer 2: Deduplicate + Distance Filter + Re-rank ──────────
    seen_ids: set[str] = set()
    unique: list[dict] = []
    for chunk in candidates:
        cid = chunk.get("metadata", {}).get("chunk_index", "") + chunk["text"][:60]
        if cid not in seen_ids:
            seen_ids.add(cid)
            unique.append(chunk)

    # Filter by distance threshold, then sort ascending (closest first)
    filtered = [c for c in unique if c["distance"] <= distance_threshold]
    filtered.sort(key=lambda c: c["distance"])

    # If threshold filtered everything, fall back to top_k of raw unique
    if not filtered:
        unique.sort(key=lambda c: c["distance"])
        filtered = unique

    return filtered[:top_k]

def get_source_stats(tenant_id: str) -> dict:
    """Get statistics about all ingested sources for a tenant."""
    coll = _get_collection(tenant_id)

    all_metadatas = []
    batch_size = 10000
    offset = 0

    while True:
        results = coll.get(
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


def clear(tenant_id: str):
    """Delete ALL data from a tenant's collection."""
    global _client
    if _client is not None:
        collection_name = _get_collection_name(tenant_id)
        _client.delete_collection(collection_name)
        print(f"  ✓ Collection '{collection_name}' cleared")
