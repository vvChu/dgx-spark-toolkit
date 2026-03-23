from FlagEmbedding import BGEM3FlagModel
import numpy as np
import torch
import logging

logger = logging.getLogger(__name__)


class BGE_M3_HybridEmbedding:
    def __init__(self):
        import os
        self.device = 'cuda' if torch.cuda.is_available() and os.getenv("FORCE_CPU_EMBEDDING") != "1" else 'cpu'
        logger.info(f"Initializing BAAI/bge-m3 Hybrid (Dense + Native Sparse) on {self.device}...")
        self.model = BGEM3FlagModel(
            'BAAI/bge-m3',
            use_fp16=(self.device == 'cuda'),
            device=self.device
        )
        self.dim = 1024

    def encode(self, texts: list[str], batch_size=16) -> list[dict]:
        """Provides backward compatible list format for downstream components if needed"""
        if isinstance(texts, str):
            texts = [texts]

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False
        )

        results = []
        dense_vecs = embeddings['dense_vecs'].tolist()
        sparse_vecs = self._convert_sparse_to_milvus(embeddings['lexical_weights'])

        for i in range(len(texts)):
            results.append({
                "dense": dense_vecs[i],
                "sparse": sparse_vecs[i]
            })

        return results

    # [P1-4] Instruction prefixes for domain-specific embedding quality
    _DOC_PREFIX = "Represent this Vietnamese legal document for retrieval: "
    _QUERY_PREFIX = "Represent this sentence for searching Vietnamese legal documents: "

    def embed_documents(self, texts: list[str], batch_size=16) -> dict:
        """Returns the dictionary format suitable for batch collection operations"""
        if isinstance(texts, str):
            texts = [texts]

        # [P1-4] Add instruction prefix for better domain-specific embeddings
        prefixed = [self._DOC_PREFIX + t for t in texts]

        embeddings = self.model.encode(
            prefixed,
            batch_size=batch_size,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False
        )

        return {
            "dense": embeddings['dense_vecs'].tolist(),
            "sparse": self._convert_sparse_to_milvus(embeddings['lexical_weights'])
        }

    def embed_query(self, query: str) -> dict:
        """Embed a single query returning dict format"""
        # [P1-4] Add instruction prefix for query
        prefixed = self._QUERY_PREFIX + query

        embeddings = self.model.encode(
            [prefixed],
            batch_size=1,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False
        )

        return {
            "dense": np.array(embeddings['dense_vecs'])[0].tolist(),
            "sparse": self._convert_sparse_to_milvus(embeddings['lexical_weights'])[0]
        }

    def _convert_sparse_to_milvus(self, lexical_weights: list[dict]) -> list[dict]:
        """Convert BGE-M3 lexical weights to Milvus SparseVector format (dict[int, float])"""
        sparse_list = []
        for doc_weights in lexical_weights:
            # Milvus expects integer keys, but BGE-M3 lexical keys are already string versions of integers
            # So we cast them appropriately.
            sparse_dict = {int(k): float(v) for k, v in doc_weights.items()}
            sparse_list.append(sparse_dict)
        return sparse_list
