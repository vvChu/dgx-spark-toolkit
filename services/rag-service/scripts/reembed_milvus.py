#!/usr/bin/env python3
"""Re-embed and insert all JSON export chunks into Milvus.

Runs on HOST (not in container). Uses rag-service's internal API
or direct pymilvus + sentence-transformers to embed and insert.

Usage:
    python3 scripts/reembed_milvus.py
"""
import json
import os
import sys
import glob
import logging
import time

from pymilvus import connections, Collection, utility

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

EXPORT_DIR = os.environ.get("EXPORT_DIR", "/home/vvc/Public/exports")
JSON_DIR = os.path.join(EXPORT_DIR, "json")
MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")
COLLECTION_NAME = os.environ.get("MILVUS_COLLECTION", "legal_docs_v10")


def main():
    logger.info("Connecting to Milvus...")
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT, timeout=30)

    if not utility.has_collection(COLLECTION_NAME):
        logger.error(f"Collection '{COLLECTION_NAME}' does not exist. Run reindex_milvus.py first.")
        return

    col = Collection(COLLECTION_NAME)
    schema_fields = [f.name for f in col.schema.fields]
    logger.info(f"Collection: {COLLECTION_NAME}, fields: {schema_fields}")
    logger.info(f"Current entities: {col.num_entities}")

    # Load embedding model
    logger.info("Loading bge-m3 embedding model...")
    try:
        from FlagEmbedding import BGEM3FlagModel
        model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    except ImportError:
        logger.warning("FlagEmbedding not available, trying sentence-transformers...")
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("BAAI/bge-m3")

    # Load all JSON chunks
    json_files = sorted(glob.glob(os.path.join(JSON_DIR, "*.json")))
    all_chunks = []
    for jf in json_files:
        if jf.endswith('.bak'):
            continue
        data = json.loads(open(jf).read())
        meta = data.get("metadata", {})
        for chunk in data.get("chunks", []):
            chunk["_meta"] = meta
            chunk["_source_file"] = os.path.basename(jf)
        all_chunks.extend(data.get("chunks", []))

    logger.info(f"Total chunks to embed: {len(all_chunks)}")

    # Utility: truncate string to byte limit
    def safe(val, limit=256):
        v = str(val or "")
        while len(v.encode('utf-8')) > limit:
            v = v[:-1]
        return v

    # Process in batches
    BATCH = 64
    total_inserted = 0

    for i in range(0, len(all_chunks), BATCH):
        batch = all_chunks[i:i+BATCH]
        texts = [c.get("text", "")[:14500] for c in batch]

        # Embed
        if hasattr(model, 'encode'):
            # BGEM3FlagModel
            output = model.encode(texts, return_dense=True, return_sparse=True)
            dense = output["dense_vecs"].tolist()
            sparse_raw = output["lexical_weights"]
        else:
            # sentence-transformers fallback
            dense = model.encode(texts).tolist()
            sparse_raw = [{} for _ in texts]

        # Build sparse vectors for Milvus
        sparse_vectors = []
        for sw in sparse_raw:
            if isinstance(sw, dict):
                sparse_vectors.append(sw)
            else:
                sparse_vectors.append({})

        # Build insertion data as list-of-lists (column-oriented, skip auto_id 'id')
        data = [
            texts,                                                                    # text
            [safe(c.get("source", ""), 512) for c in batch],                          # source
            [c.get("page", 1) for c in batch],                                       # page
            [safe(c.get("_meta", {}).get("summary", ""), 2048) for c in batch],       # summary
            [safe(c.get("_meta", {}).get("date", ""), 32) for c in batch],            # doc_date
            [safe(c.get("_meta", {}).get("type", ""), 32) for c in batch],            # doc_type
            [safe(c.get("_meta", {}).get("authority", ""), 64) for c in batch],       # authority
            [safe(c.get("_meta", {}).get("file_hash", ""), 64) for c in batch],       # file_hash
            [c.get("is_table", False) for c in batch],                                # is_table
            [safe(c.get("chunk_type", "parent"), 16) for c in batch],                 # chunk_type
            [safe(c.get("parent_id", ""), 256) for c in batch],                       # parent_id
            [safe(c.get("doc_number", ""), 128) for c in batch],                      # doc_number
            [safe(c.get("doc_id", ""), 256) for c in batch],                          # doc_id
            [safe(c.get("chunk_id", ""), 512) for c in batch],                        # chunk_id
            [json.dumps(c.get("bbox", [0,0,1000,1000])) for c in batch],              # bbox
            [safe(c.get("_meta", {}).get("validity_status", "ACTIVE"), 32) for c in batch],  # validity_status
            [safe(c.get("_meta", {}).get("legal_level", "UNKNOWN"), 32) for c in batch],     # legal_level
            [safe(c.get("hierarchy_path", ""), 1024) for c in batch],                 # hierarchy_path
            [0 for _ in batch],                                                       # citation_count
            [safe(c.get("_meta", {}).get("project_code", "GENERIC"), 64) for c in batch],    # project_code
            [safe(c.get("_meta", {}).get("discipline", "UNKNOWN"), 32) for c in batch],      # discipline
            [safe(c.get("_meta", {}).get("doc_status", "ACTIVE"), 32) for c in batch],       # doc_status
            [c.get("_meta", {}).get("revision", 0) for c in batch],                   # revision
            [safe(c.get("synthetic_queries", ""), 4090) for c in batch],              # synthetic_queries
            [safe(c.get("_meta", {}).get("source_category", "KHAC"), 64) for c in batch],    # source_category
            dense,                                                                    # vector
            sparse_vectors,                                                           # sparse_vector
        ]

        try:
            col.insert(data)
            total_inserted += len(batch)
            logger.info(f"  Batch {i//BATCH+1}: inserted {len(batch)} chunks (total: {total_inserted})")
        except Exception as e:
            logger.error(f"  Batch {i//BATCH+1} FAILED: {e}")

    col.flush()
    final_count = col.num_entities
    logger.info(f"\n✅ Done! Milvus entities: {final_count}")

    # Summary
    parents = sum(1 for c in all_chunks if c.get("chunk_type") == "parent")
    children = sum(1 for c in all_chunks if c.get("chunk_type") == "child")
    logger.info(f"Parents: {parents}, Children: {children}, Ratio: {children/max(parents,1):.2f}")


if __name__ == "__main__":
    main()
