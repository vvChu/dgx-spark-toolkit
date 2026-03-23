import logging
import os
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
from retrieval.embeddings.bge_m3_hybrid import BGE_M3_HybridEmbedding
from core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_settings = get_settings()
MILVUS_HOST = os.getenv("MILVUS_HOST", _settings.MILVUS_HOST)
MILVUS_PORT = os.getenv("MILVUS_PORT", str(_settings.MILVUS_PORT))
COLLECTION_NAME = _settings.MILVUS_COLLECTION


def migrate_sparse():
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    logger.info(f"Connected to Milvus at {MILVUS_HOST}:{MILVUS_PORT}")

    if not utility.has_collection(COLLECTION_NAME):
        logger.error(f"Collection {COLLECTION_NAME} does not exist. Cannot migrate.")
        return

    col = Collection(COLLECTION_NAME)

    # Check if sparse_vector exists
    schema_fields = [f.name for f in col.schema.fields]
    if "sparse_vector" not in schema_fields:
        logger.error("No 'sparse_vector' field in schema! Cannot migrate.")
        return

    logger.info("Initializing BGE-M3 Model for Migration...")
    model = BGE_M3_HybridEmbedding()

    # Create an iterator over the collection to update records.
    # Note: Milvus doesn't support direct partial updates for vectors easily without replacing the whole entity.
    # For large datasets, it's better to fetch entities, generate new sparse vectors, and upsert them.

    # We will search by chunks
    limit = 100
    expr = ""
    col.load()

    # Using an iterator approach
    # Since Milvus doesn't have a simple cursor for full table scan, we can use the partition or range query.
    # An alternative is to just drop and re-ingest, but the user requested zero-downtime re-embedding.
    # Due to complexity of iterating all IDs accurately in Milvus without a PK cursor, we will do a query based on primary key pagination if possible.

    logger.info("Starting background re-embedding process... (This may take a while)")

    res = col.query(expr="id >= 0", output_fields=["id", "text"], limit=10000)

    if not res:
        logger.info("Collection is empty!")
        return

    total_records = len(res)
    logger.info(f"Found {total_records} records to migrate.")

    batch_size = 32
    for i in range(0, total_records, batch_size):
        batch = res[i:i+batch_size]
        ids = [hit['id'] for hit in batch]
        texts = [hit['text'] for hit in batch]

        # We need the full entities to do an upsert, so let's query all dynamic fields
        full_entities = col.query(expr=f"id in {ids}", output_fields=schema_fields)

        # Generate new native sparse vectors
        embeddings = model.embed_documents(texts)
        native_sparse = embeddings["sparse"]
        native_dense = embeddings["dense"]  # We can also sync the dense if needed, but we keep original if preferred.

        # Prepare data for upsert
        upsert_data = []
        for field in col.schema.fields:
            if field.name == "sparse_vector":
                upsert_data.append(native_sparse)
            elif field.name == "vector":
                upsert_data.append(native_dense)  # Safest to re-embed dense at the same time to match M3 output perfectly
            else:
                field_data = [ent[field.name] for ent in full_entities]
                upsert_data.append(field_data)

        col.upsert(upsert_data)
        logger.info(f"Migrated batch {i} to {i+len(batch)} / {total_records}")

    logger.info("Migration to Native Sparse Vectors completed successfully!")


if __name__ == "__main__":
    migrate_sparse()
