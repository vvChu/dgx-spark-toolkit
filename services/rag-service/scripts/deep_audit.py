import os
from pymilvus import connections, Collection
from core.config import get_settings

_settings = get_settings()
MILVUS_HOST = os.getenv("MILVUS_HOST", _settings.MILVUS_HOST)
MILVUS_PORT = os.getenv("MILVUS_PORT", str(_settings.MILVUS_PORT))
COLLECTION_NAME = _settings.MILVUS_COLLECTION

def audit_chunks():
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    col = Collection(COLLECTION_NAME)
    col.load()
    
    # 1. Total count
    print(f"Total chunks: {col.num_entities}")
    
    # 2. Check for empty text
    empty_res = col.query(expr="text == \"\"", output_fields=["id", "source"], limit=10)
    print(f"Chunks with empty text: {len(empty_res)}")
    
    # 3. Sample chunks to check length distribution and quality
    print("\\n--- Sampling 10 random chunks ---")
    sample = col.query(expr="", output_fields=["source", "text"], limit=10)
    
    for i, s in enumerate(sample):
        text = s.get('text', '')
        source = s.get('source', '')
        print(f"\\nChunk {i+1} from {source}:")
        print(f"Length: {len(text)} characters")
        print(f"Preview: {text[:200].replace(chr(10), ' ')}...")
        if len(text) < 50:
            print("⚠️ WARNING: Extremely short chunk detected.")

if __name__ == "__main__":
    audit_chunks()
