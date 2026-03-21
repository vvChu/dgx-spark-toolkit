import os
from pymilvus import connections, Collection
from core.config import get_settings

_settings = get_settings()
# Connection settings
MILVUS_HOST = os.getenv("MILVUS_HOST", _settings.MILVUS_HOST)
MILVUS_PORT = os.getenv("MILVUS_PORT", str(_settings.MILVUS_PORT))
COLLECTION_NAME = _settings.MILVUS_COLLECTION

def audit_quality():
    print(f"Connecting to Milvus at {MILVUS_HOST}:{MILVUS_PORT}...")
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    
    try:
        col = Collection(COLLECTION_NAME)
        col.load()
    except Exception as e:
        print(f"Error loading collection {COLLECTION_NAME}: {e}")
        return

    print(f"Auditing collection: {COLLECTION_NAME}...")
    
    # Query for potentially problematic data
    # In v7, we primarily check if 'text' is empty or 'file_hash' is missing
    res = col.query(
        expr='text == ""',
        output_fields=["id", "source", "page"],
        limit=100
    )

    if not res:
        print("✅ No documents with empty text or missing file_hash found in the sample.")
        # Also check count
        print(f"Total entities in collection: {col.num_entities}")
    else:
        print(f"⚠️ Found {len(res)} chunks with low-quality data issues.")
        for r in res:
            print(f" - ID: {r['id']} | File: {r.get('source', 'unknown')} | Type: {r.get('doc_type', 'N/A')}")

if __name__ == "__main__":
    audit_quality()
