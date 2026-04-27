"""
Migration Script — ChromaDB to PostgreSQL (pgvector).
Moves existing embeddings from local storage to cloud storage without re-spending API tokens.
"""

import os
import json
import psycopg2
from psycopg2.extras import execute_values
import chromadb
from dotenv import load_dotenv

# Load local environment
load_dotenv()

CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
DATABASE_URL = os.getenv("DATABASE_URL")

def migrate():
    if not DATABASE_URL:
        print("❌ Error: DATABASE_URL not set in .env")
        return

    print("🔍 Connecting to local ChromaDB...")
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    
    print("🔍 Connecting to remote PostgreSQL...")
    pg_conn = psycopg2.connect(DATABASE_URL)
    pg_conn.autocommit = True
    
    with pg_conn.cursor() as cur:
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
        """)
        print("✅ Postgres table ready.")

    # Get all collections
    collections = chroma_client.list_collections()
    if not collections:
        print("ℹ️ No ChromaDB collections found.")
        return

    for coll_name in collections:
        print(f"\n📦 Migrating collection: {coll_name}...")
        
        # Determine tenant_id from collection name (e.g., tenant_ghazali -> ghazali)
        tenant_id = coll_name.name.replace("tenant_", "")
        if tenant_id == "sources": tenant_id = "ghazali" # fallback

        coll = chroma_client.get_collection(coll_name.name)
        total_count = coll.count()
        print(f"   Found {total_count} records.")

        batch_size = 500
        for offset in range(0, total_count, batch_size):
            # Fetch from Chroma
            results = coll.get(
                include=["documents", "metadatas", "embeddings"],
                limit=batch_size,
                offset=offset
            )
            
            ids = results["ids"]
            docs = results["documents"]
            metas = results["metadatas"]
            embs = results["embeddings"]
            
            if not ids: break

            # Prepare for Postgres
            data = []
            for i in range(len(ids)):
                death_date = metas[i].get("death_date_ah", "unknown")
                
                # Convert embedding to native python list if it's a numpy array
                emb = embs[i]
                if hasattr(emb, "tolist"):
                    emb = emb.tolist()
                elif isinstance(emb, tuple):
                    emb = list(emb)
                    
                data.append((
                    tenant_id,
                    ids[i],
                    str(death_date),
                    docs[i],
                    json.dumps(metas[i]),
                    emb
                ))

            # Insert into Postgres
            with pg_conn.cursor() as cur:
                execute_values(cur, """
                    INSERT INTO document_chunks (tenant_id, chunk_id, death_date_ah, content, metadata, embedding)
                    VALUES %s
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding
                """, data)
            
            print(f"   ✓ Progress: {min(offset + batch_size, total_count)}/{total_count} migrated")

    print("\n🎉 Migration complete!")
    pg_conn.close()

if __name__ == "__main__":
    migrate()
