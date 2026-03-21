from pymilvus import connections, Collection
from core.config import get_settings

_settings = get_settings()
connections.connect(host=_settings.MILVUS_HOST, port=str(_settings.MILVUS_PORT))
collection = Collection(_settings.MILVUS_COLLECTION)
collection.load()

# Get the 10 most recent chunks based on their internal ID (auto-increment)
res = collection.query(expr="id > 0", limit=10, output_fields=["page", "bbox", "text", "doc_number", "source"])

print("--- Recent Chunks Coordinate Check ---")
for r in res:
    print(f"Doc: {r.get('doc_number')} | Page: {r['page']} | Source: {r['source']}")
    print(f"BBox: {r['bbox']}")
    print(f"Text: {r['text'][:50]}...")
    print("-" * 20)
