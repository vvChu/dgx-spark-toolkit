from pymilvus import connections, Collection
from core.config import get_settings

_settings = get_settings()
connections.connect(host=_settings.MILVUS_HOST, port=str(_settings.MILVUS_PORT))
collection = Collection(_settings.MILVUS_COLLECTION)
collection.load()

# Search for the recently completed Da Nang document
res = collection.query(
    expr='source == "20250527_QD452-SXD-Danang_Quy dinh tam thoi ve lap-ttra-tdinh HSTK sd BIM.pdf"', 
    limit=5, 
    output_fields=["page", "bbox", "text"]
)

print("--- Deep-Link Confirmation (QD452-SXD-Danang) ---")
for r in res:
    print(f"Page: {r['page']} | BBox: {r['bbox']}")
    print(f"Text: {r['text'][:100]}...")
    print("-" * 20)

if not res:
    print("Document not found in Milvus yet. Re-trying with source name...")
