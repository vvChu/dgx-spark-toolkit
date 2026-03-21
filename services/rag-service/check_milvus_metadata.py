from pymilvus import MilvusClient
from core.config import get_settings

_settings = get_settings()
MILVUS_HOST = _settings.MILVUS_HOST
MILVUS_PORT = str(_settings.MILVUS_PORT)
COLLECTION_NAME = _settings.MILVUS_COLLECTION

client = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")

# Get unique sources and their doc_numbers
# Milvus doesn't have a direct "SELECT DISTINCT", so we query with a limit or iterate.
# Since we have ~1400 docs, we can query a large batch of parent chunks.

res = client.query(
    collection_name=COLLECTION_NAME,
    filter='chunk_type == "parent"',
    output_fields=["source", "doc_number"]
)

# Deduplicate by source
source_to_doc = {}
for entry in res:
    source = entry.get("source")
    doc_num = entry.get("doc_number")
    if source and doc_num:
        source_to_doc[source] = doc_num

print(f"Found {len(source_to_doc)} unique sources with doc_numbers in Milvus.")
for i, (src, num) in enumerate(list(source_to_doc.items())[:10]):
    print(f"  {src} -> {num}")
