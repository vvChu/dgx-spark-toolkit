"""Milvus indexing mixin — collection setup + chunk insertion."""
import json
import logging
import re

from pymilvus import Collection, utility, FieldSchema, CollectionSchema, DataType

from ingestion import pipeline_config
from ingestion.text_normalizer import detect_garbled_table

logger = logging.getLogger(__name__)


class IndexingMixin:
    """Methods for Milvus collection management and chunk indexing."""

    def setup_collection(self):
        if utility.has_collection(pipeline_config.COLLECTION_NAME):
            col = Collection(pipeline_config.COLLECTION_NAME)
            required_fields = [
                "sparse_vector", "bbox", "validity_status", "project_code",
                "synthetic_queries", "hierarchy_path", "doc_id", "chunk_id", "source_category"
            ]
            has_required = all(any(f.name == rf for f in col.schema.fields) for rf in required_fields)

            if not has_required:
                logger.info("Outdated schema detected — dropping and recreating with v10...")
                utility.drop_collection(pipeline_config.COLLECTION_NAME)
            else:
                col.load()
                return col

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
            FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=256, default_value=""),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=512, default_value=""),
            FieldSchema(name="bbox", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="validity_status", dtype=DataType.VARCHAR, max_length=32, default_value="ACTIVE"),
            FieldSchema(name="legal_level", dtype=DataType.VARCHAR, max_length=32, default_value="UNKNOWN"),
            FieldSchema(name="hierarchy_path", dtype=DataType.VARCHAR, max_length=1024, default_value=""),
            FieldSchema(name="citation_count", dtype=DataType.INT64, default_value=0),
            FieldSchema(name="project_code", dtype=DataType.VARCHAR, max_length=64, default_value="GENERIC"),
            FieldSchema(name="discipline", dtype=DataType.VARCHAR, max_length=32, default_value="UNKNOWN"),
            FieldSchema(name="doc_status", dtype=DataType.VARCHAR, max_length=32, default_value="ACTIVE"),
            FieldSchema(name="revision", dtype=DataType.INT64, default_value=0),
            FieldSchema(name="synthetic_queries", dtype=DataType.VARCHAR, max_length=4095, default_value=""),
            FieldSchema(name="source_category", dtype=DataType.VARCHAR, max_length=64, default_value="KHAC"),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=1024),
            FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
        ]
        schema = CollectionSchema(fields, "Production Legal Documents v10 - Unified Identity Architecture")
        col = Collection(pipeline_config.COLLECTION_NAME, schema)

        # Dense vector index
        col.create_index(field_name="vector", index_params={
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 500}
        })
        # Sparse vector index
        col.create_index(field_name="sparse_vector", index_params={
            "metric_type": "IP",
            "index_type": "SPARSE_INVERTED_INDEX",
            "params": {"drop_ratio_build": 0.2}
        })
        # Scalar indexes for filtering
        col.create_index(field_name="doc_number", index_params={"index_type": "INVERTED", "params": {}})
        col.create_index(field_name="doc_id", index_params={"index_type": "INVERTED", "params": {}})
        col.create_index(field_name="validity_status", index_params={"index_type": "INVERTED", "params": {}})
        col.create_index(field_name="project_code", index_params={"index_type": "INVERTED", "params": {}})

        col.load()
        logger.info(f"Created collection {pipeline_config.COLLECTION_NAME} with Hybrid Search (Dense+Sparse) and V10 Schema")
        return col

    def index_chunks(self, chunks, summary, meta, file_hash):
        if not chunks:
            return

        chunk_types = [c.get("chunk_type", "parent") for c in chunks]
        logger.info(f"  Preparing to index {len(chunks)} chunks: {chunk_types.count('parent')} parents, {chunk_types.count('child')} children")

        # Cleanup existing entries for this file_hash
        try:
            if not re.fullmatch(r'[0-9a-fA-F]+', file_hash):
                raise ValueError(f"Unexpected file_hash format: {file_hash!r}")
            self.collection.delete(expr=f"file_hash == '{file_hash}'")
        except Exception as e:
            logger.warning(f"  Cleanup of old chunks for {file_hash} failed: {e}")

        BATCH_SIZE = 200

        # Quality gate — filter out empty, too-short, or garbled chunks
        quality_chunks = []
        for c in chunks:
            text = c.get("text", "").strip()
            if len(text) < 20:
                continue
            if detect_garbled_table(text):
                logger.debug(f"  [C5] Skipping garbled chunk (page {c.get('page', '?')}): {text[:60]}...")
                continue
            quality_chunks.append(c)
        if len(quality_chunks) < len(chunks):
            logger.info(f"  [C5] Quality gate: {len(chunks)} → {len(quality_chunks)} chunks")
        chunks = quality_chunks
        if not chunks:
            logger.warning(f"  [C5] All chunks filtered by quality gate — nothing to index.")
            return

        for i in range(0, len(chunks), BATCH_SIZE):
            batch_chunks = chunks[i:i + BATCH_SIZE]
            MAX_TEXT_LEN = 14500
            texts = []
            for c in batch_chunks:
                t = c["text"]
                if len(t) > MAX_TEXT_LEN:
                    logger.warning(f"  [P0] Truncating chunk ({len(t)} → {MAX_TEXT_LEN} chars) on page {c.get('page', '?')}")
                    t = t[:MAX_TEXT_LEN] + "…[truncated]"
                texts.append(t)

            # Strip identity prefixes before embedding for cleaner semantic vectors
            texts_for_embedding = [re.sub(r'^\[.*?\]\s*', '', t, count=1) for t in texts]
            texts_for_embedding = [re.sub(r'^.*?:::\s*', '', t, count=1) for t in texts_for_embedding]

            embeddings = self.model.embed_documents(texts_for_embedding)
            dense_embeddings = embeddings["dense"]
            sparse_vectors = embeddings["sparse"]

            summary_bytes = summary.encode('utf-8')
            safe_summary = summary_bytes[:2040].decode('utf-8', 'ignore') if len(summary_bytes) > 2040 else summary

            def safe_trunc(val, limit):
                """Truncate to fit within byte limit without breaking UTF-8."""
                if not val:
                    return ""
                v_str = str(val)
                v_bytes = v_str.encode('utf-8')
                if len(v_bytes) <= limit:
                    return v_str
                while len(v_str.encode('utf-8')) > limit and v_str:
                    v_str = v_str[:-1]
                return v_str

            data = [
                texts,
                [c["source"] for c in batch_chunks],
                [c.get("page", 1) for c in batch_chunks],
                [safe_summary for _ in batch_chunks],
                [safe_trunc(meta.get("date", "unknown"), 32) for _ in batch_chunks],
                [safe_trunc(meta.get("type", "unknown"), 32) for _ in batch_chunks],
                [safe_trunc(meta.get("authority", "unknown"), 64) for _ in batch_chunks],
                [file_hash for _ in batch_chunks],
                [c.get("is_table", False) for c in batch_chunks],
                [safe_trunc(c.get("chunk_type", "parent"), 16) for c in batch_chunks],
                [safe_trunc(c.get("parent_id", ""), 256) for c in batch_chunks],
                [safe_trunc(c.get("doc_number", ""), 128) for c in batch_chunks],
                [safe_trunc(c.get("doc_id", ""), 256) for c in batch_chunks],
                [safe_trunc(c.get("chunk_id", ""), 512) for c in batch_chunks],
                [json.dumps(c.get("bbox", [0, 0, 1000, 1000])) for c in batch_chunks],
                [safe_trunc(meta.get("validity_status", "ACTIVE"), 32) for _ in batch_chunks],
                [safe_trunc(meta.get("legal_level", "UNKNOWN"), 32) for _ in batch_chunks],
                [safe_trunc(c.get("hierarchy_path", ""), 1024) for c in batch_chunks],
                [0 for _ in batch_chunks],
                [safe_trunc(meta.get("project_code", "GENERIC"), 64) for _ in batch_chunks],
                [safe_trunc(meta.get("discipline", "UNKNOWN"), 32) for _ in batch_chunks],
                [safe_trunc(meta.get("doc_status", "ACTIVE"), 32) for _ in batch_chunks],
                [meta.get("revision", 0) for _ in batch_chunks],
                [safe_trunc(c.get("synthetic_queries", ""), 4090) for c in batch_chunks],
                [safe_trunc(meta.get("source_category", "KHAC"), 64) for _ in batch_chunks],
                dense_embeddings,
                sparse_vectors,
            ]

            self.collection.insert(data)
            logger.info(f"  Inserted batch {i // BATCH_SIZE + 1} ({len(batch_chunks)} chunks)")

        self.collection.flush()
        logger.info(f"  Successfully Indexed all {len(chunks)} chunks (Hybrid Parent-Child) into Milvus")
