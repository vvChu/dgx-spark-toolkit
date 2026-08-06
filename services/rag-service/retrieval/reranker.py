import asyncio
import logging
import os
import threading
import contextlib
from functools import lru_cache

from sentence_transformers import CrossEncoder

from core.vram_accelerator import vram_accelerate

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self.model_name = model_name
        self.model = None
        self._load_lock = threading.Lock()
        self.force_cpu = os.getenv("FORCE_CPU_RERANKER") == "1"
        self.device = "cpu"

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
        """Synchronous reranking (internal)."""
        self.load_model()
        if not docs:
            return []

        pairs = [[query, doc] for doc in docs]
        force_cpu = getattr(self, "force_cpu", True)
        with vram_accelerate(self.model, min_vram_gb=2.0) if not force_cpu else contextlib.nullcontext():
            scores = self.model.predict(pairs, batch_size=32)

        doc_scores = list(zip(docs, scores))
        doc_scores.sort(key=lambda x: x[1], reverse=True)
        return doc_scores[:top_k]

    async def rerank(self, query: str, docs: list[str], top_k: int = 5):
        """Asynchronous reranking using thread pool to avoid blocking the event loop."""
        return await asyncio.to_thread(self.rerank_sync, query, docs, top_k)


@lru_cache()
def get_reranker():
    return Reranker()
