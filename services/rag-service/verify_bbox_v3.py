from pymilvus import connections, Collection
from core.config import get_settings

_settings = get_settings()
connections.connect(host=_settings.MILVUS_HOST, port=str(_settings.MILVUS_PORT))
collection = Collection(_settings.MILVUS_COLLECTION)
collection.load()

# Search using doc_number
res = collection.query(expr='doc_number == "1238/2024/QD-TTg"', limit=5, output_fields=["page", "bbox", "text"])

print("--- Deep-Link Verification (1238/2024/QD-TTg) ---")
for r in res:
    print(f"Page: {r['page']} | BBox: {r['bbox']}")
    print(f"Text: {r['text'][:100]}...")
    print("-" * 20)
