"""
Ingestion Script — loads, chunks, embeds, and stores source texts.

Embedding: Voyage AI (voyage-3.5-lite) — $0.02/1M tokens, 200M free.
Output model: Gemini / Claude (configured via LLM_PROVIDER in .env).

Run once before starting the bot:
    python ingest.py

⚠️  If you previously ingested with a different embedding model (e.g. Gemini),
    you MUST choose [y] to clear the collection and re-ingest from scratch.
    Vectors from different models are incompatible and cannot be mixed.
"""

import sys
import time

import config
from data_loader import load_all_sources
from chunker import chunk_all_documents
import vector_store


def _validate_config():
    """Validate required API keys before starting ingestion."""
    errors = []

    if not config.VOYAGE_API_KEY:
        errors.append(
            "  ✗ VOYAGE_API_KEY is not set.\n"
            "    Sign up at https://www.voyageai.com (200M free tokens)\n"
            "    then add VOYAGE_API_KEY=... to your .env file."
        )

    # Output model key (needed at query time, not ingestion, but good to warn early)
    if not config.GEMINI_API_KEY and not config.ANTHROPIC_API_KEY:
        errors.append(
            "  ✗ No output model API key found.\n"
            "    Set GEMINI_API_KEY or ANTHROPIC_API_KEY in your .env file."
        )

    if errors:
        print("\n" + "\n".join(errors))
        sys.exit(1)


def main():
    print("=" * 60)
    print("  📥  Resurrection Agent — Source Ingestion")
    print(f"       Embedding model: {config.EMBEDDING_MODEL}")
    print(f"       Vector dimension: {config.VOYAGE_OUTPUT_DIMENSION}")
    print("=" * 60)

    # Validate configuration
    _validate_config()

    # Step 1: Load sources
    print(f"\n📂 Loading sources from: {config.SOURCES_DIR}")
    try:
        documents = load_all_sources(config.SOURCES_DIR)
    except (FileNotFoundError, ValueError) as e:
        print(f"\n✗ {e}")
        sys.exit(1)

    print(f"\n  Total documents loaded: {len(documents)}")

    # Step 2: Chunk documents
    print("\n✂️  Chunking documents (paragraph-first, token-aware)...")
    chunks = chunk_all_documents(documents)
    print(f"     Chunk size:    ~{config.CHUNK_SIZE} tokens")
    print(f"     Chunk overlap: ~{config.CHUNK_OVERLAP} tokens")

    # Step 3: Initialize vector store
    print("\n🗄️  Initializing ChromaDB...")
    vector_store.initialize()

    # Check if already ingested
    if vector_store.is_ingested():
        stats = vector_store.get_source_stats()
        print(f"\n⚠️  Collection already has {stats['total_chunks']} chunks.")
        print("   ⚠️  If those were embedded with a DIFFERENT model (e.g. Gemini),")
        print("       you MUST re-ingest — mixed vectors will give wrong results.")
        print("\n   Options:")
        print("     [c] Continue — skip already-ingested chunks (resume same model)")
        print("     [y] Re-ingest — clear all and start fresh (required if model changed)")
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
    print(f"  Embedding model:   {config.EMBEDDING_MODEL}")
    print(f"  Documents loaded:  {len(documents)}")
    print(f"  Chunks created:    {len(chunks)}")
    print(f"  Chunks stored:     {stats['total_chunks']}")
    print(f"  Books indexed:     {', '.join(stats['books'])}")
    print(f"  Time elapsed:      {elapsed:.1f}s")
    print(f"\n  Start the agent:   python main.py")


if __name__ == "__main__":
    main()
