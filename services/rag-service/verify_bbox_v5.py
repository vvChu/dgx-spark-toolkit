from pymilvus import connections, Collection
from core.config import get_settings

_settings = get_settings()
connections.connect(host=_settings.MILVUS_HOST, port=str(_settings.MILVUS_PORT))
collection = Collection(_settings.MILVUS_COLLECTION)
collection.load()

# Search for bboxes that are NOT the default string "[0, 0, 1000, 1000]"
# Wait, Milvus stores it as VARCHAR. I need to be careful with the expression.
res = collection.query(expr='bbox != "[0, 0, 1000, 1000]"', limit=5, output_fields=["page", "bbox", "text", "doc_number", "source"])

print("--- Chunks with Precise Coordinates ---")
for r in res:
    print(f"Doc: {r.get('doc_number')} | Page: {r['page']} | Source: {r['source']}")
    print(f"BBox: {r['bbox']}")
    print(f"Text: {r['text'][:50]}...")
    print("-" * 20)
    
if not res:
    print("No precise coordinates found yet. This might be due to pending re-ingestion.")
