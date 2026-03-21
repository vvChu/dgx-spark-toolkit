from pymilvus import MilvusClient
from core.config import get_settings

_settings = get_settings()
MILVUS_URI = f"http://{_settings.MILVUS_HOST}:{_settings.MILVUS_PORT}"
COLLECTION_NAME = _settings.MILVUS_COLLECTION

client = MilvusClient(uri=MILVUS_URI)

print(f"Describing collection: {COLLECTION_NAME}")
desc = client.describe_collection(collection_name=COLLECTION_NAME)
for field in desc['fields']:
    print(f"  Field: {field['name']} ({field['type']})")

print("\nFetching sample parent chunk...")
res = client.query(
    collection_name=COLLECTION_NAME,
    filter='chunk_type == "parent"',
    limit=5
)
for entry in res:
    print(f"  Source: {entry.get('source')}")
    print(f"  Available keys: {list(entry.keys())}")
    print(f"  Doc Number: {entry.get('doc_number')}")
