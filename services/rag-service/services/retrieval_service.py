"""RetrievalService Facade module — subclass alias delegating directly to SearchPipeline."""
import logging
from retrieval.search_pipeline import SearchPipeline, SearchContext, get_embedding_model
from retrieval.query_tracer import QueryTracer

logger = logging.getLogger(__name__)


class RetrievalService(SearchPipeline):
    """Backward-compatible facade subclassing deep SearchPipeline directly."""
    pass

