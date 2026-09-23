from pymilvus import AsyncMilvusClient, AnnSearchRequest, RRFRanker, DataType
import json
import re
import logging
from core.config import get_settings

logger = logging.getLogger(__name__)

# Strip characters that could break a Milvus string literal in a filter expression
_MILVUS_STR_UNSAFE = re.compile(r'["\\\x00-\x1f]')


def _sanitize_pid(pid: str) -> str:
    return _MILVUS_STR_UNSAFE.sub('', str(pid))


class MilvusRepository:
    def __init__(self, client: AsyncMilvusClient):
        self.client = client
        self.collection_name = get_settings().MILVUS_COLLECTION

    async def hybrid_search(self, query_vector: list, sparse_vector: dict, limit: int = 10, expr: str = None):
        """Perform hybrid search utilizing Milvus RRF."""
        # Dense Search Request
        search_params_dense = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        req_dense = AnnSearchRequest([query_vector], "vector", search_params_dense, limit=limit, expr=expr)

        # Sparse Search Request
        search_params_sparse = {"metric_type": "IP", "params": {"drop_ratio_search": 0.2}}
        req_sparse = AnnSearchRequest([sparse_vector], "sparse_vector", search_params_sparse, limit=limit, expr=expr)

        try:
            # Hybrid Search with RRFRanker
            results = await self.client.hybrid_search(
                collection_name=self.collection_name,
                reqs=[req_dense, req_sparse],
                ranker=RRFRanker(),
                limit=limit,
                output_fields=["text", "source", "page", "summary", "doc_date", "doc_type", "authority", "chunk_type", "parent_id", "is_table", "doc_number", "doc_id", "chunk_id", "bbox", "validity_status", "project_code", "discipline", "hierarchy_path", "doc_status", "revision", "synthetic_queries", "legal_level", "citation_count"]
            )
            return results
        except Exception as e:
            if "sparse_vector" in str(e):
                logger.warning(f"Hybrid search sparse_vector missing/failed ({e}), falling back to dense-only search")
                dense_results = await self.client.search(
                    collection_name=self.collection_name,
                    data=[query_vector],
                    anns_field="vector",
                    search_params=search_params_dense,
                    limit=limit,
                    filter=expr,
                    output_fields=["text", "source", "page", "summary", "doc_date", "doc_type", "authority", "chunk_type", "parent_id", "is_table", "doc_number", "doc_id", "chunk_id", "bbox", "validity_status", "project_code", "discipline", "hierarchy_path", "doc_status", "revision", "synthetic_queries", "legal_level", "citation_count"]
                )
                return dense_results
            raise

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

    async def insert_chunks(self, chunks: list) -> int:
        """Insert a batch of document chunks into Milvus collection."""
        if not chunks:
            return 0
        entities = []
        for c in chunks:
            chunk_dict = c.to_dict() if hasattr(c, "to_dict") else dict(c)
            entities.append({
                "text": str(chunk_dict.get("text", ""))[:14000],
                "source": str(chunk_dict.get("source", "")),
                "page": int(chunk_dict.get("page", 1)),
                "summary": str(chunk_dict.get("summary", ""))[:2048],
                "doc_date": str(chunk_dict.get("doc_date", "unknown")),
                "doc_type": str(chunk_dict.get("doc_type", "unknown")),
                "authority": str(chunk_dict.get("authority", "unknown")),
                "file_hash": str(chunk_dict.get("file_hash", "")),
                "is_table": bool(chunk_dict.get("is_table", False)),
                "chunk_type": str(chunk_dict.get("chunk_type", "parent")),
                "parent_id": str(chunk_dict.get("parent_id", "")),
                "doc_number": str(chunk_dict.get("doc_number", "")),
                "doc_id": str(chunk_dict.get("doc_id", "")),
                "chunk_id": str(chunk_dict.get("chunk_id", "")),
                "bbox": str(chunk_dict.get("bbox", "")),
                "validity_status": str(chunk_dict.get("validity_status", "ACTIVE")),
                "legal_level": str(chunk_dict.get("legal_level", "UNKNOWN")),
                "hierarchy_path": str(chunk_dict.get("hierarchy_path", "")),
                "citation_count": int(chunk_dict.get("citation_count", 0)),
                "project_code": str(chunk_dict.get("project_code", "GENERIC")),
                "discipline": str(chunk_dict.get("discipline", "UNKNOWN")),
                "doc_status": str(chunk_dict.get("doc_status", "ACTIVE")),
                "revision": int(chunk_dict.get("revision", 0)),
                "synthetic_queries": str(chunk_dict.get("synthetic_queries", "")),
                "source_category": str(chunk_dict.get("source_category", "KHAC")),
                "vector": chunk_dict.get("vector", [0.0] * 1024),
                "sparse_vector": chunk_dict.get("sparse_vector", {}),
            })
        if entities:
            await self.client.insert(collection_name=self.collection_name, data=entities)
        return len(entities)

    async def delete_by_doc_id(self, doc_id: str) -> None:
        """Delete all chunks belonging to a document from Milvus."""
        safe_doc_id = _sanitize_pid(doc_id)
        filter_expr = f"doc_id == '{safe_doc_id}' or doc_number == '{safe_doc_id}'"
        await self.client.delete(collection_name=self.collection_name, filter=filter_expr)

    async def get_collection_stats(self, collection: str | None = None) -> dict:
        """Return collection statistics (row_count, etc.) without exposing the raw client."""
        target = collection or self.collection_name
        return await self.client.get_collection_stats(target)

    async def ensure_collection_schema(self) -> bool:
        """Ensure the legal chunks collection exists with valid schema and is loaded."""
        try:
            has_col = await self.client.has_collection(self.collection_name)
            if has_col:
                await self.client.load_collection(self.collection_name)
                logger.info(f"Milvus collection '{self.collection_name}' loaded successfully.")
                return True

            schema = AsyncMilvusClient.create_schema(auto_id=True, enable_dynamic_field=True)
            schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
            schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=1024)
            schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)

            index_params = AsyncMilvusClient.prepare_index_params()
            index_params.add_index(field_name="vector", metric_type="COSINE", index_type="AUTOINDEX")
            index_params.add_index(field_name="sparse_vector", metric_type="IP", index_type="SPARSE_INVERTED_INDEX")

            await self.client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index_params,
            )
            logger.info(f"Created and loaded Milvus collection '{self.collection_name}' with native hybrid schema.")
            return True
        except Exception as e:
            logger.warning(f"Could not setup Milvus collection: {e}")
            return False

    async def close(self) -> None:
        """Safely close underlying Milvus client."""
        if self.client:
            try:
                await self.client.close()
            except Exception as e:
                logger.debug(f"Error closing Milvus client: {e}")
