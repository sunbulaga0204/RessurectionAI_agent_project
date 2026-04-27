import core.vector_store as vector_store
from core.openiti_client import _resolve_book_title
import chromadb

def fix_titles(tenant_id):
    print(f"🔍 Scanning '{tenant_id}' for untitled OpenITI chunks...")
    vector_store.initialize()
    coll = vector_store._get_collection(tenant_id)
    
    # Fetch everything (metadata only)
    results = coll.get(include=["metadatas"])
    ids = results["ids"]
    metas = results["metadatas"]
    
    updated_ids = []
    updated_metas = []
    
    for i, meta in enumerate(metas):
        if meta.get("book_name") == "Unknown OpenITI Text":
            filename = meta.get("source_file", "")
            # We don't have the raw header title here, but the filename resolution is strong
            new_title = _resolve_book_title("", filename)
            
            if new_title != "Unknown OpenITI Text":
                meta["book_name"] = new_title
                updated_ids.append(ids[i])
                updated_metas.append(meta)

    if updated_ids:
        print(f"🚀 Updating {len(updated_ids)} chunks with new title...")
        coll.update(ids=updated_ids, metadatas=updated_metas)
        print("✅ Titles fixed successfully.")
    else:
        print("✨ No 'Unknown' chunks found. Your DB is already clean or using correct titles.")

if __name__ == "__main__":
    fix_titles("ghazali")
