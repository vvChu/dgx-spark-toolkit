from pymilvus import AsyncMilvusClient, AnnSearchRequest, RRFRanker
import json
import re
import logging
from core.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)

# Strip characters that could break a Milvus string literal in a filter expression
_MILVUS_STR_UNSAFE = re.compile(r'["\\\x00-\x1f]')


def _sanitize_pid(pid: str) -> str:
    return _MILVUS_STR_UNSAFE.sub('', str(pid))

class MilvusRepository:
    def __init__(self, client: AsyncMilvusClient):
        self.client = client
        self.collection_name = settings.MILVUS_COLLECTION

    async def hybrid_search(self, query_vector: list, sparse_vector: dict, limit: int = 10, expr: str = None):
        """Perform hybrid search utilizing Milvus RRF."""
        # Dense Search Request
        search_params_dense = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        req_dense = AnnSearchRequest([query_vector], "vector", search_params_dense, limit=limit, expr=expr)
        
        # Sparse Search Request
        search_params_sparse = {"metric_type": "IP", "params": {"drop_ratio_search": 0.2}}
        req_sparse = AnnSearchRequest([sparse_vector], "sparse_vector", search_params_sparse, limit=limit, expr=expr)

        # Hybrid Search with RRFRanker
        results = await self.client.hybrid_search(
            collection_name=self.collection_name,
            reqs=[req_dense, req_sparse],
            ranker=RRFRanker(),
            limit=limit,
            output_fields=["text", "source", "page", "summary", "doc_date", "doc_type", "authority", "chunk_type", "parent_id", "is_table", "doc_number", "doc_id", "chunk_id", "bbox", "validity_status", "project_code", "discipline", "hierarchy_path", "doc_status", "revision", "synthetic_queries", "legal_level", "citation_count"]
        )
        return results
    
    async def get_parent_chunks(self, parent_ids: list):
        """Retrieve parent texts given a list of parent_ids."""
        if not parent_ids:
            return []
        
        # Sanitize each parent_id before interpolating into the filter expression
        parent_id_str = "[" + ",".join(f'"{_sanitize_pid(pid)}"' for pid in parent_ids) + "]"
        query_expr = f'parent_id in {parent_id_str} and chunk_type == "parent"'
        
        results = await self.client.query(
            collection_name=self.collection_name, 
            filter=query_expr, 
            output_fields=["parent_id", "text"]
        )
        return results

    async def cache_search(self, query_vector: list, threshold: float = 0.98):
        """Search the semantic cache for hits."""
        try:
            results = await self.client.search(
                collection_name="semantic_cache",
                data=[query_vector],
                anns_field="vector",
                search_params={"metric_type": "IP"},
                limit=1,
                output_fields=["answer"]
            )
            if results and results[0] and results[0][0].score > threshold:
                return results[0][0].entity.get("answer"), results[0][0].score
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
        return None, None

    async def update_doc_validity(self, doc_id: str, new_status: str):
        """Update the validity_status for all chunks of a document in Milvus."""
        try:
            # 1. Find all chunks for this doc_id
            # Note: We need ALL fields that we want to preserve because upsert replaces the record
            fields = ["id", "text", "source", "page", "summary", "doc_date", "doc_type", "authority", 
                      "chunk_type", "parent_id", "is_table", "doc_number", "doc_id", "chunk_id",
                      "bbox", "validity_status", "project_code", "discipline", "hierarchy_path",
                      "doc_status", "revision", "synthetic_queries", "file_hash",
                      "vector", "sparse_vector"]
            
            # [Change 5] Filter by doc_id field (not doc_number which stores raw legal number)
            safe_doc_id = _sanitize_pid(doc_id)
            expr = f"doc_id == '{safe_doc_id}'"
            
            # Querying in batches if necessary, but 1000 should be enough for most docs
            results = await self.client.query(
                collection_name=self.collection_name,
                filter=expr,
                output_fields=fields,
                limit=1000
            )
            
            if not results:
                logger.info(f"No chunks found in Milvus for doc_id: {doc_id}")
                return

            # 2. Update status and prepare for upsert
            for entity in results:
                entity["validity_status"] = new_status

            # 3. Upsert back to Milvus
            await self.client.upsert(
                collection_name=self.collection_name,
                data=results
            )
            logger.info(f"Successfully updated status to {new_status} for {len(results)} chunks in Milvus (doc_id: {doc_id})")
            
        except Exception as e:
            logger.error(f"Failed to update doc validity in Milvus: {e}")
            raise
