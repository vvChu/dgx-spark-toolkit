from pymilvus import connections, Collection
import json
from core.config import get_settings

_settings = get_settings()
connections.connect(host=_settings.MILVUS_HOST, port=str(_settings.MILVUS_PORT))
collection = Collection(_settings.MILVUS_COLLECTION)
collection.load()

# Get a few chunks with their bboxes
res = collection.query(expr="id > 0", limit=5, output_fields=["page", "bbox", "source", "text"])

print("--- Sample Chunks with Coordinate Data ---")
for r in res:
    print(f"Page: {r['page']} | Source: {r['source']}")
    print(f"BBox: {r['bbox']}")
    print(f"Text Snippet: {r['text'][:50]}...")
    print("-" * 20)
