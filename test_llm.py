
import os
import json
from dotenv import load_dotenv
load_dotenv()

from core import llm_client, config

def test_nemotron_connection():
    print("--- Testing OpenRouter Nemotron Connection ---")
    print(f"Provider: {config.LLM_PROVIDER}")
    print(f"Model: {config.OPENROUTER_MODEL}")
    
    if not config.OPENROUTER_API_KEY or config.OPENROUTER_API_KEY == "your-openrouter-api-key-here":
        print("ERROR: OPENROUTER_API_KEY is not set in .env")
        return

    # Mock data for generation
    query = "Hello, who are you and what is your philosophy?"
    retrieved_chunks = [
        {
            "text": "I am Abu Hamid al-Ghazali, a seeker of truth. I believe in the synthesis of reason and revelation.",
            "metadata": {"book_name": "Test Book", "page_number": "1", "chapter": "Intro"}
        }
    ]
    system_prompt = "You are Abu Hamid al-Ghazali. Speak in your characteristic philosophical and humble tone. Respond in JSON."

    try:
        print("\nSending request to OpenRouter...")
        result = llm_client.generate_answer(query, retrieved_chunks, system_prompt)
        print("\n--- Response Received ---")
        print(json.dumps(result, indent=2))
        
        if result.get("answer_text"):
            print("\n✅ LLM Switch is SUCCESSFUL!")
        else:
            print("\n⚠️ Received empty response text. Check API settings.")
            
    except Exception as e:
        print(f"\n❌ FAILED: {str(e)}")

if __name__ == "__main__":
    test_nemotron_connection()
