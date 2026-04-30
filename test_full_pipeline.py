
import os
import json
import time
from dotenv import load_dotenv
load_dotenv()

# Force local chroma for testing
os.environ["VECTOR_STORE_TYPE"] = "chroma"
os.environ["CHROMA_DIR"] = "./test_chroma_db"

from core import vector_store, llm_client, config
from personas.ghazali import system_prompt

def run_automated_test():
    print("🚀 STARTING AUTOMATED RAG PIPELINE TEST")
    print("---------------------------------------")
    
    # 1. Initialize and Setup Mock Data
    print("1. Setting up Mock Vector Store...")
    vector_store.initialize()
    tenant_id = "ghazali_test"
    
    mock_chunks = [
        {
            "text": "Knowledge without action is madness, and action without knowledge is void. Purification of the heart (qalb) is the foundation of all spiritual growth.",
            "metadata": {"book_name": "Ihyā' Ulūm al-Dīn", "volume": "1", "page_number": "5", "chapter": "Knowledge"}
        },
        {
            "text": "The mirror of the heart must be polished through constant remembrance (dhikr) and discipline. Only then can it reflect the light of Allah.",
            "metadata": {"book_name": "Ihyā' Ulūm al-Dīn", "volume": "1", "page_number": "22", "chapter": "Remembrance"}
        }
    ]
    
    for i, c in enumerate(mock_chunks):
        c["chunk_id"] = f"mock_{i}"
    
    # Manually ingest into the test tenant
    vector_store.ingest(tenant_id, "505", mock_chunks)
    print(f"✅ Ingested {len(mock_chunks)} mock chunks into '{tenant_id}'")

    # 2. Define the Query
    # Using a follow-up style query to test the Rewriter
    user_query = "Tell me about the heart and how action relates to it?"
    print(f"\n2. User Query: '{user_query}'")
    
    # Get the system prompt
    sp = system_prompt.build_system_prompt()

    # 3. Step-by-Step Pipeline Execution
    try:
        # A. Rewriting
        print("\n3a. Testing Rewriter (Nemotron-Nano)...")
        # Mocking history for context
        history = [{"role": "user", "content": "What is the importance of knowledge?"}]
        rewritten_query = llm_client.rewrite_query(user_query, history)
        print(f"   🔄 Rewritten: '{rewritten_query}'")

        # B. Retrieval
        print("\n3b. Testing Vector Search (ChromaDB)...")
        results = vector_store.query(tenant_id, rewritten_query, death_date_ah="505", top_k=2)
        print(f"   🔍 Found {len(results)} chunks.")
        for r in results:
            print(f"      - [{r['metadata']['book_name']}] {r['text'][:50]}...")

        # C. Generation
        print("\n3c. Testing Generation (GPT-OSS 120b)...")
        start_time = time.time()
        result = llm_client.generate_answer(user_query, results, sp, history)
        gen_time = time.time() - start_time
        print(f"   ✍️ Generation completed in {gen_time:.2f}s")
        print(f"   📄 Result: {json.dumps(result, indent=2, ensure_ascii=False)}")

        # D. Verification
        print("\n3d. Testing Verification (Nemotron-Nano)...")
        is_grounded = llm_client.verify_answer(results, result)
        if is_grounded:
            print("   ✅ VERIFICATION PASSED: No hallucinations detected.")
        else:
            print("   ⚠️ VERIFICATION FAILED: Hallucination detected.")

        # E. Validation of new features
        print("\n4. Feature Validation:")
        # Check volume
        has_volume = any("volume" in c for c in result.get("citations", []))
        print(f"   - Volume in citations: {'✅ YES' if has_volume else '❌ NO'}")
        
        # Check Arabic detection (simulated)
        arabic_test = "ما هو القلب؟"
        from personas.ghazali import telegram_bot
        detected_lang = telegram_bot._detect_language(arabic_test)
        print(f"   - Arabic Detection Test ('{arabic_test}'): {'✅ PASSED' if detected_lang == 'Arabic' else '❌ FAILED'} (Detected: {detected_lang})")

    except Exception as e:
        print(f"\n❌ TEST CRASHED: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_automated_test()
