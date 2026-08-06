from pymilvus import connections, Collection, utility
import logging
from core.config import get_settings

settings = get_settings()
MILVUS_HOST = settings.MILVUS_HOST
MILVUS_PORT = str(settings.MILVUS_PORT)
COLLECTION_NAME = settings.MILVUS_COLLECTION


def audit_milvus():
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    if not utility.has_collection(COLLECTION_NAME):
        print(f"Collection {COLLECTION_NAME} does not exist.")
        return

    collection = Collection(COLLECTION_NAME)
    # collection.load() # Loading might be heavy, but usually fine for audit

    # In Milvus 2.x, we use flush+num_entities or query.
    # For counts with filters, we can use query with expr.

    num_entities = collection.num_entities
    print(f"Total entities in {COLLECTION_NAME}: {num_entities}")

    # We'll use a trick: query with limit 0 or similar to see if it works,
    # but pymilvus 2.4+ supports count(*)
    try:
        results = collection.query(expr="id > 0", output_fields=["count(*)"])
        print(f"Verified count: {results[0]['count(*)']}")

        parents = collection.query(expr="chunk_type == 'parent'", output_fields=["count(*)"])[0]["count(*)"]
        children = collection.query(expr="chunk_type == 'child'", output_fields=["count(*)"])[0]["count(*)"]

        print(f"Parents: {parents}")
        print(f"Children: {children}")
        if parents > 0:
            print(f"Avg children per parent: {children/parents:.2f}")

        with_synth = collection.query(expr="synthetic_queries != ''", output_fields=["count(*)"])[0]["count(*)"]
        print(f"Chunks with synthetic queries: {with_synth} ({with_synth/num_entities*100 if num_entities > 0 else 0:.2f}%)")
    except Exception as e:
        print(f"Advanced count failed (v2.x legacy?): {e}")
        # Fallback to a small sample
        res = collection.query(expr="id > 0", limit=10, output_fields=["chunk_type", "synthetic_queries"])
        print(f"Sample data available: {len(res)} chunks")


if __name__ == "__main__":
    audit_milvus()
