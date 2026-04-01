"""
Ingestion Script — loads, chunks, embeds, and stores source texts.
Run this once before starting the bot: python ingest.py
"""

import sys
import time

import config
from data_loader import load_all_sources
from chunker import chunk_all_documents
import vector_store


def main():
    print("=" * 60)
    print("  📥  Resurrection Agent — Source Ingestion")
    print("=" * 60)

    # Validate config
    if not config.GEMINI_API_KEY:
        print("\n✗ GEMINI_API_KEY not set. Create a .env file from .env.example")
        sys.exit(1)

    # Step 1: Load sources
    print(f"\n📂 Loading sources from: {config.SOURCES_DIR}")
    try:
        documents = load_all_sources(config.SOURCES_DIR)
    except (FileNotFoundError, ValueError) as e:
        print(f"\n✗ {e}")
        sys.exit(1)

    print(f"\n  Total documents loaded: {len(documents)}")

    # Step 2: Chunk documents
    print("\n✂️  Chunking documents...")
    chunks = chunk_all_documents(documents)

    # Step 3: Initialize vector store
    print("\n🗄️  Initializing ChromaDB...")
    vector_store.initialize()

    # Check if already ingested
    if vector_store.is_ingested():
        stats = vector_store.get_source_stats()
        print(f"\n⚠️  Collection already has {stats['total_chunks']} chunks.")
        print("   Options:")
        print("     [c] Continue — skip already-ingested chunks (resume)")
        print("     [y] Re-ingest — clear all and start fresh")
        print("     [N] Cancel")
        response = input("   Choice [c/y/N]: ").strip().lower()
        if response == "y":
            vector_store.clear()
        elif response == "c":
            existing_ids = set(vector_store.get_existing_ids())
            before = len(chunks)
            chunks = [c for c in chunks if c["chunk_id"] not in existing_ids]
            print(f"\n⏩ Resuming: {before - len(chunks)} already stored, {len(chunks)} remaining.")
            if not chunks:
                print("   Nothing to ingest — all chunks are already stored!")
                return
        else:
            print("   Skipping ingestion. Existing data preserved.")
            return

    # Step 4: Embed and store
    start_time = time.time()
    vector_store.ingest(chunks)
    elapsed = time.time() - start_time

    # Summary
    stats = vector_store.get_source_stats()
    print("\n" + "=" * 60)
    print("  ✅  Ingestion Complete!")
    print("=" * 60)
    print(f"  Documents loaded:  {len(documents)}")
    print(f"  Chunks created:    {len(chunks)}")
    print(f"  Chunks stored:     {stats['total_chunks']}")
    print(f"  Books indexed:     {', '.join(stats['books'])}")
    print(f"  Time elapsed:      {elapsed:.1f}s")
    print(f"\n  Start the agent: python main.py")


if __name__ == "__main__":
    main()
