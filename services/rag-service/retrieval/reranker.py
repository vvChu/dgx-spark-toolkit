import asyncio
import logging
import os
import threading
import contextlib
from functools import lru_cache

from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self.model_name = model_name
        self.model = None
        self._load_lock = threading.Lock()
        # CrossEncoder.predict is not safe for concurrent CUDA calls on this singleton.
        self._predict_lock = threading.Lock()
        import torch
        self.device = "cuda" if (torch.cuda.is_available() and os.getenv("FORCE_CPU_RERANKER") != "1") else "cpu"

    def load_model(self):
        if self.model is None:
            with self._load_lock:
                if self.model is None:
                    logger.info(f"Loading reranker model: {self.model_name} on {self.device}")
                    try:
                        self.model = CrossEncoder(self.model_name, device=self.device)
                    except Exception as e:
                        logger.error(f"Failed to load reranker on {self.device}: {e}. Falling back to CPU.")
                        self.device = "cpu"
                        self.model = CrossEncoder(self.model_name, device=self.device)

    def rerank_sync(self, query: str, docs: list[str], top_k: int = 5):
        """Score docs with the local cross-encoder.

        Returns ``(text, score, original_idx)`` sorted by score descending.
        ``original_idx`` is the position in ``docs`` so identical text does not collapse.
        On predict failure, returns the original order with score 0.0 instead of raising.
        """
        self.load_model()
        if not docs:
            return []

        # Truncate only the model input. The returned text stays the original string.
        pairs = [[query, doc[:1500]] for doc in docs]
        try:
            with self._predict_lock:
                scores = self.model.predict(pairs, batch_size=32)
            indexed = [(docs[i], float(scores[i]), i) for i in range(len(docs))]
        except Exception as e:
            logger.warning(
                "Reranker predict failed (%s). Falling back to original candidate order with score 0.0.",
                e,
            )
            limit = max(0, top_k)
            return [(docs[i], 0.0, i) for i in range(min(limit, len(docs)))]

        indexed.sort(key=lambda item: item[1], reverse=True)
        if top_k < 0:
            return []
        return indexed[:top_k]

    async def rerank(self, query: str, docs: list[str], top_k: int = 5):
        """Asynchronous reranking using thread pool to avoid blocking the event loop."""
        return await asyncio.to_thread(self.rerank_sync, query, docs, top_k)


@lru_cache()
def get_reranker():
    return Reranker()
