"""
Vector Store — manages embedding storage and retrieval.
Supports ChromaDB (local) and PostgreSQL (remote/Railway).
Uses Voyage AI (voyage-3-lite or voyage-4-lite) for embeddings.
"""

from __future__ import annotations
import json
import time
import os
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod

import core.config as config

# =========================================================================
# ── Base Interface ───────────────────────────────────────────────────────
# =========================================================================

class BaseVectorStore(ABC):
    """
    Abstract Base Class outlining standard vector storage capability.
    Enforces a consistent API for both local and high-performance databases.
    """
    @abstractmethod
    def initialize(self): 
        """Establish connections and bootstrap collection/table layouts."""
        pass
    
    @abstractmethod
    def is_ingested(self, tenant_id: str) -> bool: 
        """Return True if the tenant's namespace contains ingested documents."""
        pass
    
    @abstractmethod
    def get_existing_ids(self, tenant_id: str) -> List[str]: 
        """Retrieve all chunk IDs currently stored for a specific tenant."""
        pass
    
    @abstractmethod
    def ingest(self, tenant_id: str, death_date_ah: str, chunks: List[Dict]): 
        """Generate embeddings and persist documents for a tenant."""
        pass
    
    @abstractmethod
    def query(self, tenant_id: str, query_embedding: List[float], death_date_ah: str, top_k: int) -> List[Dict]: 
        """Query vector database for similar content matching target embedding."""
        pass
    
    @abstractmethod
    def get_source_stats(self, tenant_id: str) -> Dict: 
        """Return statistical breakdown of ingested source texts (e.g. books)."""
        pass
    
    @abstractmethod
    def clear(self, tenant_id: str): 
        """Delete all document collections/chunks mapped to a tenant."""
        pass


# =========================================================================
# ── ChromaDB Implementation ──────────────────────────────────────────────
# =========================================================================

class ChromaStore(BaseVectorStore):
    """
    Local-first Persistent ChromaDB Vector Store.
    Ideal for local development, tests, and static server environments.
    """
    def __init__(self):
        self.client = None
        
    def initialize(self):
        """Lazy-boots Persistent Chroma client using directory settings."""
        import chromadb
        if self.client is None:
            self.client = chromadb.PersistentClient(path=config.CHROMA_DIR)
            print(f"  ✓ ChromaDB client initialized at {config.CHROMA_DIR}")

    def _get_collection(self, tenant_id: str):
        """Sanitizes tenant identifiers and returns a standard cosine-spaced collection."""
        self.initialize()
        sanitized = "".join(c if c.isalnum() else "_" for c in tenant_id).strip("_")[:63]
        name = f"tenant_{sanitized}" if len(sanitized) >= 3 else "tenant_sources"
        return self.client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    def is_ingested(self, tenant_id: str) -> bool:
        """Return True if collection counts match > 0."""
        return self._get_collection(tenant_id).count() > 0

    def get_existing_ids(self, tenant_id: str) -> List[str]:
        """Fetch all primary document chunk keys from active collection."""
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
        """
        Processes lists of document chunks, converts texts to Voyage AI embeddings
        in batches, and saves them directly to local storage.
        """
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
        """Perform semantic nearest neighbor retrieval filtered by death_date_ah."""
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
        """Returns document counts and unique book counts inside database."""
        coll = self._get_collection(tenant_id)
        res = coll.get(include=["metadatas"])
        if not res["metadatas"]: return {"total_chunks": 0, "books": []}
        books = sorted(list(set(m.get("book_name", "Unknown") for m in res["metadatas"])))
        return {"total_chunks": len(res["metadatas"]), "books": books}

    def clear(self, tenant_id: str):
        """Purge and delete collection entirely."""
        self.initialize()
        sanitized = "".join(c if c.isalnum() else "_" for c in tenant_id).strip("_")[:63]
        name = f"tenant_{sanitized}" if len(sanitized) >= 3 else "tenant_sources"
        self.client.delete_collection(name)


# =========================================================================
# ── PostgreSQL + pgvector Implementation ──────────────────────────────────
# =========================================================================

class PostgresStore(BaseVectorStore):
    """
    SaaS Cloud Vector Database.
    Utilizes PostgreSQL pgvector with HNSW Index mappings for production scaling.
    Also serves as persistent datastore for time-aware Telegram bot subscriber states.
    """
    def __init__(self):
        self.conn = None
        
    def initialize(self):
        """Establishes database connections, validates vector extensions, and builds schemas."""
        import psycopg2
        from psycopg2.extras import execute_values
        
        # Check if connection is active or disconnected
        is_closed = self.conn is None or self.conn.closed != 0
        
        if is_closed:
            if not config.DATABASE_URL:
                raise ValueError("DATABASE_URL is not set for PostgresStore")
            
            if self.conn is not None:
                print("  ⚠ PostgreSQL connection lost. Reconnecting...")
                
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
                    CREATE TABLE IF NOT EXISTS telegram_users (
                        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                        tenant_id text NOT NULL,
                        chat_id text NOT NULL,
                        is_subscribed boolean DEFAULT FALSE,
                        preferred_language text DEFAULT 'EN',
                        timezone_offset integer DEFAULT 7,
                        last_seen timestamp DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tenant_id, chat_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON document_chunks(tenant_id, death_date_ah);
                    CREATE INDEX IF NOT EXISTS idx_chunks_vector ON document_chunks USING hnsw (embedding vector_cosine_ops);
                """)
            print("  ✓ PostgreSQL client initialized (HNSW Index enabled)")

    def is_ingested(self, tenant_id: str) -> bool:
        """Determines if the document database has active listings for tenant."""
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM document_chunks WHERE tenant_id = %s", (tenant_id,))
            return cur.fetchone()[0] > 0

    def get_existing_ids(self, tenant_id: str) -> List[str]:
        """Fetches active chunk primary keys."""
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("SELECT chunk_id FROM document_chunks WHERE tenant_id = %s", (tenant_id,))
            return [row[0] for row in cur.fetchall()]

    def ingest(self, tenant_id: str, death_date_ah: str, chunks: List[Dict]):
        """Generates and batch-inserts document contents and high-dim vectors into Postgres."""
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
        """
        Executes highly efficient cosine similarity query using pgvector index operators.
        Coerces lists into formatted vector strings to bypass adapter mismatch exceptions.
        """
        self.initialize()
        
        # Standardize vector representations natively to bypass psycopg2 numpy conversion bugs
        if hasattr(query_embedding, "tolist"):
            query_embedding = query_embedding.tolist()
        emb_str = str(list(query_embedding))
        
        with self.conn.cursor() as cur:
            # <=> stands for Cosine Distance in pgvector syntax
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
        """Retrieves data statistics (total chunk volumes and distinct ingested book lists)."""
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM document_chunks WHERE tenant_id = %s", (tenant_id,))
            total = cur.fetchone()[0]
            cur.execute("SELECT DISTINCT (metadata->>'book_name') FROM document_chunks WHERE tenant_id = %s", (tenant_id,))
            books = [row[0] for row in cur.fetchall() if row[0]]
            return {"total_chunks": total, "books": sorted(books)}

    def register_user(self, tenant_id: str, chat_id: str, language: str = 'EN', timezone: int = 7):
        """Save/update chat ID and timezone variables for motivation delivery scheduler."""
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO telegram_users (tenant_id, chat_id, preferred_language, timezone_offset, last_seen)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id, chat_id) DO UPDATE SET 
                    last_seen = CURRENT_TIMESTAMP,
                    preferred_language = %s
            """, (tenant_id, chat_id, language, timezone, language))

    def get_subscribed_users_for_hour(self, tenant_id: str, current_hour_utc: int) -> List[Dict]:
        """
        Locates active subscribers whose calculated local time sits exactly at 08:00 AM.
        Formula: (UTC Hour + Timezone Offset) % 24 == 8
        """
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT chat_id, preferred_language 
                FROM telegram_users 
                WHERE tenant_id = %s 
                  AND is_subscribed = TRUE 
                  AND ((%s + timezone_offset) %% 24) = 8
            """, (tenant_id, current_hour_utc))
            return [{"chat_id": row[0], "lang": row[1]} for row in cur.fetchall()]

    def toggle_subscription(self, tenant_id: str, chat_id: str, status: bool):
        """Flips subscription triggers to allow user opt-ins/opt-outs."""
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE telegram_users SET is_subscribed = %s 
                WHERE tenant_id = %s AND chat_id = %s
            """, (status, tenant_id, chat_id))

    def get_subscribed_users(self, tenant_id: str) -> List[str]:
        """Returns all active subscribers."""
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM telegram_users WHERE tenant_id = %s AND is_subscribed = TRUE", (tenant_id,))
            return [row[0] for row in cur.fetchall()]

    def get_all_users(self, tenant_id: str) -> List[str]:
        """Returns entire list of chat ID nodes."""
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM telegram_users WHERE tenant_id = %s", (tenant_id,))
            return [row[0] for row in cur.fetchall()]

    def clear(self, tenant_id: str):
        """Wipes document chunks cleanly."""
        self.initialize()
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM document_chunks WHERE tenant_id = %s", (tenant_id,))


# =========================================================================
# ── Module Level Caches & Core Embedder ──────────────────────────────────
# =========================================================================

_store: Optional[BaseVectorStore] = None
_voyage_client = None

def _get_store() -> BaseVectorStore:
    """Instantiates singleton client cache matching database configurations."""
    global _store
    if _store is None:
        if config.VECTOR_STORE_TYPE == "postgres":
            _store = PostgresStore()
        else:
            _store = ChromaStore()
    return _store

def _get_voyage_client():
    """Lazy boots voyage client using official client packages."""
    global _voyage_client
    if _voyage_client is None:
        import voyageai
        _voyage_client = voyageai.Client(api_key=config.VOYAGE_API_KEY)
    return _voyage_client

def _embed_texts(texts: List[str], input_type: str = "document") -> List[List[float]]:
    """Calculates vector embeddings using the configured Voyage AI model endpoints."""
    client = _get_voyage_client()
    res = client.embed(
        texts,
        model=config.EMBEDDING_MODEL,
        input_type=input_type
    )
    return res.embeddings


# =========================================================================
# ── Public RAG Interfaces ────────────────────────────────────────────────
# =========================================================================

def initialize(): 
    """Pre-heats connections."""
    _get_store().initialize()

def is_ingested(tenant_id: str) -> bool: 
    """Telemetry indicator showing database status."""
    return _get_store().is_ingested(tenant_id)

def get_existing_ids(tenant_id: str) -> List[str]: 
    """Retrieves all ingested primary key keys."""
    return _get_store().get_existing_ids(tenant_id)

def ingest(tenant_id: str, death_date_ah: str, chunks: List[Dict]): 
    """Main ingestion coordinator."""
    _get_store().ingest(tenant_id, death_date_ah, chunks)

def clear(tenant_id: str): 
    """Clear tenant data."""
    _get_store().clear(tenant_id)

def get_source_stats(tenant_id: str) -> Dict: 
    """Retrieve database metrics."""
    return _get_store().get_source_stats(tenant_id)

def register_user(tenant_id: str, chat_id: str, language: str = 'EN', timezone: int = 7): 
    """Saves user session variables for scheduler operations."""
    _get_store().register_user(tenant_id, chat_id, language, timezone)

def toggle_subscription(tenant_id: str, chat_id: str, status: bool): 
    """Manages subscription opt-out states."""
    _get_store().toggle_subscription(tenant_id, chat_id, status)

def get_subscribed_users_for_hour(tenant_id: str, current_hour_utc: int) -> List[Dict]: 
    """Locates active local users matching timezone parameters."""
    return _get_store().get_subscribed_users_for_hour(tenant_id, current_hour_utc)

def get_all_users(tenant_id: str) -> List[str]: 
    """Telemetry lookup lists."""
    return _get_store().get_all_users(tenant_id)

def query(tenant_id: str, text: str, death_date_ah: str, top_k: int = None) -> List[Dict]:
    """
    Standard Semantic Search.
    Embeds search query text and retrieves top matching documents.
    """
    top_k = top_k or config.TOP_K
    emb = _embed_texts([text], input_type="query")[0]
    return _get_store().query(tenant_id, emb, death_date_ah, top_k)

def query_multilayer(tenant_id: str, text: str, death_date_ah: str, top_k: int = None, distance_threshold: float = 0.65) -> List[Dict]:
    """
    Advanced Multi-Layer/Hybrid Semantic Search.
    Implemented to handle multi-sentence historical queries and keyword terms.

    Flow:
      1. Broad fetch retrieval based on main embedding query.
      2. Query splitting/Expansion (sub-query generation on segment blocks).
      3. Global candidate de-duplication.
      4. Balanced round-robin diversity filtering (mitigating single book biases).
      5. Strict semantic distance threshold pruning.
    """
    top_k = top_k or config.TOP_K
    
    def _fetch(query_text: str, n: int) -> List[Dict]:
        emb = _embed_texts([query_text], input_type="query")[0]
        return _get_store().query(tenant_id, emb, death_date_ah, n)

    # 1. Broad Retrieval Phase
    candidates = _fetch(text, min(top_k * 3, 30))

    # 2. Sub-query Expansion Phase
    # Breaks long complex inquiries down to extract distinct contextual aspects
    words = text.split()
    if len(text) > 80 and len(words) >= 6:
        mid = len(words) // 2
        for sub in [" ".join(words[:mid]), " ".join(words[mid:])]:
            candidates.extend(_fetch(sub, top_k))

    # 3. Deduplication Phase
    seen = set()
    unique = []
    for c in candidates:
        tid = c["text"][:100]
        if tid not in seen:
            seen.add(tid)
            unique.append(c)

    # 4. Book Diversity Balancing
    # Groups sources by book name and pulls candidate references equally
    # to avoid answers relying solely on a single document source.
    by_book = {}
    for c in unique:
        b = c["metadata"].get("book_name", "Unknown")
        by_book.setdefault(b, []).append(c)
    
    balanced = []
    for b in by_book:
        by_book[b].sort(key=lambda x: x["distance"])
        balanced.extend(by_book[b][:3])
    
    balanced.sort(key=lambda x: x["distance"])
    # 5. Strict Similarity Pruning
    filtered = [c for c in balanced if c["distance"] <= distance_threshold]
    
    # Fill remaining spots with closest unique options if thresholds are too tight
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

