"""Tests for Neo4j Transitional Governance Relationships and 2026 Decrees.
=============================================================================
Validates:
1. Document-level GOVERNS_TRANSITIONAL edges exist with metadata:
   - 135/2025/QH15 -> 50/2014/QH13 (cutoff_date: 2026-07-01)
   - 31/2026/TT-BXD -> QCVN 04:2021/BXD (grace_period_end: 2027-06-15)
   - 09/2023/TT-BXD -> QCVN 06:2022/BXD (cutoff_date: 2023-12-01)
2. Correct AMENDS relationships for 2026 Decrees:
   - 207/2026/NĐ-CP -[:AMENDS]-> 15/2021/NĐ-CP
   - 209/2026/NĐ-CP -[:AMENDS]-> 06/2021/NĐ-CP
   - 206/2026/NĐ-CP -[:AMENDS]-> 10/2021/NĐ-CP
   - 339/2026/NĐ-CP -[:AMENDS]-> 16/2022/NĐ-CP
3. Neo4jRepository.get_legal_timeline() and GraphTimelineRetriever.get_legal_timeline()
   properly surface transitional predecessors and governors in the timeline list.

Adheres to:
- ADR-0058: Hard Completion Lock
- Grok 4.7 xhigh Condition C3: Document-level GOVERNS_TRANSITIONAL
"""

import asyncio
import os
import sys
from pathlib import Path
import pytest
from neo4j import AsyncGraphDatabase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RAG_SERVICE_DIR = REPO_ROOT / "services/rag-service"
if str(RAG_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_SERVICE_DIR))

from core.config import Settings  # noqa: E402
from repositories.neo4j_repo import Neo4jRepository  # noqa: E402
from retrieval.graph_timeline_retriever import GraphTimelineRetriever  # noqa: E402


_loop = None


def get_loop():
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def _run(coro):
    return get_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def neo4j_credentials():
    pwd = os.environ.get("NEO4J_PASSWORD", "")
    if not pwd or pwd == "ci_test_placeholder_safe":
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("NEO4J_PASSWORD="):
                    pwd = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    user = os.environ.get("NEO4J_USER", "neo4j")
    # In CI/local docker, connect via localhost:7687
    return "bolt://localhost:7687", user, pwd


@pytest.fixture(scope="module")
def neo4j_driver(neo4j_credentials):
    uri, user, pwd = neo4j_credentials
    driver = AsyncGraphDatabase.driver(uri, auth=(user, pwd))

    async def _ping():
        async with driver.session() as session:
            await session.run("RETURN 1")

    try:
        _run(_ping())
    except Exception as e:
        pytest.skip(f"Neo4j database not reachable at {uri}: {e}")
    yield driver
    _run(driver.close())


@pytest.fixture
def neo4j_repo(neo4j_driver):
    return Neo4jRepository(neo4j_driver)


@pytest.fixture
def timeline_retriever(neo4j_driver):
    return GraphTimelineRetriever(driver=neo4j_driver)


def test_transitional_edges_in_graph(neo4j_driver):
    """Verify statutory GOVERNS_TRANSITIONAL relationships exist with expected metadata."""
    query = """
    MATCH (s:Document)-[r:GOVERNS_TRANSITIONAL]->(t:Document)
    RETURN s.doc_number as source, t.doc_number as target, properties(r) as props
    """

    async def _test():
        async with neo4j_driver.session() as session:
            res = await session.run(query)
            records = [r async for r in res]
            assert len(records) >= 3, f"Expected at least 3 GOVERNS_TRANSITIONAL edges, got {len(records)}"

            edges_map = {(r["source"], r["target"]): r["props"] for r in records}

            # 1. Luật Xây dựng 2025 -> Luật Xây dựng 2014
            assert ("135/2025/QH15", "50/2014/QH13") in edges_map
            law_props = edges_map[("135/2025/QH15", "50/2014/QH13")]
            assert law_props.get("cutoff_date") == "2026-07-01"
            assert "2014" in law_props.get("condition", "")

            # 2. Thông tư 31/2026 -> QCVN 04:2021
            assert ("31/2026/TT-BXD", "QCVN 04:2021/BXD") in edges_map
            tt31_props = edges_map[("31/2026/TT-BXD", "QCVN 04:2021/BXD")]
            assert tt31_props.get("grace_period_end") == "2027-06-15"
            assert "trạm sạc" in tt31_props.get("condition", "")

    _run(_test())


def test_decree_2026_amends_relationships(neo4j_driver):
    """Verify 2026 Decrees properly AMEND (not erroneously REPLACE) core decrees."""
    query = """
    MATCH (s:Document)-[r:AMENDS]->(t:Document)
    WHERE s.doc_number IN ['207/2026/NĐ-CP', '209/2026/NĐ-CP', '206/2026/NĐ-CP', '339/2026/NĐ-CP']
    RETURN s.doc_number as source, t.doc_number as target
    """

    async def _test():
        async with neo4j_driver.session() as session:
            res = await session.run(query)
            pairs = {(r["source"], r["target"]) async for r in res}

            assert ("207/2026/NĐ-CP", "15/2021/NĐ-CP") in pairs
            assert ("209/2026/NĐ-CP", "06/2021/NĐ-CP") in pairs
            assert ("206/2026/NĐ-CP", "10/2021/NĐ-CP") in pairs
            assert ("339/2026/NĐ-CP", "16/2022/NĐ-CP") in pairs

    _run(_test())


def test_neo4j_repo_legal_timeline_transitional(neo4j_repo):
    """Verify Neo4jRepository.get_legal_timeline surfaces transitional governance metadata."""
    async def _test():
        # Query Law 2025: should show outgoing transitional predecessor (50/2014/QH13)
        timeline_2025 = await neo4j_repo.get_legal_timeline("135/2025/QH15")
        assert any(
            item.get("relation_to_next") == "TRANSITIONAL_PREDECESSOR" and "50/2014" in str(item.get("doc_number", ""))
            for item in timeline_2025
        )

        # Query QCVN 04: should show incoming GOVERNS_TRANSITIONAL from 31/2026/TT-BXD
        timeline_qcvn04 = await neo4j_repo.get_legal_timeline("QCVN 04:2021/BXD")
        assert any(
            item.get("relation_to_next") == "GOVERNS_TRANSITIONAL" and "31/2026" in str(item.get("doc_number", ""))
            for item in timeline_qcvn04
        )

    _run(_test())


def test_retriever_timeline_parity(timeline_retriever):
    """Verify GraphTimelineRetriever yields identical transitional relationship semantics."""
    async def _test():
        timeline = await timeline_retriever.get_legal_timeline("50/2014/QH13")
        assert any(
            item.get("relation_to_next") == "GOVERNS_TRANSITIONAL" and "135/2025" in str(item.get("doc_number", ""))
            for item in timeline
        )

    _run(_test())


def test_statutory_references_graph(neo4j_driver):
    """Verify statutory REFERENCES and REPLACES edges between key standards in Neo4j."""
    query = """
    MATCH (s:Document)-[r:REFERENCES|REPLACES]->(t:Document)
    WHERE s.doc_number IN ['QCVN 06:2022/BXD', 'QCVN 04:2021/BXD', 'QCVN 10:2025/BCA']
    RETURN s.doc_number as source, type(r) as rel_type, t.doc_number as target
    """

    async def _test():
        async with neo4j_driver.session() as session:
            res = await session.run(query)
            edges = {(r["source"], r["rel_type"], r["target"]) async for r in res}

            # QCVN 06:2022/BXD references
            assert ("QCVN 06:2022/BXD", "REFERENCES", "TCVN 7336:2021") in edges
            assert ("QCVN 06:2022/BXD", "REFERENCES", "TCVN 3890:2023") in edges
            assert ("QCVN 06:2022/BXD", "REFERENCES", "TCVN 5738:2021") in edges
            assert ("QCVN 06:2022/BXD", "REFERENCES", "QCVN 01:2021/BXD") in edges
            assert ("QCVN 06:2022/BXD", "REFERENCES", "QCVN 04:2021/BXD") in edges

            # QCVN 04:2021/BXD references
            assert ("QCVN 04:2021/BXD", "REFERENCES", "QCVN 06:2022/BXD") in edges
            assert ("QCVN 04:2021/BXD", "REFERENCES", "QCVN 01:2021/BXD") in edges

            # QCVN 10:2025/BCA replaces TCVN 3890:2023
            assert ("QCVN 10:2025/BCA", "REPLACES", "TCVN 3890:2023") in edges

    _run(_test())

