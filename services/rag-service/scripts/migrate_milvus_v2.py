import os
import json
import time
from pymilvus import connections, Collection, utility, FieldSchema, CollectionSchema, DataType

# Configuration
MILVUS_HOST = os.getenv("MILVUS_HOST", "milvus-standalone")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
OLD_COLLECTION = "legal_docs_v2"
NEW_COLLECTION = "legal_docs_v7"

def migrate():
    print(f"Connecting to Milvus at {MILVUS_HOST}:{MILVUS_PORT}...")
    connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
    
    if not utility.has_collection(OLD_COLLECTION):
        print(f"Error: Old collection {OLD_COLLECTION} not found!")
        return

    old_col = Collection(OLD_COLLECTION)
    old_col.load()
    
    print(f"Creating new collection {NEW_COLLECTION}...")
    if utility.has_collection(NEW_COLLECTION):
        print(f"Collection {NEW_COLLECTION} already exists. Dropping it first.")
        utility.drop_collection(NEW_COLLECTION)
    
    # Define new schema including doc_number
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=15000),
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="page", dtype=DataType.INT64),
        FieldSchema(name="summary", dtype=DataType.VARCHAR, max_length=2048),
        FieldSchema(name="doc_date", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="authority", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="file_hash", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="is_table", dtype=DataType.BOOL),
        FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=16),
        FieldSchema(name="parent_id", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="doc_number", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=1024),
        FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR)
    ]
    schema = CollectionSchema(fields, "Legal Docs v2 - with doc_number support")
    new_col = Collection(NEW_COLLECTION, schema)
    
    # Create Indices
    print("Creating indices for NEW_COLLECTION...")
    new_col.create_index("vector", {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": 16, "efConstruction": 500}})
    new_col.create_index("sparse_vector", {"metric_type": "IP", "index_type": "SPARSE_INVERTED_INDEX", "params": {"drop_ratio_build": 0.2}})
    new_col.create_index("doc_number", {"index_type": "INVERTED", "params": {}})
    
    print(f"Migrating entities from {OLD_COLLECTION} to {NEW_COLLECTION}...")
    
    # Use query_iterator for large datasets to avoid offset/limit constraints
    iterator = old_col.query_iterator(
        batch_size=500,
        expr="id > 0",
        output_fields=["text", "source", "page", "summary", "doc_date", "doc_type", "authority", "file_hash", "is_table", "chunk_type", "parent_id", "vector", "sparse_vector"]
    )
    
    total_migrated = 0
    batch_idx = 0
    
    while True:
        res = iterator.next()
        if not res:
            break
            
        batch_idx += 1
        print(f"Processing batch {batch_idx} (Size: {len(res)})...")
        
        # Prepare data for insertion
        data = {field.name: [] for field in fields if not field.is_primary}
        
        for r in res:
            for field_name in data.keys():
                if field_name == "doc_number":
                    data["doc_number"].append("") 
                else:
                    data[field_name].append(r.get(field_name))
        
        # Insert into new collection
        insert_data = [data[f.name] for f in fields if not f.is_primary]
        new_col.insert(insert_data)
        
        total_migrated += len(res)
        
    print(f"Migration complete! Total migrated: {total_migrated}")
    new_col.flush()

if __name__ == "__main__":
    migrate()
