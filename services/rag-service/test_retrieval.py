"""
Direct retrieval quality test: embed a query and search Milvus
to verify table chunks are now coherent and findable.
"""
import sys, asyncio
sys.path.insert(0, '/app')
from ingestion.text_normalizer import rejoin_paragraphs

# Import BGE-M3 for embedding
from retrieval.embeddings.bge_m3_hybrid import BGEM3HybridEmbedder
from core.config import get_settings
from pymilvus import connections, Collection, MilvusClient

s = get_settings()
connections.connect(host=s.MILVUS_HOST, port=str(s.MILVUS_PORT))
coll = Collection(s.MILVUS_COLLECTION)
coll.load()

print(f"Collection: {s.MILVUS_COLLECTION}")
print(f"Entities: {coll.num_entities}")

# Init embedder
embedder = BGEM3HybridEmbedder()

queries = [
    "lực nén hướng kính vành 1.10",       # from QCVN_113 Bảng 2
    "mức phát thải NOx xe ô tô mức 5",    # from QCVN_109_2024
    "kích thước vành danh nghĩa mã 1.20", # from QCVN_113 Bảng A.2
]

for q in queries:
    print(f"\n{'='*55}")
    print(f"Query: {q}")
    print(f"{'='*55}")

    vecs = embedder.encode([q])
    dense_v = vecs["dense"][0].tolist()
    sparse_v = vecs["sparse"][0]

    from pymilvus import AnnSearchRequest, WeightedRanker
    req_dense = AnnSearchRequest([dense_v], "vector", {"metric_type": "COSINE", "params": {"nprobe": 10}}, limit=5)
    sparse_dict = {int(k): float(v) for k, v in zip(sparse_v.indices, sparse_v.data)}
    req_sparse = AnnSearchRequest([sparse_dict], "sparse_vector", {"metric_type": "IP", "params": {"drop_ratio_search": 0.2}}, limit=5)

    results = coll.hybrid_search(
        [req_dense, req_sparse],
        rerank=WeightedRanker(0.7, 0.3),
        limit=3,
        output_fields=["text", "doc_number", "chunk_type"]
    )

    for i, hit in enumerate(results[0], 1):
        text = hit.entity.get("text", "")[:200]
        doc = hit.entity.get("doc_number", "?")
        ctype = hit.entity.get("chunk_type", "?")
        score = hit.distance
        has_table = '|---|' in text or '| ---' in text
        print(f"\n  Hit {i} [score={score:.4f}] doc={doc} type={ctype} {'📊TABLE' if has_table else ''}")
        print(f"  {text[:180]}")
