"""
Vector Store — manages embedding storage and retrieval.
Supports ChromaDB (local) and PostgreSQL (remote/Railway).
Uses Voyage AI (voyage-4-lite) for embeddings.
"""

from __future__ import annotations
import json
import time
import os
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod

import core.config as config

# ── Base Interface ───────────────────────────────────────

class BaseVectorStore(ABC):
    @abstractmethod
    def initialize(self): pass
    
    @abstractmethod
    def is_ingested(self, tenant_id: str) -> bool: pass
    
    @abstractmethod
    def get_existing_ids(self, tenant_id: str) -> List[str]: pass
    
    @abstractmethod
    def ingest(self, tenant_id: str, death_date_ah: str, chunks: List[Dict]): pass
    
    @abstractmethod
    def query(self, tenant_id: str, query_embedding: List[float], death_date_ah: str, top_k: int) -> List[Dict]: pass
    
    @abstractmethod
    def get_source_stats(self, tenant_id: str) -> Dict: pass
    
    @abstractmethod
    def clear(self, tenant_id: str): pass

# ── ChromaDB Implementation ──────────────────────────────

class ChromaStore(BaseVectorStore):
    def __init__(self):
        self.client = None
        
    def initialize(self):
        import chromadb
        if self.client is None:
            self.client = chromadb.PersistentClient(path=config.CHROMA_DIR)
            print(f"  ✓ ChromaDB client initialized at {config.CHROMA_DIR}")

    def _get_collection(self, tenant_id: str):
        self.initialize()
        sanitized = "".join(c if c.isalnum() else "_" for c in tenant_id).strip("_")[:63]
        name = f"tenant_{sanitized}" if len(sanitized) >= 3 else "tenant_sources"
        return self.client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    def is_ingested(self, tenant_id: str) -> bool:
        return self._get_collection(tenant_id).count() > 0

    def get_existing_ids(self, tenant_id: str) -> List[str]:
        coll = self._get_collection(tenant_id)
        all_ids = []
        offset = 0
        while True:
            res = coll.get(limit=10000, offset=offset)
            if not res["ids"]: break
            all_ids.extend(res["ids"])
            offset += 10000
        return all_ids

    def ingest(self, tenant_id: str, death_date_ah: str, chunks: List[Dict]):
        coll = self._get_collection(tenant_id)
        for i in range(0, len(chunks), config.EMBED_BATCH_SIZE):
            batch = chunks[i:i + config.EMBED_BATCH_SIZE]
            texts = [c["text"] for c in batch]
            ids = [c["chunk_id"] for c in batch]
            metas = [c["metadata"] for c in batch]
            for m in metas:
                for k, v in m.items(): m[k] = str(v)
                m["death_date_ah"] = str(death_date_ah)
            
            embeddings = _embed_texts(texts, input_type="document")
            coll.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)
            print(f"  [{min(i + config.EMBED_BATCH_SIZE, len(chunks))}/{len(chunks)}] chunks stored")

    def query(self, tenant_id: str, query_embedding: List[float], death_date_ah: str, top_k: int) -> List[Dict]:
        coll = self._get_collection(tenant_id)
        res = coll.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"death_date_ah": str(death_date_ah)},
            include=["documents", "metadatas", "distances"]
        )
        out = []
        if res and res["documents"]:
            for i in range(len(res["documents"][0])):
                out.append({
                    "text": res["documents"][0][i],
                    "metadata": res["metadatas"][0][i],
                    "distance": res["distances"][0][i]
                })
        return out

    def get_source_stats(self, tenant_id: str) -> Dict:
        coll = self._get_collection(tenant_id)
        res = coll.get(include=["metadatas"])
        if not res["metadatas"]: return {"total_chunks": 0, "books": []}
        books = sorted(list(set(m.get("book_name", "Unknown") for m in res["metadatas"])))
        return {"total_chunks": len(res["metadatas"]), "books": books}

    def clear(self, tenant_id: str):
        self.initialize()
        sanitized = "".join(c if c.isalnum() else "_" for c in tenant_id).strip("_")[:63]
        name = f"tenant_{sanitized}" if len(sanitized) >= 3 else "tenant_sources"
        self.client.delete_collection(name)

# ── PostgreSQL Implementation ────────────────────────────

class PostgresStore(BaseVectorStore):
    def __init__(self):
        self.conn = None
        
    def initialize(self):
        import psycopg2
        from psycopg2.extras import execute_values
        if self.conn is None:
            if not config.DATABASE_URL:
                raise ValueError("DATABASE_URL is not set for PostgresStore")
            self.conn = psycopg2.connect(config.DATABASE_URL)
            self.conn.autocommit = True
            with self.conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS document_chunks (
                        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                        tenant_id text NOT NULL,
                        chunk_id text UNIQUE NOT NULL,
                        death_date_ah text,
                        content text NOT NULL,
                        metadata jsonb,
                        embedding vector(1024)
                    );
                    CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON document_chunks(tenant_id, death_date_ah);
                    -- HNSW index for lightning fast vector search
                    CREATE INDEX IF NOT EXISTS idx_chunks_vector ON document_chunks USING hnsw (embedding vector_cosine_ops);
                """)
            print("  ✓ PostgreSQL client initialized (HNSW Index enabled)")

    def is_ingested(self, tenant_id: str) -> bool:
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM document_chunks WHERE tenant_id = %s", (tenant_id,))
            return cur.fetchone()[0] > 0

    def get_existing_ids(self, tenant_id: str) -> List[str]:
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("SELECT chunk_id FROM document_chunks WHERE tenant_id = %s", (tenant_id,))
            return [row[0] for row in cur.fetchall()]

    def ingest(self, tenant_id: str, death_date_ah: str, chunks: List[Dict]):
        self.initialize()
        from psycopg2.extras import execute_values
        for i in range(0, len(chunks), config.EMBED_BATCH_SIZE):
            batch = chunks[i:i + config.EMBED_BATCH_SIZE]
            texts = [c["text"] for c in batch]
            ids = [c["chunk_id"] for c in batch]
            metas = [c["metadata"] for c in batch]
            embeddings = _embed_texts(texts, input_type="document")
            
            data = []
            for j in range(len(batch)):
                data.append((tenant_id, ids[j], str(death_date_ah), texts[j], json.dumps(metas[j]), embeddings[j]))
            
            with self.conn.cursor() as cur:
                execute_values(cur, """
                    INSERT INTO document_chunks (tenant_id, chunk_id, death_date_ah, content, metadata, embedding)
                    VALUES %s
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding
                """, data)
            print(f"  [{min(i + config.EMBED_BATCH_SIZE, len(chunks))}/{len(chunks)}] chunks stored in Postgres")

    def query(self, tenant_id: str, query_embedding: List[float], death_date_ah: str, top_k: int) -> List[Dict]:
        self.initialize()
        
        # Convert embedding to a string format that Postgres pgvector natively accepts "[0.1, 0.2, ...]"
        # This completely avoids any psycopg2 list/numpy adaptation errors.
        if hasattr(query_embedding, "tolist"):
            query_embedding = query_embedding.tolist()
        emb_str = str(list(query_embedding))
        
        with self.conn.cursor() as cur:
            # Using <=> for cosine distance
            cur.execute("""
                SELECT content, metadata, (embedding <=> %s::vector) as dist
                FROM document_chunks
                WHERE tenant_id = %s AND death_date_ah = %s
                ORDER BY dist
                LIMIT %s
            """, (emb_str, tenant_id, str(death_date_ah), top_k))
            
            out = []
            for row in cur.fetchall():
                out.append({"text": row[0], "metadata": row[1], "distance": row[2]})
            return out

    def get_source_stats(self, tenant_id: str) -> Dict:
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT count(*), array_agg(DISTINCT (metadata->>'book_name'))
                FROM document_chunks WHERE tenant_id = %s
            """, (tenant_id,))
            row = cur.fetchone()
            return {"total_chunks": row[0], "books": sorted(row[1]) if row[1] and row[1][0] else []}

    def clear(self, tenant_id: str):
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM document_chunks WHERE tenant_id = %s", (tenant_id,))

# ── Module Level State ───────────────────────────────────

_store: Optional[BaseVectorStore] = None
_voyage_client = None

def _get_store() -> BaseVectorStore:
    global _store
    if _store is None:
        if config.VECTOR_STORE_TYPE == "postgres":
            _store = PostgresStore()
        else:
            _store = ChromaStore()
    return _store

def _get_voyage_client():
    global _voyage_client
    if _voyage_client is None:
        import voyageai
        _voyage_client = voyageai.Client(api_key=config.VOYAGE_API_KEY)
    return _voyage_client

def _embed_texts(texts: List[str], input_type: str = "document") -> List[List[float]]:
    client = _get_voyage_client()
    res = client.embed(
        texts,
        model=config.EMBEDDING_MODEL,
        input_type=input_type,
        output_dimension=config.VOYAGE_OUTPUT_DIMENSION
    )
    return res.embeddings

# ── Public API ───────────────────────────────────────────

def initialize(): _get_store().initialize()
def is_ingested(tenant_id: str) -> bool: return _get_store().is_ingested(tenant_id)
def get_existing_ids(tenant_id: str) -> List[str]: return _get_store().get_existing_ids(tenant_id)
def ingest(tenant_id: str, death_date_ah: str, chunks: List[Dict]): _get_store().ingest(tenant_id, death_date_ah, chunks)
def clear(tenant_id: str): _get_store().clear(tenant_id)
def get_source_stats(tenant_id: str) -> Dict: return _get_store().get_source_stats(tenant_id)

def query(tenant_id: str, text: str, death_date_ah: str, top_k: int = None) -> List[Dict]:
    top_k = top_k or config.TOP_K
    emb = _embed_texts([text], input_type="query")[0]
    return _get_store().query(tenant_id, emb, death_date_ah, top_k)

def query_multilayer(tenant_id: str, text: str, death_date_ah: str, top_k: int = None, distance_threshold: float = 0.65) -> List[Dict]:
    # Multilayer logic remains the same, just calls query() as the engine
    top_k = top_k or config.TOP_K
    
    def _fetch(query_text: str, n: int) -> List[Dict]:
        emb = _embed_texts([query_text], input_type="query")[0]
        return _get_store().query(tenant_id, emb, death_date_ah, n)

    # Broad Fetch
    candidates = _fetch(text, min(top_k * 3, 30))

    # Sub-query Expansion
    words = text.split()
    if len(text) > 80 and len(words) >= 6:
        mid = len(words) // 2
        for sub in [" ".join(words[:mid]), " ".join(words[mid:])]:
            candidates.extend(_fetch(sub, top_k))

    # Deduplicate + Round Robin Diversity
    seen = set()
    unique = []
    for c in candidates:
        tid = c["text"][:100]
        if tid not in seen:
            seen.add(tid)
            unique.append(c)

    by_book = {}
    for c in unique:
        b = c["metadata"].get("book_name", "Unknown")
        by_book.setdefault(b, []).append(c)
    
    balanced = []
    for b in by_book:
        by_book[b].sort(key=lambda x: x["distance"])
        balanced.extend(by_book[b][:3])
    
    balanced.sort(key=lambda x: x["distance"])
    filtered = [c for c in balanced if c["distance"] <= distance_threshold]
    
    if len(filtered) < top_k:
        unique.sort(key=lambda x: x["distance"])
        seen_txt = set(c["text"][:100] for c in filtered)
        for c in unique:
            if len(filtered) >= top_k: break
            if c["text"][:100] not in seen_txt:
                filtered.append(c)
                seen_txt.add(c["text"][:100])

    filtered.sort(key=lambda c: c["distance"])
    return filtered[:top_k]
