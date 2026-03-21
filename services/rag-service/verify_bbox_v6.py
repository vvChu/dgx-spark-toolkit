from pymilvus import connections, Collection
from core.config import get_settings

_settings = get_settings()
connections.connect(host=_settings.MILVUS_HOST, port=str(_settings.MILVUS_PORT))
collection = Collection(_settings.MILVUS_COLLECTION)
collection.load()

# Search for bboxes that are NOT the default
# We use a broader query to find any precise bboxes
res = collection.query(
    expr='bbox != "[0, 0, 1000, 1000]"', 
    limit=10, 
    output_fields=["page", "bbox", "text", "source", "doc_number"]
)

print("--- Precise Coordinate Detection ---")
for r in res:
    print(f"Doc: {r.get('doc_number')} | Source: {r['source']}")
    print(f"BBox: {r['bbox']}")
    print(f"Text: {r['text'][:50]}...")
    print("-" * 20)
    
if not res:
    print("No precise coordinates found yet.")
