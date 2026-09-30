#!/usr/bin/env python3
"""Re-index Consolidated QCVN 06:2022/BXD (with Sửa đổi 1:2023) into Milvus legal_docs_v12_okf.

Follows Verdict B' and Single Living Standard Invariant:
- Deletes stale 2022 pre-consolidation chunks of QCVN 06 and TT 09.
- Chunks the consolidated qcvn_06_2022_bxd.md using OKF Anchor-Based Chunker.
- Synthesizes 1 legal preamble chunk for Promulgating/Amending Circular 09/2023/TT-BXD.
- Embeds with BGE-M3 (dense 1024 + sparse lexical vector) and inserts into legal_docs_v12_okf.
- Verifies post-condition: Mục 1.1.2 reflects 25m/5000m3 thresholds.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Path setup
SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_DIR = SCRIPT_DIR.parent
ROOT_DIR = SERVICE_DIR.parent.parent

load_dotenv()
load_dotenv(ROOT_DIR / ".env")

if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from pymilvus import DataType, MilvusClient
from ingestion.hub3_bridge import Hub3Bridge, Hub3BundleInfo
from ingestion.pipeline_config import HUB3_LEGAL_PATH
from retrieval.embeddings.bge_m3_hybrid import BGE_M3_HybridEmbedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reindex_qcvn06")

is_docker = os.path.exists("/.dockerenv")
DEFAULT_MILVUS_HOST = "milvus-standalone" if is_docker else "127.0.0.1"
COLLECTION_NAME = os.getenv("MILVUS_OKF_COLLECTION", "legal_docs_v12_okf")
MILVUS_URI = f"http://{os.getenv('MILVUS_HOST', DEFAULT_MILVUS_HOST)}:{os.getenv('MILVUS_PORT', '19530')}"


def main() -> int:
    logger.info("Initializing MilvusClient at %s...", MILVUS_URI)
    client = MilvusClient(uri=MILVUS_URI)

    if not client.has_collection(COLLECTION_NAME):
        logger.error("Collection '%s' does not exist in Milvus!", COLLECTION_NAME)
        return 1

    # Step 1: Query and delete existing chunks of QCVN 06 and TT 09
    logger.info("Checking existing chunks of QCVN 06 and TT 09 in '%s'...", COLLECTION_NAME)
    filter_expr = 'doc_id in ["VBPL/QCVN_06_2022/BXD", "VBPL/09/2023/TT-BXD"] or doc_number in ["QCVN 06:2022/BXD", "09/2023/TT-BXD"]'
    existing = client.query(collection_name=COLLECTION_NAME, filter=filter_expr, output_fields=["count(*)"])
    logger.info("Found existing chunks to delete: %s", existing)

    delete_res = client.delete(collection_name=COLLECTION_NAME, filter=filter_expr)
    logger.info("Deleted stale chunks: %s", delete_res)

    # Step 2: Load QCVN 06 bundle from Hub 3
    default_hub3 = "/app/data/ccba-legal-knowledge" if is_docker else HUB3_LEGAL_PATH
    hub3_path = Path(os.getenv("HUB3_LEGAL_PATH", default_hub3)).resolve()
    bridge = Hub3Bridge(str(hub3_path))
    bundles = bridge.load_master_catalog()
    id_map = bridge.build_canonical_id_map(bundles)

    qcvn06_bundle = next((b for b in bundles if b.slug == "qcvn_06_2022_bxd"), None)
    if not qcvn06_bundle:
        logger.error("Could not find bundle 'qcvn_06_2022_bxd' in %s", hub3_path)
        return 1

    logger.info("Found bundle: %s (%s)", qcvn06_bundle.slug, qcvn06_bundle.canonical_id)

    # Step 3: Chunk consolidated Markdown
    t0_chunk = time.time()
    proc_doc = bridge.convert_bundle_to_processed_doc(qcvn06_bundle, canonical_map=id_map)
    qcvn_chunks = proc_doc.chunks
    chunk_dur = time.time() - t0_chunk
    logger.info("Extracted %d chunks from consolidated QCVN 06 in %.2fs", len(qcvn_chunks), chunk_dur)

    # Step 4: Create 1 Legal Preamble Chunk for TT 09/2023/TT-BXD
    class MockChunk:
        def __init__(self, text, doc_number, doc_id, chunk_id, hierarchy_path):
            self.text = text
            self.source = "legal_docs/01_vbpl/09_2023_tt_bxd/sources/09_2023_tt_bxd.pdf"
            self.page = 1
            self.hierarchy_path = hierarchy_path
            self.is_table = False
            self.chunk_type = "preamble"
            self.parent_id = doc_id
            self.doc_number = doc_number
            self.doc_id = doc_id
            self.chunk_id = chunk_id
            self.bbox = "[]"
            self.validity_status = "ACTIVE"

    tt09_text = (
        "THÔNG TƯ 09/2023/TT-BXD\n"
        "Ban hành Sửa đổi 1:2023 QCVN 06:2022/BXD Quy chuẩn kỹ thuật quốc gia về An toàn cháy cho nhà và công trình.\n\n"
        "Bộ Xây dựng ban hành Thông tư số 09/2023/TT-BXD ngày 16 tháng 10 năm 2023 sửa đổi 1:2023 QCVN 06:2022/BXD.\n"
        "- Điều 1: Ban hành kèm theo Thông tư này 'Sửa đổi 1:2023 QCVN 06:2022/BXD Quy chuẩn kỹ thuật quốc gia về An toàn cháy cho nhà và công trình'.\n"
        "- Điều 2: Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 12 năm 2023. Quy định chuyển tiếp đối với các dự án, công trình đã được cấp giấy chứng nhận thẩm duyệt thiết kế PCCC trước ngày Thông tư này có hiệu lực.\n"
        "- Toàn bộ nội dung kỹ thuật sửa đổi vi sai của Thông tư 09/2023/TT-BXD đã được hợp nhất trực tiếp vào văn bản quy chuẩn hợp nhất QCVN 06:2022/BXD (Sửa đổi 1:2023)."
    )
    tt09_chunk = MockChunk(
        text=tt09_text,
        doc_number="09/2023/TT-BXD",
        doc_id="VBPL/09/2023/TT-BXD",
        chunk_id="VBPL/09/2023/TT-BXD::p1::preamble",
        hierarchy_path="Thông tư 09/2023/TT-BXD > Lời mở đầu",
    )

    all_items: List[tuple[Any, Any]] = [(qcvn06_bundle, c) for c in qcvn_chunks]
    # For TT 09 mock bundle
    class MockBundle:
        effective_date = "2023-12-01"
        issued_date = "2023-10-16"
        doc_type = "Thông tư"
        issued_by = "Bộ Xây dựng"
        pdf_sha256 = ""
        category = "01_vbpl"
        validity_status = "ACTIVE"
    all_items.append((MockBundle(), tt09_chunk))

    # Step 5: Embed with BGE-M3
    logger.info("Initializing BGE-M3 Hybrid Embedder...")
    embedder = BGE_M3_HybridEmbedding()

    batch_size = 32
    total_inserted = 0
    t0_embed = time.time()

    for i in range(0, len(all_items), batch_size):
        batch = all_items[i : i + batch_size]
        texts = [c.text for _, c in batch]

        emb_res = embedder.embed_documents(texts, batch_size=batch_size)
        dense_vecs = emb_res["dense"]
        sparse_vecs = emb_res["sparse"]

        entities = []
        for idx_in_batch, (b, c) in enumerate(batch):
            sparse_raw = sparse_vecs[idx_in_batch]
            clean_sparse: Dict[int, float] = {}
            if isinstance(sparse_raw, dict):
                for k, v in sparse_raw.items():
                    try:
                        ik = int(k)
                        if ik >= 0:
                            clean_sparse[ik] = float(v)
                    except (ValueError, TypeError):
                        continue

            entities.append({
                "text": str(c.text)[:14000],
                "source": str(c.source),
                "page": int(c.page),
                "summary": str(c.hierarchy_path or "")[:2048],
                "doc_date": str(b.effective_date or b.issued_date or "unknown"),
                "doc_type": str(b.doc_type or "unknown"),
                "authority": str(b.issued_by or "unknown"),
                "file_hash": str(b.pdf_sha256 or ""),
                "is_table": bool(c.is_table),
                "chunk_type": str(c.chunk_type),
                "parent_id": str(c.parent_id),
                "doc_number": str(c.doc_number),
                "doc_id": str(c.doc_id),
                "chunk_id": str(c.chunk_id),
                "bbox": str(c.bbox),
                "validity_status": str(c.validity_status),
                "legal_level": str(b.category),
                "hierarchy_path": str(c.hierarchy_path),
                "citation_count": 0,
                "project_code": "LEGAL_OKF",
                "discipline": "LEGAL",
                "doc_status": str(b.validity_status),
                "revision": 0,
                "synthetic_queries": "",
                "source_category": str(b.category),
                "vector": dense_vecs[idx_in_batch],
                "sparse_vector": clean_sparse,
            })

        ins_res = client.insert(collection_name=COLLECTION_NAME, data=entities)
        total_inserted += ins_res.get("insert_count", len(entities))
        logger.info("Inserted %d/%d chunks into Milvus...", total_inserted, len(all_items))

    embed_dur = time.time() - t0_embed
    logger.info("Completed embedding and insertion in %.2fs (total inserted: %d)", embed_dur, total_inserted)

    # Step 6: Verification Gate
    logger.info("Running post-insertion verification gate...")
    v_res = client.query(
        collection_name=COLLECTION_NAME,
        filter='chunk_id == "VBPL/QCVN_06_2022/BXD::p1::muc-1-1-2"',
        output_fields=["chunk_id", "text"],
    )
    if not v_res:
        logger.error("VERIFICATION FAILED: Chunk 'VBPL/QCVN_06_2022/BXD::p1::muc-1-1-2' not found!")
        return 1

    chunk_text = v_res[0]["text"]
    assert "7 tầng" in chunk_text, "Missing '7 tầng' in Mục 1.1.2!"
    assert "25 m" in chunk_text or "25m" in chunk_text, "Missing '25 m' in Mục 1.1.2!"
    assert "5 000 m3" in chunk_text or "5000" in chunk_text, "Missing '5 000 m3' in Mục 1.1.2!"
    assert "30% tổng diện tích sàn" not in chunk_text, "Stale '30% tổng diện tích sàn' still present in Mục 1.1.2!"

    print("\n========================================================")
    print(" VERIFICATION SUCCESS: CONSOLIDATED QCVN 06 RE-INDEXED! ")
    print("========================================================")
    print(f"Collection       : {COLLECTION_NAME}")
    print(f"Total Chunks     : {total_inserted}")
    print(f"Mục 1.1.2 Sample : {chunk_text[:250]}...")
    print("========================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
