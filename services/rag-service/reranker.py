from sentence_transformers import CrossEncoder
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

class Reranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self.model = None

    def load_model(self):
        if self.model is None:
            logger.info(f"Loading reranker model: {self.model_name}")
            self.model = CrossEncoder(self.model_name)

    def rerank(self, query: str, docs: list[str], top_k: int = 3):
        """
        Rerank a list of documents based on the query.
        Returns a list of (doc, score) tuples, sorted by score.
        """
        self.load_model()
        if not docs:
            return []
            
        pairs = [[query, doc] for doc in docs]
        scores = self.model.predict(pairs)
        
        # Zip and sort
        doc_scores = list(zip(docs, scores))
        doc_scores.sort(key=lambda x: x[1], reverse=True)
        
        return doc_scores[:top_k]

@lru_cache()
def get_reranker():
    return Reranker()
