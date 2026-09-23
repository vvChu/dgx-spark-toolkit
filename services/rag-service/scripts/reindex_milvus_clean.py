#!/usr/bin/env python3
"""Clean Streaming Re-Indexing Script for Milvus legal_chunks collection.

Recreates the Milvus collection from sanitized JSON exports using file-by-file
streaming to guarantee zero memory bloat and zero OOM killer risks. Generates fresh
BGE-M3 hybrid embeddings (dense + sparse) on CPU, completely reserving GPU VRAM
for vLLM.

Usage (inside rag-service container):
    docker compose exec rag-service python3 scripts/reindex_milvus_clean.py

Options:
    --dry-run       Validate chunks and show summary without modifying Milvus
    --batch-size N  Batch size for embedding and insertion (default: 16)
    --max-length N  Max sequence length for BGE-M3 (default: 512)
    --device DEV    Device to use for embedding (default: cpu)
    --no-drop       Do not drop existing collection (append/upsert instead)
"""
import os
import sys
import gc
import glob
import json
import time
import logging
import argparse
from pathlib import Path

# Ensure rag-service root (/app or services/rag-service) is in sys.path
_RAG_ROOT = str(Path(__file__).resolve().parent.parent)
if _RAG_ROOT not in sys.path:
    sys.path.insert(0, _RAG_ROOT)
if os.path.exists("/app") and "/app" not in sys.path:
    sys.path.insert(0, "/app")

from core.config import get_settings
from ingestion.normalizers.boilerplate import strip_ai_monologue
from ingestion.legal_taxonomy import classify_source_category
from scripts.comprehensive_audit import is_valid_synthetic_queries

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Re-index Milvus from JSON exports cleanly with streaming.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Milvus")
    parser.add_argument("--batch-size", type=int, default=16, help="Embedding batch size (default: 16)")
    parser.add_argument("--max-length", type=int, default=512, help="Max sequence length (default: 512)")
    parser.add_argument("--device", type=str, default="cpu", choices=["auto", "cuda:0", "cpu"], help="Device for embedding (default: cpu)")
    parser.add_argument("--no-drop", action="store_true", help="Do not drop collection before indexing")
    parser.add_argument("--resume", action="store_true", help="Resume indexing, skipping already indexed files")
    parser.add_argument("--max-chunks", type=int, default=0, help="Max total chunks to index (0 for unlimited, e.g. 528)")
    parser.add_argument(
        "--json-dir",
        type=str,
        default=os.environ.get("EXPORT_JSON_DIR", "/app/exports/json" if os.path.exists("/app/exports/json") else str(Path.home() / "Public" / "exports" / "json")),
        help="Path to JSON exports directory",
    )
    return parser.parse_args()


def load_file_chunks(fpath: str) -> tuple[list[dict], dict]:
    """Load and sanitize chunks from a single JSON export file."""
    stats = {
        "total_chunks": 0,
        "parent_chunks": 0,
        "child_chunks": 0,
        "valid_synthetic_queries": 0,
        "source_category": "UNKNOWN",
    }
    try:
        data = json.loads(Path(fpath).read_text(errors="replace"))
    except Exception as e:
        logger.warning(f"Failed to read {fpath}: {e}")
        return [], stats

    meta = data.get("metadata", {})
    doc_id = data.get("doc_id", "")
    orig_path = data.get("original_path", "") or Path(fpath).name
    summary = data.get("summary", "")
    doc_date = meta.get("date", "unknown")
    doc_type = meta.get("type", "unknown")
    authority = meta.get("authority", "unknown")
    legal_level = meta.get("legal_level", "UNKNOWN")
    source_category = classify_source_category(orig_path)
    stats["source_category"] = source_category

    entities = []
    for chunk in data.get("chunks", []):
        stats["total_chunks"] += 1
        ctype = chunk.get("chunk_type", "parent")
        if ctype == "parent":
            stats["parent_chunks"] += 1
        elif ctype == "child":
            stats["child_chunks"] += 1

        # Sanitize text
        text = strip_ai_monologue(chunk.get("text", "")).strip()

        # Sanitize & validate synthetic_queries
        raw_sq = chunk.get("synthetic_queries", "")
        sq = strip_ai_monologue(raw_sq).strip()
        if not is_valid_synthetic_queries(sq):
            sq = ""
        else:
            stats["valid_synthetic_queries"] += 1

        entity = {
            "text": text[:14000],
            "source": str(chunk.get("source", orig_path)),
            "page": int(chunk.get("page", 1)),
            "summary": str(summary)[:2048],
            "doc_date": str(doc_date),
            "doc_type": str(doc_type),
            "authority": str(authority),
            "file_hash": str(chunk.get("file_hash", "")),
            "is_table": bool(chunk.get("is_table", False)),
            "chunk_type": str(ctype),
            "parent_id": str(chunk.get("parent_id", "")),
            "doc_number": str(chunk.get("doc_number", meta.get("doc_number", ""))),
            "doc_id": str(doc_id),
            "chunk_id": str(chunk.get("chunk_id", "")),
            "bbox": str(chunk.get("bbox", "[0,0,1000,1000]")),
            "validity_status": str(meta.get("validity_status", "ACTIVE")),
            "legal_level": str(legal_level),
            "hierarchy_path": str(chunk.get("hierarchy_path", "")),
            "citation_count": int(chunk.get("citation_count", 0)),
            "project_code": str(chunk.get("project_code", "GENERIC")),
            "discipline": str(chunk.get("discipline", meta.get("discipline", "UNKNOWN"))),
            "doc_status": str(meta.get("validity_status", "ACTIVE")),
            "revision": int(chunk.get("revision", 0)),
            "synthetic_queries": sq,
            "source_category": source_category,
        }
        entities.append(entity)

    return entities, stats


def scan_dataset_summary(files: list[str]) -> dict:
    """Fast scan of the dataset metadata without holding all entities in memory."""
    total_stats = {
        "files": len(files),
        "total_chunks": 0,
        "parent_chunks": 0,
        "child_chunks": 0,
        "valid_synthetic_queries": 0,
        "source_categories": {},
    }
    for f in files:
        try:
            d = json.loads(Path(f).read_text(errors="replace"))
        except Exception:
            continue
        orig = d.get("original_path", "") or Path(f).name
        cat = classify_source_category(orig)
        for c in d.get("chunks", []):
            total_stats["total_chunks"] += 1
            ctype = c.get("chunk_type", "parent")
            if ctype == "parent":
                total_stats["parent_chunks"] += 1
                if is_valid_synthetic_queries(strip_ai_monologue(c.get("synthetic_queries", ""))):
                    total_stats["valid_synthetic_queries"] += 1
            elif ctype == "child":
                total_stats["child_chunks"] += 1
            total_stats["source_categories"][cat] = total_stats["source_categories"].get(cat, 0) + 1
    return total_stats


def create_hybrid_collection(client, collection_name: str) -> None:
    """Create collection schema with dense (1024 dims) and sparse (SPARSE_FLOAT_VECTOR) fields."""
    from pymilvus import MilvusClient, DataType
    schema = MilvusClient.create_schema(auto_id=True, enable_dynamic_field=True)
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=1024)
    schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)

    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(field_name="vector", metric_type="COSINE", index_type="AUTOINDEX")
    index_params.add_index(field_name="sparse_vector", metric_type="IP", index_type="SPARSE_INVERTED_INDEX")

    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )


def main():
    args = parse_args()
    settings = get_settings()
    collection_name = settings.MILVUS_COLLECTION

    files = sorted(glob.glob(os.path.join(args.json_dir, "*.json")))
    files = [f for f in files if not f.endswith(".bak")]

    logger.info(f"Target Milvus: {settings.MILVUS_HOST}:{settings.MILVUS_PORT}, collection: {collection_name}")
    logger.info(f"Scanning dataset in {args.json_dir}: found {len(files)} files")

    stats = scan_dataset_summary(files)
    logger.info("=== Loaded Dataset Summary ===")
    logger.info(f"  Files: {stats['files']}")
    logger.info(f"  Total chunks: {stats['total_chunks']}")
    logger.info(f"  Parent chunks: {stats['parent_chunks']}")
    logger.info(f"  Child chunks: {stats['child_chunks']}")
    sq_rate = (stats['valid_synthetic_queries'] / max(stats['parent_chunks'], 1)) * 100
    logger.info(f"  Valid synthetic queries on parents: {stats['valid_synthetic_queries']}/{stats['parent_chunks']} ({sq_rate:.1f}%)")
    logger.info(f"  Source categories: {stats['source_categories']}")

    if args.dry_run:
        logger.info("DRY RUN completed. Exiting without modifying Milvus.")
        return

    from pymilvus import MilvusClient

    client = MilvusClient(uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}")

    try:
        # Step 1: Drop & recreate collection (unless --no-drop or --resume)
        existing_counts = {}
        if args.resume:
            args.no_drop = True

        if not args.no_drop:
            if client.has_collection(collection_name):
                logger.info(f"Dropping contaminated collection: {collection_name}")
                client.drop_collection(collection_name)

            logger.info(f"Creating pristine collection with native hybrid schema: {collection_name}")
            create_hybrid_collection(client, collection_name)
        else:
            if not client.has_collection(collection_name):
                logger.info(f"Collection {collection_name} does not exist. Creating with native hybrid schema...")
                create_hybrid_collection(client, collection_name)
            elif args.resume:
                try:
                    res = client.query(collection_name=collection_name, filter="", output_fields=["source"], limit=16384)
                    for r in res:
                        s = r.get("source", "")
                        existing_counts[s] = existing_counts.get(s, 0) + 1
                    logger.info(f"Resume mode: Found {len(res)} chunks across {len(existing_counts)} sources already in Milvus.")
                except Exception as e:
                    logger.warning(f"Could not query existing items in resume mode: {e}")

        # Step 2: Initialize embedding model
        import torch
        from FlagEmbedding import BGEM3FlagModel

        device = getattr(args, "device", "cpu")
        if device == "auto":
            device = "cuda:0" if torch.cuda.is_available() and os.getenv("FORCE_CPU_EMBEDDING") != "1" else "cpu"

        use_fp16 = device.startswith("cuda")
        if device == "cpu":
            num_threads = min(int(os.environ.get("OMP_NUM_THREADS", "4")), 4)
            torch.set_num_threads(num_threads)
            logger.info(f"Configured PyTorch CPU threads: {num_threads}")

        logger.info(f"Initializing BGE-M3 embedding model on {device} (fp16={use_fp16})...")
        bg_model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=use_fp16, devices=device)

        # Step 3: Stream file by file
        total_chunks = stats["total_chunks"]
        batch_size = args.batch_size
        logger.info(f"Streaming {len(files)} files ({total_chunks} chunks) in batches of {batch_size} (device={device})...")

        t0 = time.time()
        inserted_total = 0
        doc_prefix = "Represent this Vietnamese legal document for retrieval: "

        for f_idx, fpath in enumerate(files, 1):
            if args.max_chunks > 0 and inserted_total >= args.max_chunks:
                logger.info(f"Reached --max-chunks limit ({args.max_chunks}). Stopping file processing.")
                break
            fname = Path(fpath).name
            file_entities, f_stats = load_file_chunks(fpath)
            f_count = len(file_entities)
            source_name = file_entities[0]["source"] if file_entities else ""
            t_file0 = time.time()

            if args.resume and source_name:
                already_in = existing_counts.get(source_name, 0)
                if already_in == f_count:
                    logger.info(f"[{f_idx}/{len(files)}] {fname}: Already fully indexed ({already_in}/{f_count} chunks). Skipping.")
                    inserted_total += f_count
                    continue
                elif already_in > 0:
                    logger.info(f"[{f_idx}/{len(files)}] {fname}: Partial index detected ({already_in}/{f_count} chunks). Deleting partial rows...")
                    client.delete(collection_name=collection_name, filter=f'source == "{source_name}"')

            for i in range(0, f_count, batch_size):
                if args.max_chunks > 0 and inserted_total >= args.max_chunks:
                    break
                batch = file_entities[i:i + batch_size]
                if args.max_chunks > 0 and inserted_total + len(batch) > args.max_chunks:
                    batch = batch[:args.max_chunks - inserted_total]
                texts = [b["text"] for b in batch]
                prefixed = [doc_prefix + t for t in texts]

                embeddings = bg_model.encode(
                    prefixed,
                    batch_size=batch_size,
                    max_length=args.max_length,
                    return_dense=True,
                    return_sparse=True,
                    return_colbert_vecs=False,
                )

                dense_vectors = embeddings["dense_vecs"].tolist()
                sparse_vectors = embeddings["lexical_weights"]

                for j, entity in enumerate(batch):
                    entity["vector"] = dense_vectors[j]
                    entity["sparse_vector"] = {int(k) if str(k).isdigit() else str(k): float(v) for k, v in sparse_vectors[j].items()}

                for attempt in range(3):
                    try:
                        client.insert(collection_name=collection_name, data=batch)
                        break
                    except Exception as e:
                        if attempt == 2:
                            raise
                        logger.warning(f"Insert failed: {e}. Retrying in 2s...")
                        time.sleep(2)
                inserted_total += len(batch)

            # Persist newly inserted segments immediately
            try:
                client.flush(collection_name=collection_name)
            except Exception as e:
                logger.warning(f"Flush after {fname} failed: {e}")

            dt_file = time.time() - t_file0
            elapsed = time.time() - t0
            rate = inserted_total / max(elapsed, 0.1)
            pct = (inserted_total / max(total_chunks, 1)) * 100
            logger.info(
                f"[{f_idx}/{len(files)}] {fname}: {f_count} chunks in {dt_file:.1f}s | "
                f"Progress: {inserted_total}/{total_chunks} ({pct:.1f}%) | Rate: {rate:.1f} chunks/sec"
            )

            # Reclaim heap memory immediately after each file
            del file_entities
            gc.collect()

        # Step 4: Load collection into memory
        logger.info(f"Loading collection {collection_name} into memory...")
        client.load_collection(collection_name)

        # Step 5: Verify collection entity count
        col_stats = client.get_collection_stats(collection_name)
        logger.info(f"Collection stats: {col_stats}")
        logger.info(f"✅ Clean Milvus re-indexing complete! {inserted_total} chunks indexed into {collection_name}.")

    finally:
        client.close()


if __name__ == "__main__":
    main()
