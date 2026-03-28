"""Knowledge graph mixin — relationship extraction + Neo4j sync."""
import asyncio
import logging
import re
import time

from ingestion.json_parser import extract_json_from_response
from ingestion.pipeline_config import RELATIONSHIP_MODEL

logger = logging.getLogger(__name__)


class GraphMixin:
    """Methods for legal relationship extraction and Neo4j graph sync."""

    def parse_relationships_llm(self, text):
        """Extract legal relationships using LLM for higher precision with Regex fallback."""
        try:
            payload = {
                "model": RELATIONSHIP_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a Vietnamese legal knowledge graph expert. Extract relationships between documents as JSON. Do NOT include any 'Thinking Process', 'Analysis', or preamble. NO text before or after the JSON block. Start exactly with '{' and end exactly with '}'."},
                    {"role": "user", "content": f"Extract relationship JSON from this text (Respond ONLY with JSON):\n\n{text[:6000]}"}
                ],
                "max_tokens": 4096,
                "temperature": 0.0,
            }
            # Only add vLLM-specific params for local models
            if RELATIONSHIP_MODEL in ("rag-core", "qwen3.5-35b", "rag-light"):
                payload["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
            headers = {"Authorization": f"Bearer {self.vision.api_key}"}
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    resp = self._http_client.post(self.vision.api_url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        time.sleep(5 * (2 ** attempt))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    rels = extract_json_from_response(data)
                    if rels:
                        for key in ["replaces", "amends", "references", "guides"]:
                            if key not in rels or not isinstance(rels[key], list):
                                rels[key] = []
                        logger.info(f"  LLM extracted relationships: {rels}")
                        return rels
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Relationship extraction failed after {max_retries} attempts: {e}")
                        return self.parse_relationships(text)
                    time.sleep(5 * (2 ** attempt))
        except Exception as e:
            logger.warning(f"LLM relationship extraction failed: {e}. Falling back to Regex.")
            return self.parse_relationships(text)

    def parse_relationships(self, text):
        """Extract legal relationships from text using regex."""
        rels = {"replaces": [], "amends": [], "references": [], "guides": []}
        doc_pattern = r'(?:số\s+)?(\d+/\d+/[A-ZĐ0-9-]+|\d+/\d+)'

        replaces = re.findall(rf'(?:thay\s+thế|bãi\s+bỏ)(?:.*?){doc_pattern}', text, re.IGNORECASE | re.DOTALL)
        rels["replaces"].extend([r.strip() for r in replaces])

        amends = re.findall(rf'(?:sửa\s+đổi|bổ\s+sung)(?:.*?){doc_pattern}', text, re.IGNORECASE | re.DOTALL)
        rels["amends"].extend([r.strip() for r in amends])

        refs = re.findall(rf'(?:Căn\s+cứ|Theo|Tại)(?:.*?){doc_pattern}', text, re.IGNORECASE | re.DOTALL)
        rels["references"].extend([r.strip() for r in refs])

        guides = re.findall(rf'(?:Hướng\s+dẫn)(?:.*?){doc_pattern}', text, re.IGNORECASE | re.DOTALL)
        rels["guides"].extend([r.strip() for r in guides])

        for k in rels:
            rels[k] = list(set(rels[k]))
        return rels

    def sync_to_graph(self, doc_id, meta, relationships):
        """Sync Document Nodes and Edges to Neo4j."""
        with self.neo4j_driver.session() as session:
            session.run(
                """
                MERGE (d:Document {id: $id})
                SET d.doc_type = $type, d.authority = $auth, d.date = $date,
                    d.doc_number = $doc_number,
                    d.status = $status, d.file_name = $file_name,
                    d.validity_status = $validity_status,
                    d.project_code = $project_code,
                    d.discipline = $discipline,
                    d.revision = $revision,
                    d.source_category = $source_category
                """,
                id=doc_id, type=meta.get("type", "unknown"), auth=meta.get("authority", "unknown"),
                date=meta.get("date", "unknown"), file_name=meta.get("file_name", doc_id),
                doc_number=meta.get("doc_number", ""),
                status=meta.get("doc_status", "ACTIVE"),
                validity_status=meta.get("validity_status", "ACTIVE"),
                project_code=meta.get("project_code", "GENERIC"),
                discipline=meta.get("discipline", "UNKNOWN"),
                revision=meta.get("revision", 0),
                source_category=meta.get("source_category", "KHAC")
            )

            for target_id in relationships["replaces"]:
                session.run(
                    """
                    MATCH (source:Document {id: $source_id})
                    MERGE (target:Document {id: $target_id})
                    SET target.status = 'OUTDATED'
                    MERGE (source)-[:REPLACES]->(target)
                    """,
                    source_id=doc_id, target_id=target_id
                )
                # Cascading status sync
                try:
                    logger.info(f"  Triggering cascading status sync for replaced doc: {target_id}")
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.ensure_future(self.lifecycle_service.sync_document_status(target_id, "OUTDATED"))
                    except RuntimeError:
                        asyncio.run(self.lifecycle_service.sync_document_status(target_id, "OUTDATED"))
                except Exception as e:
                    logger.error(f"  Automated Lifecycle Sync failed for {target_id}: {e}")

            for target_id in relationships["amends"]:
                session.run(
                    """
                    MATCH (source:Document {id: $source_id})
                    MERGE (target:Document {id: $target_id})
                    MERGE (source)-[:AMENDS]->(target)
                    """,
                    source_id=doc_id, target_id=target_id
                )

            for target_id in relationships["references"]:
                session.run(
                    """
                    MATCH (source:Document {id: $source_id})
                    MERGE (target:Document {id: $target_id})
                    MERGE (source)-[:REFERENCES]->(target)
                    """,
                    source_id=doc_id, target_id=target_id
                )

            for target_id in relationships["guides"]:
                session.run(
                    """
                    MATCH (source:Document {id: $source_id})
                    MERGE (target:Document {id: $target_id})
                    MERGE (source)-[:GUIDES]->(target)
                    """,
                    source_id=doc_id, target_id=target_id
                )

        logger.info(f"  Synced Graph edges for {doc_id}: {relationships}")
