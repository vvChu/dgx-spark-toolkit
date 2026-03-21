from pymilvus import connections, Collection
import json
from core.config import get_settings

_settings = get_settings()
connections.connect(host=_settings.MILVUS_HOST, port=str(_settings.MILVUS_PORT))
collection = Collection(_settings.MILVUS_COLLECTION)
collection.load()

# Search for chunks of the Da Nang document
res = collection.query(expr='text LIKE "%Da Nang%"', limit=10, output_fields=["page", "bbox", "text"])

print("--- Data Check for Da Nang Document ---")
for r in res:
    print(f"Page: {r['page']} | BBox: {r['bbox']}")
    print(f"Text: {r['text'][:100]}...")
    print("-" * 20)
