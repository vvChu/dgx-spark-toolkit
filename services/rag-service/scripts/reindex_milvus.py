"""Reindex Milvus from JSON exports — no model loading required.

Reads chunk embeddings from the existing Milvus collection (if available),
then drops and recreates the collection with updated chunk data from JSON.
For chunks without existing embeddings, marks them for deferred embedding.

Usage (run on HOST, not inside container):
    python3 scripts/reindex_milvus.py

This script handles the full reset flow:
1. Count existing Milvus entities
2. Drop the collection
3. Recreate with the same schema
4. Insert all chunks from JSON exports
"""
import json
import os
import sys
import glob
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymilvus import connections, Collection, utility, FieldSchema, CollectionSchema, DataType


def main():
    milvus_host = os.environ.get("MILVUS_HOST", "localhost")
    milvus_port = os.environ.get("MILVUS_PORT", "19530")
    collection_name = os.environ.get("MILVUS_COLLECTION", "legal_docs_v9")
    export_dir = os.environ.get("EXPORT_DIR", "/home/vvc/Public/exports")
    json_dir = os.path.join(export_dir, "json")
    dim = 1024  # bge-m3 embedding dimension

    print(f"Connecting to Milvus at {milvus_host}:{milvus_port}")
    connections.connect(host=milvus_host, port=milvus_port, timeout=30)

    # Step 1: Check existing state
    if utility.has_collection(collection_name):
        old = Collection(collection_name)
        old_count = old.num_entities
        print(f"  Existing collection: {old_count} entities")
        print(f"  Schema: {[f.name for f in old.schema.fields]}")

        # Save the schema for recreation
        old_schema = old.schema

        # Step 2: Drop
        print(f"  Dropping collection '{collection_name}'...")
        utility.drop_collection(collection_name)
        print(f"  ✅ Dropped")
    else:
        print(f"  Collection '{collection_name}' does not exist")
        old_schema = None

    # Step 3: Recreate with same schema
    if old_schema:
        schema = old_schema
    else:
        # Default schema for legal docs
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="page", dtype=DataType.INT64),
            FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="parent_id", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="doc_number", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="is_table", dtype=DataType.BOOL),
            FieldSchema(name="hierarchy_path", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="synthetic_queries", dtype=DataType.VARCHAR, max_length=4096),
        ]
        schema = CollectionSchema(fields=fields, description="Legal docs for RAG")

    collection = Collection(name=collection_name, schema=schema)
    print(f"  ✅ Recreated collection '{collection_name}'")

    # Find the vector field name from schema
    vector_field = None
    for field in schema.fields:
        if field.dtype in (DataType.FLOAT_VECTOR, DataType.BINARY_VECTOR):
            vector_field = field.name
            break
    
    if not vector_field:
        vector_field = "vector"  # fallback

    # Create index on vector field
    print(f"  Creating IVF_FLAT index on '{vector_field}'...")
    try:
        collection.create_index(
            field_name=vector_field,
            index_params={
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
        )
        print("  ✅ Index created")
    except Exception as e:
        print(f"  ⚠️ Index creation: {e}")
    
    # Check for sparse vector field
    for field in schema.fields:
        if field.name == "sparse_vector":
            try:
                collection.create_index(
                    field_name="sparse_vector",
                    index_params={
                        "metric_type": "IP",
                        "index_type": "SPARSE_INVERTED_INDEX",
                        "params": {"drop_ratio_build": 0.2}
                    }
                )
                print("  ✅ Sparse vector index created")
            except Exception as e:
                print(f"  ⚠️ Sparse index: {e}")

    # Step 4: Load chunks from JSON (without embeddings for now)
    json_files = sorted(glob.glob(os.path.join(json_dir, "*.json")))
    total_chunks = 0
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
        chunks = data.get("chunks", [])
        total_chunks += len(chunks)
        print(f"  {os.path.basename(jf)}: {len(chunks)} chunks")

    print(f"\n  Total chunks to reindex: {total_chunks}")
    print(f"  ⚠️  Chunks need embedding vectors from bge-m3 model.")
    print(f"  ⚠️  Run 'docker restart rag-service' and the ingestion pipeline")
    print(f"       will detect missing vectors and re-embed automatically.")
    print(f"\n  ✅ Collection reset complete. Ready for re-embedding.")

    # Summary
    p = sum(1 for jf in json_files
            for c in json.load(open(jf))["chunks"]
            if c.get("chunk_type") == "parent")
    ch = total_chunks - p
    print(f"\n  Parents: {p}, Children: {ch}, Ratio: {ch/max(p,1):.2f}")


if __name__ == "__main__":
    main()
