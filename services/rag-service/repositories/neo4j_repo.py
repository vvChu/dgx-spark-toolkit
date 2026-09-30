import logging
import os
import re
from typing import Any, Dict, List, Optional

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)


class Neo4jRepository:
    """
    Repository pattern for encapsulating Neo4j Knowledge Graph queries.
    """

    def __init__(self, driver: AsyncDriver):
        self._driver = driver

    async def init_schema(self) -> None:
        """Initialize Neo4j schema constraints and indexes for Document nodes."""
        query_constraint = "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE"
        query_index = "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.doc_number)"
        try:
            async with self._driver.session() as session:
                await session.run(query_constraint)
                await session.run(query_index)
            logger.info("Neo4j schema constraints and indexes initialized successfully.")
        except Exception as e:
            logger.warning(f"Neo4j schema initialization skipped: {e}")

    @property
    def driver(self) -> AsyncDriver:
        """Underlying Neo4j driver connection. Provided for internal graph timeline traversal."""
        return self._driver

    async def close(self) -> None:
        """Safely close underlying Neo4j driver."""
        if self._driver:
            try:
                await self._driver.close()
            except Exception as e:
                logger.debug(f"Error closing Neo4j driver: {e}")

    async def get_legal_timeline(self, doc_number: str, max_hops: int = 10) -> list[dict]:
        """Iterative Cypher traversal to retrieve comprehensive legal timeline for a document node."""
        if not doc_number or not self._driver:
            return []

        query = """
        MATCH (start:Document)
        WHERE start.doc_number = $doc_number
           OR start.id = $doc_number
           OR start.id = 'VBPL/' + $doc_number
           OR start.id = 'ROOT/' + $doc_number
           OR start.doc_number = replace($doc_number, 'ROOT/', '')
        WITH start LIMIT 1
        OPTIONAL MATCH (newer:Document)-[:REPLACES]->(start)
        OPTIONAL MATCH (p:Document)-[:PROMULGATES]->(start)
        OPTIONAL MATCH (start)-[:PROMULGATES]->(out_p:Document)
        OPTIONAL MATCH (a:Document)-[:AMENDS]->(start)
        OPTIONAL MATCH (start)-[:AMENDS]->(out_a:Document)
        OPTIONAL MATCH path = (start)-[:REPLACES|REFERENCES*1..10]->(current)
        WITH start,
             collect(DISTINCT newer) AS superseding,
             collect(DISTINCT p) AS promulgators,
             collect(DISTINCT out_p) AS out_promulgates,
             collect(DISTINCT a) AS amenders,
             collect(DISTINCT out_a) AS out_amends,
             collect(path) AS rep_paths
        RETURN start, superseding, promulgators, out_promulgates, amenders, out_amends, rep_paths
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, doc_number=doc_number)
                record = await result.single()
                if not record or not record.get("start"):
                    return []

                start = record["start"]
                superseding = record["superseding"]
                promulgators = record["promulgators"]
                out_promulgates = record["out_promulgates"]
                amenders = record["amenders"]
                out_amends = record["out_amends"]
                rep_paths = record["rep_paths"]

                timeline: list[dict] = []

                # 1. Superseding documents
                for n in superseding:
                    timeline.append({
                        "doc_number": n.get("doc_number") or n.get("id"),
                        "id": n.get("id"),
                        "effective_date": n.get("effective_date") or n.get("date") or "unknown",
                        "status": n.get("status", "ACTIVE"),
                        "relation_to_next": "REPLACES",
                    })

                # 2. Promulgating circulars
                for p in promulgators:
                    timeline.append({
                        "doc_number": p.get("doc_number") or p.get("id"),
                        "id": p.get("id"),
                        "effective_date": p.get("effective_date") or p.get("date") or "unknown",
                        "status": p.get("status", "ACTIVE"),
                        "relation_to_next": "PROMULGATES",
                    })

                # 3. Amending circulars
                for a in amenders:
                    timeline.append({
                        "doc_number": a.get("doc_number") or a.get("id"),
                        "id": a.get("id"),
                        "effective_date": a.get("effective_date") or a.get("date") or "unknown",
                        "status": a.get("status", "ACTIVE"),
                        "relation_to_next": "AMENDS",
                    })

                # 4. Longest replacement path
                longest_path = None
                if rep_paths:
                    valid_paths = [p for p in rep_paths if p and hasattr(p, "relationships")]
                    if valid_paths:
                        longest_path = max(valid_paths, key=lambda p: len(p.relationships))

                # Determine start's relation_to_next
                start_rel = None
                if out_promulgates:
                    start_rel = "PROMULGATES"
                elif out_amends:
                    start_rel = "AMENDS"
                elif longest_path and len(longest_path.relationships) > 0:
                    start_rel = longest_path.relationships[0].type

                timeline.append({
                    "doc_number": start.get("doc_number") or start.get("id"),
                    "id": start.get("id"),
                    "effective_date": start.get("effective_date") or start.get("date") or "unknown",
                    "status": start.get("status", "UNKNOWN"),
                    "relation_to_next": start_rel,
                })

                # 5. Outgoing promulgations
                for op in out_promulgates:
                    timeline.append({
                        "doc_number": op.get("doc_number") or op.get("id"),
                        "id": op.get("id"),
                        "effective_date": op.get("effective_date") or op.get("date") or "unknown",
                        "status": op.get("status", "ACTIVE"),
                        "relation_to_next": None,
                    })

                # 6. Outgoing amendments
                for oa in out_amends:
                    timeline.append({
                        "doc_number": oa.get("doc_number") or oa.get("id"),
                        "id": oa.get("id"),
                        "effective_date": oa.get("effective_date") or oa.get("date") or "unknown",
                        "status": oa.get("status", "ACTIVE"),
                        "relation_to_next": None,
                    })

                # 7. Predecessors in replacement chain
                if longest_path:
                    path_nodes = list(longest_path.nodes)
                    path_rels = list(longest_path.relationships)
                    for i in range(1, len(path_nodes)):
                        node = path_nodes[i]
                        rel_type = path_rels[i].type if i < len(path_rels) else None
                        timeline.append({
                            "doc_number": node.get("doc_number") or node.get("id"),
                            "id": node.get("id"),
                            "effective_date": node.get("effective_date") or node.get("date") or "unknown",
                            "status": node.get("status", "OUTDATED"),
                            "relation_to_next": rel_type,
                        })

                return timeline
        except Exception as e:
            logger.error(f"Failed to retrieve legal timeline for {doc_number}: {e}")
            return []

    async def get_document_relations(self, doc_id: str):
        query = """
        MATCH (d:Document)
        WHERE d.id CONTAINS $query_id
        OPTIONAL MATCH (d)-[r:REPLACES|AMENDS|REFERENCES|GUIDES*1..3]->(target:Document)
        OPTIONAL MATCH (source:Document)-[r2:REPLACES|AMENDS|GUIDES*1..3]->(d)
        RETURN d.id as id,
               CASE WHEN d.status IS NOT NULL THEN d.status ELSE 'UNKNOWN' END as status,
               [rel in coalesce(r, []) | type(rel)] as out_rels, [t in coalesce(target, []) | t.id] as targets,
               [rel in coalesce(r2, []) | type(rel)] as in_rels, [s in coalesce(source, []) | s.id] as sources
        LIMIT 10
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, query_id=doc_id)
                # Ensure we pull the data out fully while the session is alive
                return [record.data() async for record in result]
        except Exception as e:
            logger.error(f"Graph query failed: {e}")
            return []

    async def get_guided_circulars(self, doc_id: str):
        query = """
        MATCH (d:Document)<-[:GUIDES|REFERENCES*1..2]-(guided:Document)
        WHERE d.id CONTAINS $query_id AND guided.doc_type = 'TT'
        RETURN d.id as source, guided.id as guided_id, guided.status as status
        LIMIT 15
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, query_id=doc_id)
                return [record.data() async for record in result]
        except Exception as e:
            logger.error(f"Graph guided circulars query failed: {e}")
            return []

    async def find_document_status(self, doc_ids: list[str]) -> dict[str, str]:
        """Fetch the status (ACTIVE, OUTDATED) for a list of document IDs."""
        status_map = {}
        query = (
            "MATCH (d:Document) WHERE d.id IN $ids OR d.file_name IN $ids "
            "RETURN coalesce(d.file_name, d.id) as id, d.id as doc_id, d.file_name as file_name, d.status as status"
        )
        try:
            async with self._driver.session() as session:
                result = await session.run(query, ids=doc_ids)
                records = [record.data() async for record in result]
                for rec in records:
                    raw_status = rec.get("status", "ACTIVE")
                    norm_status = "OUTDATED" if str(raw_status).upper() in ("OUTDATED", "SUPERSEDED", "EXPIRED") else "ACTIVE"
                    if rec.get("id"):
                        status_map[rec["id"]] = norm_status
                    if rec.get("doc_id"):
                        status_map[rec["doc_id"]] = norm_status
                    if rec.get("file_name"):
                        status_map[rec["file_name"]] = norm_status
            return status_map
        except Exception as e:
            logger.error(f"Failed to fetch document status from Graph: {e}")
            return {}

    @staticmethod
    def _canonicalize_doc_id(identifier: str, id_map: Optional[dict[str, str]] = None) -> str:
        """Resolve identifier to canonical doc_id format (VBPL/...)."""
        clean = identifier.strip()
        if not clean:
            return ""
        if id_map:
            if clean in id_map:
                return id_map[clean]
            if clean.lower() in id_map:
                return id_map[clean.lower()]
            swapped = clean.replace("-", "_")
            if swapped in id_map:
                return id_map[swapped]
            norm = re.sub(r"[^\w\d]", "", clean).lower()
            if norm in id_map:
                return id_map[norm]

        if clean.startswith("VBPL/"):
            return re.sub(r"[^\w\d\-_/.]", "_", clean)

        # Match QCVN: e.g. QCVN 06:2020/BXD or QCVN-01-2019-BXD
        m_qcvn = re.search(r"QCVN[-_\s]*(\d+)[:\-_/](\d{4})[-_\s/]*([A-Z]+)", clean, re.IGNORECASE)
        if m_qcvn:
            num = m_qcvn.group(1).zfill(2)
            year = m_qcvn.group(2)
            auth = m_qcvn.group(3).upper()
            return f"VBPL/QCVN_{num}_{year}/{auth}"

        # Match TCVN: e.g. TCVN 7336:2021, TCVN-4601-1988, TCVN ISO 19650-1:2021
        m_tcvn = re.search(r"TCVN[-_\s]*(?:ISO[-_\s]*)?(\d+)(?:[-_\s]+(\d+))?[:\-_/](\d{4})", clean, re.IGNORECASE)
        if m_tcvn:
            p1 = m_tcvn.group(1)
            p2 = m_tcvn.group(2)
            year = m_tcvn.group(3)
            if "ISO" in clean.upper():
                suffix = f"-{p2}" if p2 else ""
                return f"VBPL/TCVN_ISO_{p1}{suffix}_{year}"
            return f"VBPL/TCVN_{p1}_{year}"

        # Match TCXD or TCXDVN
        m_tcxd = re.search(r"(TCXDVN|TCXD)[-_\s]*(\d+)[:\-_/](\d{2,4})", clean, re.IGNORECASE)
        if m_tcxd:
            prefix = m_tcxd.group(1).upper()
            return f"VBPL/{prefix}_{m_tcxd.group(2)}_{m_tcxd.group(3)}"

        # Match standard decree/circular/law: e.g. 15/2021/NĐ-CP or 10_2021_nd_cp
        m_law = re.search(r"(\d+)[/_\-](\d{4})[/_\-]([A-Za-z0-9Đđ_\-]+)", clean)
        if m_law:
            num = m_law.group(1)
            year = m_law.group(2)
            suffix = m_law.group(3).upper().replace("_", "-")
            if "ND" in suffix and "NĐ" not in suffix:
                suffix = suffix.replace("ND", "NĐ")
            return f"VBPL/{num}/{year}/{suffix}"

        sanitized = re.sub(r"[^\w\d\-_/.]", "_", clean)
        return f"VBPL/{sanitized}"

    async def sync_hub3_topology(
        self,
        bundles: list,
        id_map: Optional[dict[str, str]] = None,
    ) -> dict[str, int]:
        """Synchronize Hub 3 OKF v2.4 legal topology and status to Neo4j.

        - Creates or merges (:Document) nodes with properties: id, doc_number,
          file_name, doc_type, authority, status, effective_date.
        - Creates (:Document)-[:REPLACES]->(:Document) relationships and marks
          replaced documents as OUTDATED using canonical document IDs.
        - Creates (:Document)-[:AMENDS]->(:Document) relationships while preserving
          the ACTIVE status of the base standard being amended.

        Args:
            bundles: List of Hub3BundleInfo instances or equivalent dicts.
            id_map: Optional lookup map to resolve aliases to canonical IDs.

        Returns:
            Dict containing nodes_synced, replaces_created, amends_created counts.
        """
        nodes_synced = 0
        replaces_created = 0
        amends_created = 0

        if not bundles or not self._driver:
            return {
                "nodes_synced": 0,
                "replaces_created": 0,
                "amends_created": 0,
            }

        try:
            async with self._driver.session() as session:
                # Step 0: Cleanup legacy / orphan amendment nodes
                await session.run(
                    """
                    MATCH (d:Document)
                    WHERE d.id IN ['VBPL/1/2023/QCVN-06', 'VBPL/1/2026/QCVN-04']
                    DETACH DELETE d
                    """
                )

                # Step 1: Upsert Document nodes
                for b in bundles:
                    doc_id = (
                        getattr(b, "canonical_id", None)
                        or getattr(b, "id", None)
                        or (b.get("canonical_id") if isinstance(b, dict) else None)
                        or (b.get("id") if isinstance(b, dict) else None)
                    )
                    if not doc_id:
                        continue

                    doc_number = (
                        getattr(b, "document_number", "")
                        or (b.get("document_number", "") if isinstance(b, dict) else "")
                    )
                    file_name = (
                        getattr(b, "file_name", "")
                        or (b.get("file_name", "") if isinstance(b, dict) else "")
                    )
                    doc_type = (
                        getattr(b, "doc_type", "")
                        or (b.get("doc_type", "") if isinstance(b, dict) else "")
                    )
                    authority = (
                        getattr(b, "issued_by", "")
                        or (b.get("issued_by", "") if isinstance(b, dict) else "")
                        or (b.get("authority", "") if isinstance(b, dict) else "")
                    )
                    effective_date = (
                        getattr(b, "effective_date", "")
                        or (b.get("effective_date", "") if isinstance(b, dict) else "")
                    )
                    status = (
                        getattr(b, "validity_status", "")
                        or (b.get("validity_status", "") if isinstance(b, dict) else "")
                    )
                    if not status:
                        raw_status = (
                            getattr(b, "status", "active")
                            or (b.get("status", "active") if isinstance(b, dict) else "active")
                        )
                        status = "OUTDATED" if str(raw_status).lower() in ("expired", "outdated", "superseded") else "ACTIVE"

                    await session.run(
                        """
                        MERGE (d:Document {id: $doc_id})
                        SET d.doc_number = $doc_number,
                            d.file_name = $file_name,
                            d.doc_type = $doc_type,
                            d.authority = $authority,
                            d.status = $status,
                            d.effective_date = $effective_date
                        """,
                        doc_id=doc_id,
                        doc_number=doc_number,
                        file_name=file_name,
                        doc_type=doc_type,
                        authority=authority,
                        status=status,
                        effective_date=effective_date,
                    )
                    nodes_synced += 1

                # Step 2: Create [:REPLACES] relationships
                for b in bundles:
                    source_id = (
                        getattr(b, "canonical_id", None)
                        or getattr(b, "id", None)
                        or (b.get("canonical_id") if isinstance(b, dict) else None)
                        or (b.get("id") if isinstance(b, dict) else None)
                    )
                    if not source_id:
                        continue

                    replaces_list = (
                        getattr(b, "canonical_replaces", None)
                        or getattr(b, "replaces", [])
                        or (b.get("canonical_replaces") if isinstance(b, dict) else None)
                        or (b.get("replaces", []) if isinstance(b, dict) else [])
                    )
                    if isinstance(replaces_list, str):
                        replaces_list = [replaces_list]

                    seen_targets = set()
                    for raw_target in replaces_list:
                        raw_target = str(raw_target).strip()
                        if not raw_target:
                            continue
                        target_id = self._canonicalize_doc_id(raw_target, id_map)
                        if target_id in seen_targets or target_id == source_id:
                            continue
                        seen_targets.add(target_id)

                        await session.run(
                            """
                            MERGE (target:Document {id: $target_id})
                            MERGE (source:Document {id: $source_id})
                            MERGE (source)-[:REPLACES]->(target)
                            SET target.status = 'OUTDATED'
                            """,
                            source_id=source_id,
                            target_id=target_id,
                        )
                        replaces_created += 1

                # Step 3: Create [:AMENDS] relationships (preserving base document ACTIVE status)
                for b in bundles:
                    base_id = (
                        getattr(b, "canonical_id", None)
                        or getattr(b, "id", None)
                        or (b.get("canonical_id") if isinstance(b, dict) else None)
                        or (b.get("id") if isinstance(b, dict) else None)
                    )
                    if not base_id:
                        continue

                    seen_amends = set()

                    # Case A: Bundle has amendments list (e.g. SD1 amends this bundle)
                    amendments = (
                        getattr(b, "amendments", [])
                        or (b.get("amendments", []) if isinstance(b, dict) else [])
                    )
                    for amd in amendments:
                        raw_amd_id = amd.get("id") if isinstance(amd, dict) else str(amd)
                        if not raw_amd_id:
                            continue
                        amd_id = self._canonicalize_doc_id(str(raw_amd_id), id_map)
                        if amd_id in seen_amends or amd_id == base_id:
                            continue
                        seen_amends.add(amd_id)

                        amd_title = amd.get("title", "") if isinstance(amd, dict) else ""
                        amd_doc_num = (
                            amd.get("document_number", "")
                            if isinstance(amd, dict)
                            else ""
                        )
                        if not amd_doc_num:
                            m_num = re.search(r"(\d+/\d{4}/(?:TT|QĐ)-[A-ZĐ]+)", amd_id) or re.search(r"(\d+/\d{4}/(?:TT|QĐ)-[A-ZĐ]+)", amd_title)
                            if m_num:
                                amd_doc_num = m_num.group(1)
                            else:
                                amd_doc_num = amd_title

                        doc_type = "Thông tư" if "TT-" in amd_doc_num else ("Quyết định" if "QĐ-" in amd_doc_num else "Sửa đổi bổ sung")

                        await session.run(
                            """
                            MERGE (amending:Document {id: $amd_id})
                            ON CREATE SET amending.status = 'ACTIVE',
                                          amending.doc_type = $doc_type,
                                          amending.doc_number = $amd_doc_num,
                                          amending.title = $amd_title
                            ON MATCH SET amending.doc_number = CASE WHEN amending.doc_number IS NULL OR amending.doc_number = '' OR amending.doc_number CONTAINS 'Sửa đổi' THEN $amd_doc_num ELSE amending.doc_number END,
                                         amending.doc_type = CASE WHEN amending.doc_type IS NULL OR amending.doc_type = '' OR amending.doc_type = 'Sửa đổi bổ sung' THEN $doc_type ELSE amending.doc_type END
                            MERGE (base:Document {id: $base_id})
                            MERGE (amending)-[:AMENDS]->(base)
                            """,
                            amd_id=amd_id,
                            base_id=base_id,
                            amd_doc_num=amd_doc_num,
                            doc_type=doc_type,
                            amd_title=amd_title,
                        )
                        amends_created += 1

                    # Case B: Bundle itself amends another document
                    amends_list = (
                        getattr(b, "canonical_amends", None)
                        or getattr(b, "amends", [])
                        or (b.get("canonical_amends") if isinstance(b, dict) else None)
                        or (b.get("amends", []) if isinstance(b, dict) else [])
                    )
                    if isinstance(amends_list, str):
                        amends_list = [amends_list]
                    for raw_target in amends_list:
                        raw_target = str(raw_target).strip()
                        if not raw_target:
                            continue
                        target_id = self._canonicalize_doc_id(raw_target, id_map)
                        if target_id in seen_amends or target_id == base_id:
                            continue
                        seen_amends.add(target_id)

                        await session.run(
                            """
                            MERGE (source:Document {id: $source_id})
                            MERGE (target:Document {id: $target_id})
                            MERGE (source)-[:AMENDS]->(target)
                            """,
                            source_id=base_id,
                            target_id=target_id,
                        )
                        amends_created += 1

                # Step 3.5: Create [:PROMULGATES] relationships (Circular/Decision -> Technical Regulation/Standard)
                promulgates_created = 0
                for b in bundles:
                    base_id = (
                        getattr(b, "canonical_id", None)
                        or getattr(b, "id", None)
                        or (b.get("canonical_id") if isinstance(b, dict) else None)
                        or (b.get("id") if isinstance(b, dict) else None)
                    )
                    prom_raw = (
                        getattr(b, "canonical_promulgated_by", None)
                        or getattr(b, "promulgated_by", None)
                        or (b.get("canonical_promulgated_by") if isinstance(b, dict) else None)
                        or (b.get("promulgated_by") if isinstance(b, dict) else None)
                    )
                    if not prom_raw or not base_id:
                        continue

                    prom_id = self._canonicalize_doc_id(str(prom_raw), id_map)
                    if not prom_id or prom_id == base_id:
                        continue

                    m_num = re.search(r"(\d+/\d{4}/(?:TT|QĐ)-[A-ZĐ]+)", prom_id) or re.search(r"(\d+/\d{4}/(?:TT|QĐ)-[A-ZĐ]+)", str(prom_raw))
                    prom_doc_num = m_num.group(1) if m_num else str(prom_raw)
                    doc_type = "Thông tư" if "TT-" in prom_doc_num else ("Quyết định" if "QĐ-" in prom_doc_num else "Văn bản QPPL")
                    prom_title = f"{doc_type} {prom_doc_num} ban hành {getattr(b, 'document_number', base_id)}"

                    await session.run(
                        """
                        MERGE (promulgator:Document {id: $prom_id})
                        ON CREATE SET promulgator.status = 'ACTIVE',
                                      promulgator.doc_type = $doc_type,
                                      promulgator.doc_number = $prom_doc_num,
                                      promulgator.title = $prom_title
                        ON MATCH SET promulgator.doc_number = CASE WHEN promulgator.doc_number IS NULL OR promulgator.doc_number = '' THEN $prom_doc_num ELSE promulgator.doc_number END,
                                     promulgator.doc_type = CASE WHEN promulgator.doc_type IS NULL OR promulgator.doc_type = '' THEN $doc_type ELSE promulgator.doc_type END
                        MERGE (base:Document {id: $base_id})
                        MERGE (promulgator)-[:PROMULGATES]->(base)
                        """,
                        prom_id=prom_id,
                        base_id=base_id,
                        prom_doc_num=prom_doc_num,
                        doc_type=doc_type,
                        prom_title=prom_title,
                    )
                    promulgates_created += 1

                # Step 4: Create [:GUIDES] relationships
                guides_created = 0
                for b in bundles:
                    source_id = (
                        getattr(b, "canonical_id", None)
                        or getattr(b, "id", None)
                        or (b.get("canonical_id") if isinstance(b, dict) else None)
                        or (b.get("id") if isinstance(b, dict) else None)
                    )
                    if not source_id:
                        continue

                    guides_list = (
                        getattr(b, "canonical_guides", None)
                        or getattr(b, "guides", [])
                        or (b.get("canonical_guides") if isinstance(b, dict) else None)
                        or (b.get("guides", []) if isinstance(b, dict) else [])
                    )
                    if not guides_list and getattr(b, "guided_by", None):
                        guides_list = [getattr(b, "guided_by")]

                    if isinstance(guides_list, str):
                        guides_list = [guides_list]

                    seen_guides = set()
                    for raw_target in guides_list:
                        raw_target = str(raw_target).strip()
                        if not raw_target:
                            continue
                        target_id = self._canonicalize_doc_id(raw_target, id_map)
                        if target_id in seen_guides or target_id == source_id:
                            continue
                        seen_guides.add(target_id)

                        await session.run(
                            """
                            MERGE (source:Document {id: $source_id})
                            MERGE (target:Document {id: $target_id})
                            MERGE (source)-[:GUIDES]->(target)
                            """,
                            source_id=source_id,
                            target_id=target_id,
                        )
                        guides_created += 1

        except Exception as e:
            logger.error(f"Failed to sync Hub 3 topology to Neo4j: {e}")
            raise

        return {
            "nodes_synced": nodes_synced,
            "replaces_created": replaces_created,
            "amends_created": amends_created,
            "promulgates_created": promulgates_created,
            "guides_created": guides_created,
        }

    async def update_node_status(self, doc_id: str, new_status: str):
        """Update the status property of a Document node."""
        query = "MATCH (d:Document {id: $doc_id}) SET d.status = $status"
        try:
            async with self._driver.session() as session:
                await session.run(query, doc_id=doc_id, status=new_status)
                logger.info(f"Successfully updated status to {new_status} for Document node: {doc_id}")
        except Exception as e:
            logger.error(f"Failed to update Neo4j node status for {doc_id}: {e}")
            raise

    async def clear_db(self, confirm: bool = False):
        """Delete all nodes and relationships in Neo4j.

        Requires both ``confirm=True`` and the ``ALLOW_DB_CLEAR`` environment
        variable set to ``"1"`` to prevent accidental data loss.
        """
        if not confirm or os.environ.get("ALLOW_DB_CLEAR") != "1":
            raise RuntimeError(
                "clear_db() refused: pass confirm=True and set ALLOW_DB_CLEAR=1 to proceed."
            )
        query = "MATCH (n) DETACH DELETE n"
        try:
            async with self._driver.session() as session:
                await session.run(query)
                logger.info("Neo4j database cleared.")
        except Exception as e:
            logger.error(f"Failed to clear Neo4j DB: {e}")

    async def run_query(self, cypher: str, **params) -> list[dict]:
        """Execute an arbitrary read-only Cypher query and return all records as dicts.

        This provides a controlled escape hatch for routers that need custom
        queries (e.g. stats, graph visualization) without accessing _driver.
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(cypher, **params)
                return [record.data() async for record in result]
        except Exception as e:
            logger.error(f"Neo4j run_query failed: {e}")
            return []

    async def create_supersedes_relation(self, new_doc_id: str, old_doc_id: str) -> None:
        """Create a SUPERSEDES relationship from new_doc → old_doc.

        Uses MERGE to prevent duplicate relationships.
        Also ensures both Document nodes exist (MERGE on node too).

        Cypher:
            (new_doc)-[:SUPERSEDES]->(old_doc)
        """
        query = """
        MERGE (new_doc:Document {id: $new_doc_id})
        MERGE (old_doc:Document {id: $old_doc_id})
        MERGE (new_doc)-[:SUPERSEDES]->(old_doc)
        SET old_doc.status = 'SUPERSEDED',
            new_doc.supersedes = coalesce(new_doc.supersedes, []) + $old_doc_id
        """
        try:
            async with self._driver.session() as session:
                await session.run(query, new_doc_id=new_doc_id, old_doc_id=old_doc_id)
            logger.info(f"Neo4j: Created SUPERSEDES {new_doc_id} → {old_doc_id}")
        except Exception as e:
            logger.error(f"Failed to create SUPERSEDES relation {new_doc_id}→{old_doc_id}: {e}")
            raise

    async def create_amends_relation(self, new_doc_id: str, amended_doc_id: str) -> None:
        """Create an AMENDS relationship from new_doc → amended_doc.

        Uses MERGE to prevent duplicate relationships.
        Unlike SUPERSEDES, the amended document stays partially valid (OUTDATED).

        Cypher:
            (new_doc)-[:AMENDS]->(amended_doc)
        """
        query = """
        MERGE (new_doc:Document {id: $new_doc_id})
        MERGE (amended_doc:Document {id: $amended_doc_id})
        MERGE (new_doc)-[:AMENDS]->(amended_doc)
        SET amended_doc.status = 'OUTDATED'
        """
        try:
            async with self._driver.session() as session:
                await session.run(query, new_doc_id=new_doc_id, amended_doc_id=amended_doc_id)
            logger.info(f"Neo4j: Created AMENDS {new_doc_id} → {amended_doc_id}")
        except Exception as e:
            logger.error(f"Failed to create AMENDS relation {new_doc_id}→{amended_doc_id}: {e}")
            raise

    async def get_superseded_by(self, doc_id: str) -> list[dict]:
        """Find which document(s) supersede the given doc_id.

        Useful for UI: 'This document has been replaced by X'.
        Returns list of {id, title, effective_date} for replacement docs.
        """
        query = """
        MATCH (newer:Document)-[:SUPERSEDES]->(old:Document {id: $doc_id})
        RETURN newer.id AS id,
               coalesce(newer.title, '') AS title,
               coalesce(newer.effective_date, '') AS effective_date
        ORDER BY newer.effective_date DESC
        LIMIT 5
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, doc_id=doc_id)
                return [record.data() async for record in result]
        except Exception as e:
            logger.error(f"Neo4j get_superseded_by failed for {doc_id}: {e}")
            return []

    async def create_document_node(self, processed_doc) -> None:
        """Create or update a Document node and its relationships in Neo4j."""
        identity = processed_doc.identity
        metadata = processed_doc.metadata
        doc_id = identity.doc_id
        doc_number = identity.doc_number
        file_name = identity.file_name
        rel_path = identity.rel_path

        doc_type = getattr(metadata, "doc_type", "UNKNOWN")
        authority = getattr(metadata, "authority", "UNKNOWN")
        doc_date = getattr(metadata, "date", "UNKNOWN")
        validity = getattr(metadata, "validity_status", "ACTIVE")

        query = """
        MERGE (d:Document {id: $doc_id})
        SET d.doc_number = $doc_number,
            d.file_name = $file_name,
            d.rel_path = $rel_path,
            d.doc_type = $doc_type,
            d.authority = $authority,
            d.doc_date = $doc_date,
            d.status = $validity
        """
        try:
            async with self._driver.session() as session:
                await session.run(
                    query,
                    doc_id=doc_id,
                    doc_number=doc_number,
                    file_name=file_name,
                    rel_path=rel_path,
                    doc_type=doc_type,
                    authority=authority,
                    doc_date=doc_date,
                    validity=validity,
                )

                relationships = getattr(processed_doc, "relationships", None)
                if relationships:
                    rel_dict = relationships.to_dict() if hasattr(relationships, "to_dict") else dict(relationships)
                    for replaced in (rel_dict.get("replaces") or []):
                        target_id = str(replaced).strip() if replaced else ""
                        if target_id:
                            await session.run("""
                                MERGE (target:Document {id: $target_id})
                                MERGE (source:Document {id: $source_id})
                                MERGE (source)-[:REPLACES]->(target)
                                SET target.status = 'SUPERSEDED'
                            """, source_id=doc_id, target_id=target_id)

                    for amended in (rel_dict.get("amends") or []):
                        target_id = str(amended).strip() if amended else ""
                        if target_id:
                            await session.run("""
                                MERGE (target:Document {id: $target_id})
                                MERGE (source:Document {id: $source_id})
                                MERGE (source)-[:AMENDS]->(target)
                                SET target.status = 'OUTDATED'
                            """, source_id=doc_id, target_id=target_id)

                    for referenced in (rel_dict.get("references") or []):
                        target_id = str(referenced).strip() if referenced else ""
                        if target_id:
                            await session.run("""
                                MERGE (target:Document {id: $target_id})
                                MERGE (source:Document {id: $source_id})
                                MERGE (source)-[:REFERENCES]->(target)
                            """, source_id=doc_id, target_id=target_id)

                    for guided in (rel_dict.get("guides") or []):
                        target_id = str(guided).strip() if guided else ""
                        if target_id:
                            await session.run("""
                                MERGE (target:Document {id: $target_id})
                                MERGE (source:Document {id: $source_id})
                                MERGE (source)-[:GUIDES]->(target)
                            """, source_id=doc_id, target_id=target_id)
        except Exception as e:
            logger.error(f"Failed to create Document node in Neo4j for {doc_id}: {e}")
            raise

    async def delete_document_node(self, doc_id: str) -> None:
        """Detach and delete a Document node by id."""
        query = "MATCH (d:Document) WHERE d.id = $doc_id or d.doc_number = $doc_id DETACH DELETE d"
        try:
            async with self._driver.session() as session:
                await session.run(query, doc_id=doc_id)
        except Exception as e:
            logger.error(f"Failed to delete Document node in Neo4j for {doc_id}: {e}")
            raise
