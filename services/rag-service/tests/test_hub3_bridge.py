"""Tests for Hub 3 OKF v2.4 Gazette Bundles Bridge and Ingestion Pipeline."""
from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingestion.chunking import DocumentChunker
from ingestion.hub3_bridge import (
    Hub3Bridge,
    Hub3BundleInfo,
    ShaVerificationStatus,
)
from ingestion.models import Chunk, ProcessedDocument
from repositories.neo4j_repo import Neo4jRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hub3_bridge() -> Hub3Bridge:
    """Returns Hub3Bridge instance initialized with default or local path."""
    return Hub3Bridge()


@pytest.fixture
def mock_neo4j_repo():
    """Mock Neo4jRepository with async session."""
    session = AsyncMock()
    session.run = AsyncMock()

    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session.return_value = session_ctx
    driver.close = AsyncMock()

    repo = Neo4jRepository(driver)
    return repo, session


# ---------------------------------------------------------------------------
# Test Suite: Catalog Discovery & Merging (ADR-0047 SSOT)
# ---------------------------------------------------------------------------

class TestCatalogDiscovery:
    """Tests for Master Catalog discovery and metadata merging."""

    def test_load_master_catalog_all_bundles(self, hub3_bridge: Hub3Bridge):
        """Verify discovering all 60 bundles from the real Hub 3 repo."""
        if not hub3_bridge.hub3_path.exists():
            pytest.skip("Hub 3 path not present on this machine")

        bundles = hub3_bridge.load_master_catalog()
        assert len(bundles) >= 60
        # Verify deterministic sorting by slug
        slugs = [b.slug for b in bundles]
        # Inode Invariance: verify sorted
        assert slugs == sorted(slugs)

    def test_load_master_catalog_category_filter(self, hub3_bridge: Hub3Bridge):
        """Verify category filtering works for 02_qcvn."""
        if not hub3_bridge.hub3_path.exists():
            pytest.skip("Hub 3 path not present")

        qcvn_bundles = hub3_bridge.load_master_catalog(category="02_qcvn")
        assert len(qcvn_bundles) >= 12
        for b in qcvn_bundles:
            assert b.category == "02_qcvn"

    def test_load_master_catalog_limit(self, hub3_bridge: Hub3Bridge):
        """Verify limit parameter caps bundle count."""
        if not hub3_bridge.hub3_path.exists():
            pytest.skip("Hub 3 path not present")

        bundles = hub3_bridge.load_master_catalog(limit=5)
        assert len(bundles) == 5

    def test_reconciles_missing_replaces_from_ssot(self, hub3_bridge: Hub3Bridge):
        """Verify Master Catalog (ADR-0047 SSOT) restores replaces relations missing in metadata.yaml."""
        if not hub3_bridge.hub3_path.exists():
            pytest.skip("Hub 3 path not present")

        bundles = hub3_bridge.load_master_catalog()
        bundle_map = {b.slug: b for b in bundles}

        # QCVN 06:2022/BXD replaces QCVN 06:2020/BXD
        qcvn06 = bundle_map.get("qcvn_06_2022_bxd")
        assert qcvn06 is not None
        assert "QCVN 06:2020/BXD" in qcvn06.replaces

        # Nghị định 217/2026/NĐ-CP replaces 15/2021/NĐ-CP & 175/2024/NĐ-CP
        nd217 = bundle_map.get("nghi_dinh_217_2026_nd_cp")
        assert nd217 is not None
        assert "15/2021/NĐ-CP" in nd217.replaces
        assert "175/2024/NĐ-CP" in nd217.replaces


# ---------------------------------------------------------------------------
# Test Suite: Cryptographic SHA-256 Verifier (ADR-0059)
# ---------------------------------------------------------------------------

class TestSha256Verification:
    """Tests for streaming 64KB SHA-256 verification and status classification."""

    def test_verify_real_bundle_verified(self, hub3_bridge: Hub3Bridge):
        """Verify real bundle returns VERIFIED when hash matches."""
        if not hub3_bridge.hub3_path.exists():
            pytest.skip("Hub 3 path not present")

        bundles = hub3_bridge.load_master_catalog(category="03_tcvn", limit=1)
        assert len(bundles) == 1
        bundle = bundles[0]
        status = hub3_bridge.verify_bundle_sha256(bundle)
        assert status == ShaVerificationStatus.VERIFIED.value
        assert bundle.is_verified is True

    def test_verify_tampered_pdf(self, hub3_bridge: Hub3Bridge):
        """Verify TAMPERED status when PDF bytes do not match expected hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "tampered.pdf"
            pdf_path.write_bytes(b"Modified PDF content that does not match official gazette hash")

            bundle = Hub3BundleInfo(
                slug="test_tampered",
                category="01_vbpl",
                registry_id="test-tampered-id",
                document_number="999/2026/NĐ-CP",
                title="Test Tampered",
                doc_type="Nghị định",
                issued_by="Chính phủ",
                issued_date="2026-01-01",
                effective_date="2026-01-01",
                status="active",
                validity_status="ACTIVE",
                bundle_path="legal_docs/01_vbpl/test_tampered/",
                bundle_dir=tmpdir,
                markdown_path=str(Path(tmpdir) / "test_tampered.md"),
                pdf_path=str(pdf_path),
                pdf_sha256="0000000000000000000000000000000000000000000000000000000000000000",
                canonical_id="VBPL/999/2026/NĐ-CP",
                file_name="tampered.pdf",
                is_statutory=True,
            )

            status = hub3_bridge.verify_bundle_sha256(bundle)
            assert status == ShaVerificationStatus.TAMPERED.value
            assert bundle.is_verified is False

    def test_verify_no_source_pdf(self, hub3_bridge: Hub3Bridge):
        """Verify NO_SOURCE status when PDF file does not exist on disk."""
        bundle = Hub3BundleInfo(
            slug="test_missing_source",
            category="01_vbpl",
            registry_id="missing-source",
            document_number="888/2026/NĐ-CP",
            title="Missing Source",
            doc_type="Nghị định",
            issued_by="Chính phủ",
            issued_date="2026-01-01",
            effective_date="2026-01-01",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/01_vbpl/missing/",
            bundle_dir="/non/existent/dir",
            markdown_path="/non/existent/dir/missing.md",
            pdf_path="/non/existent/path/doc.pdf",
            pdf_sha256="abc123def456",
            canonical_id="VBPL/888/2026/NĐ-CP",
            is_statutory=True,
        )
        status = hub3_bridge.verify_bundle_sha256(bundle)
        assert status == ShaVerificationStatus.NO_SOURCE.value

    def test_verify_non_statutory(self, hub3_bridge: Hub3Bridge):
        """Verify NON_STATUTORY status for appendices and comparison tables."""
        bundle = Hub3BundleInfo(
            slug="bang_so_sanh_thay_doi",
            category="04_appendices",
            registry_id="bang-so-sanh",
            document_number="APPENDIX-01",
            title="Bảng so sánh",
            doc_type="Phụ lục đối chiếu",
            issued_by="CCBA",
            issued_date="2026-01-01",
            effective_date="2026-01-01",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/04_appendices/bang_so_sanh/",
            bundle_dir="/tmp",
            markdown_path="/tmp/doc.md",
            canonical_id="VBPL/APPENDIX-01",
            is_statutory=False,
        )
        status = hub3_bridge.verify_bundle_sha256(bundle)
        assert status == ShaVerificationStatus.NON_STATUTORY.value


# ---------------------------------------------------------------------------
# Test Suite: Markdown Cleaner & Frontmatter Stripping
# ---------------------------------------------------------------------------

class TestMarkdownCleaner:
    """Tests for stripping YAML frontmatter from OKF v2.4 Markdown."""

    def test_strip_yaml_frontmatter(self, hub3_bridge: Hub3Bridge):
        """Verify clean extraction of Markdown text without YAML header."""
        raw_md = (
            "---\n"
            "okf_version: '2.4'\n"
            "type: technical_standard_qcvn\n"
            "title: QCVN 06:2022/BXD\n"
            "---\n\n"
            "# QCVN 06:2022/BXD\n"
            "## Điều 1. Phạm vi điều chỉnh\n"
            "Nội dung quy chuẩn an toàn cháy..."
        )
        cleaned = hub3_bridge.clean_markdown_frontmatter(raw_md)
        assert not cleaned.startswith("---")
        assert not cleaned.startswith("okf_version")
        assert cleaned.startswith("# QCVN 06:2022/BXD")
        assert "Điều 1. Phạm vi điều chỉnh" in cleaned

    def test_no_frontmatter_unchanged(self, hub3_bridge: Hub3Bridge):
        """Verify text without frontmatter remains intact."""
        raw_md = "# Title\n\nSome text content."
        cleaned = hub3_bridge.clean_markdown_frontmatter(raw_md)
        assert cleaned == raw_md

    def test_strip_yaml_frontmatter_bom_and_crlf(self, hub3_bridge: Hub3Bridge):
        """Verify handling of UTF-8 BOM, CRLF line endings, and whitespace."""
        raw_crlf = "\ufeff---\r\ntitle: Sample Doc\r\nstatus: active\r\n---\r\n\r\n# Main Title\r\nBody text."
        cleaned = hub3_bridge.clean_markdown_frontmatter(raw_crlf)
        assert not cleaned.startswith("\ufeff")
        assert not cleaned.startswith("---")
        assert cleaned.startswith("# Main Title")


# ---------------------------------------------------------------------------
# Test Suite: Bidirectional ID Resolver (Luật, QCVN, TCVN)
# ---------------------------------------------------------------------------

class TestBidirectionalIdResolver:
    """Tests for uniform canonical ID resolution across Luật, QCVN, and TCVN."""

    def test_canonical_id_computation(self, hub3_bridge: Hub3Bridge):
        """Verify canonical IDs avoid redundant filename duplication for all document types."""
        # 1. Luật / Nghị định
        id_law = hub3_bridge._compute_canonical_id("55/2024/QH15", "luat_phong_chay")
        assert id_law == "VBPL/55/2024/QH15"

        id_nd = hub3_bridge._compute_canonical_id("217/2026/NĐ-CP", "nghi_dinh_217")
        assert id_nd == "VBPL/217/2026/NĐ-CP"

        # 2. QCVN
        id_qcvn = hub3_bridge._compute_canonical_id("QCVN 06:2022/BXD", "qcvn_06_2022_bxd")
        assert id_qcvn == "VBPL/QCVN_06_2022/BXD"
        assert not id_qcvn.endswith("_qcvn_06_2022_bxd")

        # 3. TCVN
        id_tcvn = hub3_bridge._compute_canonical_id("TCVN 7336:2021", "tcvn_7336_2021")
        assert id_tcvn == "VBPL/TCVN_7336_2021"
        assert not id_tcvn.endswith("_tcvn_7336_2021")

        # 4. TCXD and TCXDVN
        id_tcxd = hub3_bridge._compute_canonical_id("TCXD 205:1998", "tcxd_205_1998")
        assert id_tcxd == "VBPL/TCXD_205_1998"

        # 5. Appendix / Phụ lục
        id_app = hub3_bridge._compute_canonical_id("APPENDIX-XD-2025-2014", "bang_so_sanh")
        assert id_app == "VBPL/APPENDIX-XD-2025-2014"

    def test_build_canonical_id_map_and_resolution(self, hub3_bridge: Hub3Bridge):
        """Verify bidirectional mapping resolves aliases, filenames, and slugs."""
        bundle_qcvn = Hub3BundleInfo(
            slug="qcvn_06_2022_bxd",
            category="02_qcvn",
            registry_id="qcvn-06-2022-bxd",
            document_number="QCVN 06:2022/BXD",
            title="QCVN 06:2022/BXD",
            doc_type="Quy chuẩn kỹ thuật quốc gia",
            issued_by="Bộ Xây dựng",
            issued_date="2022-11-30",
            effective_date="2023-01-16",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/02_qcvn/qcvn_06_2022_bxd/",
            bundle_dir="/tmp/qcvn06",
            markdown_path="/tmp/qcvn06.md",
            pdf_path="sources/qcvn_06_2022_bxd.pdf",
            canonical_id="VBPL/QCVN_06_2022/BXD",
            file_name="qcvn_06_2022_bxd.pdf",
        )
        bundle_tcvn = Hub3BundleInfo(
            slug="tcvn_7336_2021",
            category="03_tcvn",
            registry_id="tcvn-7336-2021",
            document_number="TCVN 7336:2021",
            title="TCVN 7336:2021",
            doc_type="Tiêu chuẩn quốc gia",
            issued_by="BKHCN",
            issued_date="2021-12-31",
            effective_date="2021-12-31",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/03_tcvn/tcvn_7336_2021/",
            bundle_dir="/tmp/tcvn7336",
            markdown_path="/tmp/tcvn7336.md",
            pdf_path="sources/tcvn_7336_2021.pdf",
            canonical_id="VBPL/TCVN_7336_2021",
            file_name="tcvn_7336_2021.pdf",
        )

        id_map = hub3_bridge.build_canonical_id_map([bundle_qcvn, bundle_tcvn])

        # Test resolving from slug
        assert hub3_bridge.resolve_canonical_id("qcvn_06_2022_bxd", id_map) == "VBPL/QCVN_06_2022/BXD"
        assert hub3_bridge.resolve_canonical_id("qcvn-06-2022-bxd", id_map) == "VBPL/QCVN_06_2022/BXD"

        # Test resolving from doc_number
        assert hub3_bridge.resolve_canonical_id("QCVN 06:2022/BXD", id_map) == "VBPL/QCVN_06_2022/BXD"
        assert hub3_bridge.resolve_canonical_id("TCVN 7336:2021", id_map) == "VBPL/TCVN_7336_2021"

        # Test resolving from filename
        assert hub3_bridge.resolve_canonical_id("qcvn_06_2022_bxd.pdf", id_map) == "VBPL/QCVN_06_2022/BXD"

    def test_resolve_unmapped_external_doc(self, hub3_bridge: Hub3Bridge):
        """Verify algorithmic normalization for older docs not present in Hub 3."""
        # Older QCVN
        resolved_qcvn = hub3_bridge.resolve_canonical_id("QCVN-01-2019-BXD")
        assert resolved_qcvn == "VBPL/QCVN_01_2019/BXD"

        # Older Decree
        resolved_nd = hub3_bridge.resolve_canonical_id("10_2021_nd_cp")
        assert resolved_nd == "VBPL/10/2021/NĐ-CP"

        # Older TCXD / TCXDVN
        resolved_tcxd = hub3_bridge.resolve_canonical_id("TCXD 205:1998")
        assert resolved_tcxd == "VBPL/TCXD_205_1998"

        resolved_tcxdvn = hub3_bridge.resolve_canonical_id("TCXDVN 365:2007")
        assert resolved_tcxdvn == "VBPL/TCXDVN_365_2007"

        # TCVN ISO
        resolved_iso = hub3_bridge.resolve_canonical_id("TCVN ISO 19650-1:2021")
        assert resolved_iso == "VBPL/TCVN_ISO_19650-1_2021"


# ---------------------------------------------------------------------------
# Test Suite: Fast-Path ProcessedDocument Conversion & Chunk ID Assignment
# ---------------------------------------------------------------------------

class TestProcessedDocumentConversion:
    """Tests for converting a bundle into ProcessedDocument with chunk_id and validity_status."""

    def test_convert_active_bundle(self, hub3_bridge: Hub3Bridge):
        """Verify ProcessedDocument generation with stamped chunk_id and validity_status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "test_doc.md"
            md_content = (
                "---\n"
                "title: Test Doc\n"
                "---\n\n"
                "# Test Doc\n\n"
                "Điều 1. Phạm vi điều chỉnh\n"
                "Quy định chi tiết các điều kiện áp dụng.\n\n"
                "Điều 2. Đối tượng áp dụng\n"
                "Các tổ chức, cá nhân có liên quan."
            )
            md_path.write_text(md_content, encoding="utf-8")

            bundle = Hub3BundleInfo(
                slug="test_doc",
                category="01_vbpl",
                registry_id="test-doc-id",
                document_number="100/2026/NĐ-CP",
                title="Nghị định 100",
                doc_type="Nghị định",
                issued_by="Chính phủ",
                issued_date="2026-05-01",
                effective_date="2026-07-01",
                status="active",
                validity_status="ACTIVE",
                bundle_path="legal_docs/01_vbpl/test_doc/",
                bundle_dir=tmpdir,
                markdown_path=str(md_path),
                pdf_path="test_doc.pdf",
                canonical_id="VBPL/100/2026/NĐ-CP",
                file_name="test_doc.pdf",
            )

            chunker = DocumentChunker()
            proc_doc = hub3_bridge.convert_bundle_to_processed_doc(bundle, chunker=chunker)

            assert isinstance(proc_doc, ProcessedDocument)
            assert proc_doc.identity.doc_id == "VBPL/100/2026/NĐ-CP"
            assert proc_doc.metadata.validity_status == "ACTIVE"
            assert len(proc_doc.chunks) > 0

            # Verify chunk_id format '{doc_id}::p1::c{idx}' and validity_status
            for idx, c in enumerate(proc_doc.chunks, start=1):
                assert c.chunk_id == f"VBPL/100/2026/NĐ-CP::p1::c{idx}"
                assert c.doc_id == "VBPL/100/2026/NĐ-CP"
                assert c.validity_status == "ACTIVE"
                # Check to_dict() includes validity_status
                c_dict = c.to_dict()
                assert c_dict["validity_status"] == "ACTIVE"
                assert c_dict["chunk_id"] == c.chunk_id

    def test_convert_outdated_bundle(self, hub3_bridge: Hub3Bridge):
        """Verify outdated document chunks carry OUTDATED status (preventing Milvus default to ACTIVE)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "expired_doc.md"
            md_path.write_text("# Expired Doc\n\nĐiều 1. Nội dung cũ.", encoding="utf-8")

            bundle = Hub3BundleInfo(
                slug="expired_doc",
                category="01_vbpl",
                registry_id="expired-doc-id",
                document_number="10/2021/NĐ-CP",
                title="Nghị định 10",
                doc_type="Nghị định",
                issued_by="Chính phủ",
                issued_date="2021-02-09",
                effective_date="2021-02-09",
                status="expired",
                validity_status="OUTDATED",
                bundle_path="legal_docs/01_vbpl/expired_doc/",
                bundle_dir=tmpdir,
                markdown_path=str(md_path),
                canonical_id="VBPL/10/2021/NĐ-CP",
                file_name="expired_doc.pdf",
            )

            proc_doc = hub3_bridge.convert_bundle_to_processed_doc(bundle)
            assert proc_doc.metadata.validity_status == "OUTDATED"
            for c in proc_doc.chunks:
                assert c.validity_status == "OUTDATED"
                assert c.to_dict()["validity_status"] == "OUTDATED"

    def test_convert_appendix_bundle_matches_identity(self, hub3_bridge: Hub3Bridge):
        """Verify appendix documents maintain 100% identical doc_id across identity and chunks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "appendix.md"
            md_path.write_text("# Appendix\n\nNội dung phụ lục.", encoding="utf-8")

            bundle = Hub3BundleInfo(
                slug="bang_so_sanh_luat_xay_dung_2025_vs_2014",
                category="04_appendices",
                registry_id="bang-so-sanh-xd",
                document_number="APPENDIX-XD-2025-2014",
                title="Bảng so sánh Luật Xây dựng",
                doc_type="Phụ lục đối chiếu",
                issued_by="CCBA",
                issued_date="2025-01-01",
                effective_date="2025-01-01",
                status="active",
                validity_status="ACTIVE",
                bundle_path="legal_docs/04_appendices/bang_so_sanh_luat_xay_dung_2025_vs_2014/",
                bundle_dir=tmpdir,
                markdown_path=str(md_path),
                canonical_id="VBPL/APPENDIX-XD-2025-2014",
                file_name="bang_so_sanh.pdf",
                is_statutory=False,
            )

            proc_doc = hub3_bridge.convert_bundle_to_processed_doc(bundle)
            assert proc_doc.identity.doc_id == "VBPL/APPENDIX-XD-2025-2014"
            assert proc_doc.identity.doc_id == bundle.canonical_id
            for idx, c in enumerate(proc_doc.chunks, start=1):
                assert c.doc_id == "VBPL/APPENDIX-XD-2025-2014"
                assert c.chunk_id == f"VBPL/APPENDIX-XD-2025-2014::p1::c{idx}"

    def test_convert_all_60_bundles_without_identity_split(self, hub3_bridge: Hub3Bridge):
        """Verify bundles convert with zero identity splitting between identity and chunks."""
        if not hub3_bridge.hub3_path.exists():
            pytest.skip("Hub 3 path not present")

        bundles = hub3_bridge.load_master_catalog()
        assert len(bundles) >= 60
        id_map = hub3_bridge.build_canonical_id_map(bundles)

        # In fast CI/local test runs, test representative sample across all categories.
        # Set RUN_ALL_60_BUNDLES=1 to run the full suite across all 60 full documents.
        if os.getenv("RUN_ALL_60_BUNDLES", "0") != "1":
            sample_bundles = []
            seen_cats = set()
            for b in bundles:
                if b.category not in seen_cats:
                    sample_bundles.append(b)
                    seen_cats.add(b.category)
            bundles = sample_bundles

        for b in bundles:
            proc_doc = hub3_bridge.convert_bundle_to_processed_doc(b, canonical_map=id_map)
            assert proc_doc.identity.doc_id == b.canonical_id
            assert proc_doc.metadata.validity_status in ("ACTIVE", "OUTDATED")
            assert proc_doc.metadata.doc_status == proc_doc.metadata.validity_status
            for idx, c in enumerate(proc_doc.chunks, start=1):
                assert c.doc_id == b.canonical_id
                assert c.chunk_id.startswith(f"{b.canonical_id}::p1::")
                assert len(c.chunk_id) > len(f"{b.canonical_id}::p1::")
                assert c.validity_status == proc_doc.metadata.validity_status

    def test_fast_path_chunker_no_llm_call(self, hub3_bridge: Hub3Bridge):
        """Verify Fast-Path chunking executes 100% locally with zero LLM/network calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Markdown containing a table larger than TABLE_SUMMARY_MIN_CHARS and broken table patterns
            table_rows = ["| STT | Tên thiết bị | Thông số kỹ thuật | Ghi chú |", "| --- | --- | --- | --- |"]
            for i in range(80):
                table_rows.append(f"| {i} | Thiết bị công trình {i} | Tiêu chuẩn cấp {i} .... 12345 | Ghi chú dòng {i} |")
            large_table = "\n".join(table_rows)

            md_content = f"# QCVN Test Document\n\nĐiều 1. Quy định kỹ thuật\n\n{large_table}\n"
            md_path = Path(tmpdir) / "large_table_doc.md"
            md_path.write_text(md_content, encoding="utf-8")

            bundle = Hub3BundleInfo(
                slug="test_fast_chunk_llm",
                category="02_qcvn",
                registry_id="reg-fast-llm",
                document_number="QCVN 99:2026/BXD",
                title="QCVN 99",
                doc_type="Quy chuẩn",
                issued_by="BXD",
                issued_date="2026-01-01",
                effective_date="2026-01-01",
                status="active",
                validity_status="ACTIVE",
                bundle_path="legal_docs/02_qcvn/test_fast_chunk_llm/",
                bundle_dir=tmpdir,
                markdown_path=str(md_path),
                canonical_id="VBPL/QCVN_99_2026/BXD",
                file_name="qcvn_99.pdf",
            )

            with patch("ingestion.chunking._generate_table_summary") as mock_sum, \
                 patch("ingestion.chunking._correct_broken_table_with_vision") as mock_vis, \
                 patch("core.ai_gateway_client.AIGatewayClient.complete_sync") as mock_llm:

                mock_sum.side_effect = AssertionError("Table summarization LLM call must not be invoked in Fast-Path!")
                mock_vis.side_effect = AssertionError("Table vision correction LLM call must not be invoked in Fast-Path!")
                mock_llm.side_effect = AssertionError("AIGatewayClient LLM call must not be invoked in Fast-Path!")

                proc_doc = hub3_bridge.convert_bundle_to_processed_doc(bundle)

                assert len(proc_doc.chunks) > 0
                mock_sum.assert_not_called()
                mock_vis.assert_not_called()
                mock_llm.assert_not_called()

    def test_fast_path_chunker_with_passed_chunker(self, hub3_bridge: Hub3Bridge):
        """Verify passing an existing DocumentChunker also disables LLM table features."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "test.md"
            md_path.write_text("# Doc\n\n| A | B |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")

            bundle = Hub3BundleInfo(
                slug="test_custom_chunker",
                category="01_vbpl",
                registry_id="reg-custom",
                document_number="01/2026/TT-BXD",
                title="TT 01",
                doc_type="Thông tư",
                issued_by="BXD",
                issued_date="2026-01-01",
                effective_date="2026-01-01",
                status="active",
                validity_status="ACTIVE",
                bundle_path="p/",
                bundle_dir=tmpdir,
                markdown_path=str(md_path),
                canonical_id="VBPL/01/2026/TT-BXD",
            )

            custom_chunker = DocumentChunker()
            custom_chunker.TABLE_CORRECT_ENABLED = True
            custom_chunker.TABLE_SUMMARY_ENABLED = True

            proc_doc = hub3_bridge.convert_bundle_to_processed_doc(bundle, chunker=custom_chunker)
            assert len(proc_doc.chunks) > 0
            assert custom_chunker.TABLE_CORRECT_ENABLED is False
            assert custom_chunker.TABLE_SUMMARY_ENABLED is False


# ---------------------------------------------------------------------------
# Test Suite: Neo4j Repository Updates & Graph Synchronization
# ---------------------------------------------------------------------------

class TestNeo4jGraphIntegration:
    """Tests for find_document_status and sync_hub3_topology."""

    def test_find_document_status_by_id_and_filename(self, mock_neo4j_repo):
        """Verify find_document_status MATCHES by both d.id and d.file_name."""
        repo, session = mock_neo4j_repo

        # Simulate Neo4j returning records with coalesce(d.file_name, d.id) as id
        class MockRecord:
            def __init__(self, data_dict):
                self._data = data_dict
            def data(self):
                return self._data

        class MockResult:
            def __init__(self, records):
                self.records = records
            def __aiter__(self):
                self.idx = 0
                return self
            async def __anext__(self):
                if self.idx < len(self.records):
                    r = self.records[self.idx]
                    self.idx += 1
                    return r
                raise StopAsyncIteration

        session.run.return_value = MockResult([
            MockRecord({"id": "qcvn_06_2022_bxd.pdf", "status": "ACTIVE"}),
            MockRecord({"id": "VBPL/10/2021/NĐ-CP", "status": "OUTDATED"}),
        ])

        status_map = asyncio.run(repo.find_document_status(["qcvn_06_2022_bxd.pdf", "VBPL/10/2021/NĐ-CP"]))
        assert status_map["qcvn_06_2022_bxd.pdf"] == "ACTIVE"
        assert status_map["VBPL/10/2021/NĐ-CP"] == "OUTDATED"

        # Verify query string contains OR d.file_name IN $ids
        call_args = session.run.call_args
        query_str = call_args[0][0]
        assert "d.id IN $ids OR d.file_name IN $ids" in query_str
        assert "coalesce(d.file_name, d.id) as id" in query_str

    def test_find_document_status_dual_lookup_and_superseded_normalization(self, mock_neo4j_repo):
        """Verify find_document_status returns both doc_id and file_name keys and normalizes SUPERSEDED to OUTDATED."""
        repo, session = mock_neo4j_repo

        class MockRecord:
            def __init__(self, data_dict):
                self._data = data_dict
            def data(self):
                return self._data

        class MockResult:
            def __init__(self, records):
                self.records = records
            def __aiter__(self):
                self.idx = 0
                return self
            async def __anext__(self):
                if self.idx < len(self.records):
                    r = self.records[self.idx]
                    self.idx += 1
                    return r
                raise StopAsyncIteration

        # Simulate real Cypher output returning id, doc_id, file_name, status
        session.run.return_value = MockResult([
            MockRecord({
                "id": "10_2021_nd_cp.pdf",
                "doc_id": "VBPL/10/2021/NĐ-CP",
                "file_name": "10_2021_nd_cp.pdf",
                "status": "SUPERSEDED",
            }),
            MockRecord({
                "id": "qcvn_06_2022_bxd.pdf",
                "doc_id": "VBPL/QCVN_06_2022/BXD",
                "file_name": "qcvn_06_2022_bxd.pdf",
                "status": "ACTIVE",
            }),
        ])

        status_map = asyncio.run(repo.find_document_status(["VBPL/10/2021/NĐ-CP", "qcvn_06_2022_bxd.pdf"]))
        # Both keys must be populated
        assert status_map["VBPL/10/2021/NĐ-CP"] == "OUTDATED"
        assert status_map["10_2021_nd_cp.pdf"] == "OUTDATED"
        assert status_map["VBPL/QCVN_06_2022/BXD"] == "ACTIVE"
        assert status_map["qcvn_06_2022_bxd.pdf"] == "ACTIVE"

    def test_sync_hub3_topology_replaces_and_amends(self, mock_neo4j_repo):
        """Verify sync_hub3_topology creates REPLACES and AMENDS and preserves base ACTIVE status."""
        repo, session = mock_neo4j_repo

        bundle_new = Hub3BundleInfo(
            slug="qcvn_06_2022_bxd",
            category="02_qcvn",
            registry_id="qcvn_06_2022_bxd",
            document_number="QCVN 06:2022/BXD",
            title="QCVN 06:2022/BXD",
            doc_type="Quy chuẩn",
            issued_by="BXD",
            issued_date="2022-11-30",
            effective_date="2023-01-16",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/02_qcvn/qcvn_06_2022_bxd/",
            bundle_dir="/tmp",
            markdown_path="/tmp/qcvn06.md",
            canonical_id="VBPL/QCVN_06_2022/BXD",
            file_name="qcvn_06_2022_bxd.pdf",
            replaces=["VBPL/QCVN_06_2020/BXD"],
            amendments=[{"id": "SD1-2023-QCVN-06", "title": "Sửa đổi 1:2023"}],
        )

        res = asyncio.run(repo.sync_hub3_topology([bundle_new]))
        assert res["nodes_synced"] == 1
        assert res["replaces_created"] == 1
        assert res["amends_created"] == 1

        # Check Cypher calls
        all_calls = session.run.call_args_list
        replaces_calls = [c for c in all_calls if "[:REPLACES]" in str(c)]
        amends_calls = [c for c in all_calls if "[:AMENDS]" in str(c)]

        assert len(replaces_calls) == 1
        # [:REPLACES] marks target as OUTDATED
        assert "SET target.status = 'OUTDATED'" in str(replaces_calls[0])

        assert len(amends_calls) == 1
        # [:AMENDS] preserves base active status (does NOT set base status = OUTDATED)
        assert "SET base.status = 'OUTDATED'" not in str(amends_calls[0])

    def test_sync_hub3_topology_raw_replaces_canonicalization_and_dedup(self, mock_neo4j_repo):
        """Verify raw replaces strings are resolved to canonical target IDs and deduplicated."""
        repo, session = mock_neo4j_repo

        bundle = Hub3BundleInfo(
            slug="tcvn_4601_2012",
            category="03_tcvn",
            registry_id="tcvn-4601-2012",
            document_number="TCVN 4601:2012",
            title="TCVN 4601:2012",
            doc_type="Tiêu chuẩn",
            issued_by="BKHCN",
            issued_date="2012-01-01",
            effective_date="2012-01-01",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/03_tcvn/tcvn_4601_2012/",
            bundle_dir="/tmp",
            markdown_path="/tmp/tcvn.md",
            canonical_id="VBPL/TCVN_4601_2012",
            file_name="tcvn_4601_2012.pdf",
            replaces=["TCVN 4601:1988", "TCVN-4601-1988"],  # Duplicate raw aliases
            amendments=[{"id": "SD1-2023-QCVN-06", "title": "Sửa đổi 1:2023"}],
        )

        res = asyncio.run(repo.sync_hub3_topology([bundle]))
        assert res["nodes_synced"] == 1
        assert res["replaces_created"] == 1  # Deduplicated to exactly 1 canonical target
        assert res["amends_created"] == 1

        all_calls = session.run.call_args_list
        replaces_call = [c for c in all_calls if "[:REPLACES]" in str(c)][0]
        assert replaces_call[1]["target_id"] == "VBPL/TCVN_4601_1988"

    def test_sync_hub3_topology_promulgates(self, mock_neo4j_repo):
        """Verify sync_hub3_topology creates PROMULGATES relationships."""
        repo, session = mock_neo4j_repo

        bundle = Hub3BundleInfo(
            slug="qcvn_06_2022_bxd",
            category="02_qcvn",
            registry_id="qcvn_06_2022_bxd",
            document_number="QCVN 06:2022/BXD",
            title="QCVN 06:2022/BXD",
            doc_type="Quy chuẩn",
            issued_by="BXD",
            issued_date="2022-11-30",
            effective_date="2023-01-16",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/02_qcvn/qcvn_06_2022_bxd/",
            bundle_dir="/tmp",
            markdown_path="/tmp/qcvn06.md",
            canonical_id="VBPL/QCVN_06_2022/BXD",
            file_name="qcvn_06_2022_bxd.pdf",
            promulgated_by="06/2022/TT-BXD",
        )

        res = asyncio.run(repo.sync_hub3_topology([bundle]))
        assert res["nodes_synced"] == 1
        assert res["promulgates_created"] == 1

        all_calls = session.run.call_args_list
        prom_calls = [c for c in all_calls if "[:PROMULGATES]" in str(c)]
        assert len(prom_calls) == 1
        assert "MERGE (promulgator)-[:PROMULGATES]->(base)" in str(prom_calls[0])


# ---------------------------------------------------------------------------
# Test Suite: IngestionQueue Integration
# ---------------------------------------------------------------------------

class TestIngestionQueueIntegration:
    """Tests for enqueue_bundle and enqueue_batch."""

    def test_enqueue_single_bundle(self, hub3_bridge: Hub3Bridge):
        """Verify enqueue_bundle passes file path, hash, and relative path."""
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = "msg-12345"

        bundle = Hub3BundleInfo(
            slug="test_bundle",
            category="01_vbpl",
            registry_id="reg-1",
            document_number="01/2026/TT-BXD",
            title="TT 01",
            doc_type="Thông tư",
            issued_by="BXD",
            issued_date="2026-01-01",
            effective_date="2026-01-01",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/01_vbpl/test_bundle/",
            bundle_dir="/tmp",
            markdown_path="/tmp/test_bundle.md",
            pdf_path=None,
            canonical_id="VBPL/01/2026/TT-BXD",
            sha_status=ShaVerificationStatus.VERIFIED.value,
        )

        msg_id = hub3_bridge.enqueue_bundle(bundle, mock_queue)
        assert msg_id == "msg-12345"
        mock_queue.enqueue.assert_called_once()
        args = mock_queue.enqueue.call_args[0]
        assert args[0] == "/tmp/test_bundle.md"
        assert args[2] == "legal_docs/01_vbpl/test_bundle/"

    def test_enqueue_bundle_prefers_markdown_fast_path(self, hub3_bridge: Hub3Bridge):
        """Verify enqueue_bundle always enqueues Markdown for Fast-Path even when PDF exists."""
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = "msg-fastpath"

        bundle = Hub3BundleInfo(
            slug="test_fast_path",
            category="02_qcvn",
            registry_id="reg-2",
            document_number="QCVN 06:2022/BXD",
            title="QCVN 06",
            doc_type="Quy chuẩn",
            issued_by="BXD",
            issued_date="2022-11-30",
            effective_date="2023-01-16",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/02_qcvn/qcvn_06_2022_bxd/",
            bundle_dir="/tmp",
            markdown_path="/tmp/qcvn_06_2022_bxd.md",
            pdf_path="sources/qcvn_06_2022_bxd.pdf",
            canonical_id="VBPL/QCVN_06_2022/BXD",
            sha_status=ShaVerificationStatus.VERIFIED.value,
        )

        msg_id = hub3_bridge.enqueue_bundle(bundle, mock_queue)
        assert msg_id == "msg-fastpath"
        mock_queue.enqueue.assert_called_once()
        args = mock_queue.enqueue.call_args[0]
        # Fast-Path invariant: Markdown path is passed to queue, not PDF
        assert args[0] == "/tmp/qcvn_06_2022_bxd.md"

    def test_enqueue_batch(self, hub3_bridge: Hub3Bridge):
        """Verify enqueue_batch pushes list of bundles."""
        mock_queue = MagicMock()
        mock_queue.enqueue_batch.return_value = 2

        b1 = Hub3BundleInfo(
            slug="b1", category="01_vbpl", registry_id="1", document_number="01/2026",
            title="b1", doc_type="TT", issued_by="BXD", issued_date="", effective_date="",
            status="active", validity_status="ACTIVE", bundle_path="p1/", bundle_dir="",
            markdown_path="/tmp/b1.md", canonical_id="VBPL/01/2026",
            sha_status=ShaVerificationStatus.VERIFIED.value,
        )
        b2 = Hub3BundleInfo(
            slug="b2", category="02_qcvn", registry_id="2", document_number="QCVN 01",
            title="b2", doc_type="QCVN", issued_by="BXD", issued_date="", effective_date="",
            status="active", validity_status="ACTIVE", bundle_path="p2/", bundle_dir="",
            markdown_path="/tmp/b2.md", canonical_id="VBPL/QCVN_01",
            sha_status=ShaVerificationStatus.VERIFIED.value,
        )

        count = hub3_bridge.enqueue_batch([b1, b2], mock_queue)
        assert count == 2
        mock_queue.enqueue_batch.assert_called_once()

    def test_enqueue_tampered_bundle_rejected(self, hub3_bridge: Hub3Bridge):
        """Verify enqueue_bundle and enqueue_batch reject TAMPERED bundles with ValueError."""
        mock_queue = MagicMock()

        tampered_bundle = Hub3BundleInfo(
            slug="test_tampered_doc",
            category="01_vbpl",
            registry_id="tampered-1",
            document_number="99/2026/TT-BXD",
            title="TT 99 Tampered",
            doc_type="Thông tư",
            issued_by="BXD",
            issued_date="2026-01-01",
            effective_date="2026-01-01",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/01_vbpl/test_tampered/",
            bundle_dir="/tmp",
            markdown_path="/tmp/test_tampered.md",
            pdf_path="test_tampered.pdf",
            pdf_sha256="expected_sha256_hash",
            sha_status=ShaVerificationStatus.TAMPERED.value,
            canonical_id="VBPL/99/2026/TT-BXD",
        )

        with pytest.raises(ValueError, match=r"Security Exception: Cannot enqueue TAMPERED bundle"):
            hub3_bridge.enqueue_bundle(tampered_bundle, mock_queue)

        mock_queue.enqueue.assert_not_called()

        with pytest.raises(ValueError, match=r"Security Exception: Cannot enqueue TAMPERED bundle"):
            hub3_bridge.enqueue_batch([tampered_bundle], mock_queue)

        mock_queue.enqueue_batch.assert_not_called()

    def test_enqueue_unverified_statutory_rejected(self, hub3_bridge: Hub3Bridge):
        """Verify enqueue_bundle rejects unverified statutory bundle without valid source PDF."""
        mock_queue = MagicMock()

        no_source_bundle = Hub3BundleInfo(
            slug="test_no_source",
            category="01_vbpl",
            registry_id="no-source-1",
            document_number="98/2026/TT-BXD",
            title="TT 98 No Source",
            doc_type="Thông tư",
            issued_by="BXD",
            issued_date="2026-01-01",
            effective_date="2026-01-01",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/01_vbpl/test_no_source/",
            bundle_dir="/tmp",
            markdown_path="/tmp/test_no_source.md",
            pdf_path=None,
            canonical_id="VBPL/98/2026/TT-BXD",
        )

        with pytest.raises(ValueError, match=r"Security Exception: Cannot enqueue statutory bundle"):
            hub3_bridge.enqueue_bundle(no_source_bundle, mock_queue)

        mock_queue.enqueue.assert_not_called()

        with pytest.raises(ValueError, match=r"Security Exception: Cannot enqueue statutory bundle"):
            hub3_bridge.enqueue_batch([no_source_bundle], mock_queue)

        mock_queue.enqueue_batch.assert_not_called()

    def test_enqueue_appendix_allowed_without_pdf(self, hub3_bridge: Hub3Bridge):
        """Verify enqueue_bundle allows non-statutory / appendix bundles without PDF."""
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = "msg-app"

        appendix_bundle = Hub3BundleInfo(
            slug="test_appendix",
            category="04_appendices",
            registry_id="app-1",
            document_number="APPENDIX-01",
            title="Appendix 01",
            doc_type="Phụ lục",
            issued_by="CCBA",
            issued_date="2026-01-01",
            effective_date="2026-01-01",
            status="active",
            validity_status="ACTIVE",
            bundle_path="legal_docs/04_appendices/test_appendix/",
            bundle_dir="/tmp",
            markdown_path="/tmp/test_appendix.md",
            pdf_path=None,
            canonical_id="VBPL/APPENDIX-01",
            is_statutory=False,
        )

        msg_id = hub3_bridge.enqueue_bundle(appendix_bundle, mock_queue)
        assert msg_id == "msg-app"
        mock_queue.enqueue.assert_called_once()

    def test_enqueue_unverified_bundle_auto_verifies_success(self, hub3_bridge: Hub3Bridge):
        """Verify enqueue_bundle auto-invokes verify_bundle_sha256 on unverified bundle with valid PDF."""
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = "msg-auto-ok"

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "sample.pdf"
            content = b"%PDF-1.4 sample content for sha verification"
            pdf_path.write_bytes(content)
            expected_sha = hashlib.sha256(content).hexdigest()

            md_path = Path(tmpdir) / "sample.md"
            md_path.write_text("# Sample", encoding="utf-8")

            bundle = Hub3BundleInfo(
                slug="sample_doc",
                category="01_vbpl",
                registry_id="reg-sample",
                document_number="12/2026/TT-BXD",
                title="Sample",
                doc_type="Thông tư",
                issued_by="BXD",
                issued_date="2026-01-01",
                effective_date="2026-01-01",
                status="active",
                validity_status="ACTIVE",
                bundle_path="legal_docs/01_vbpl/sample_doc/",
                bundle_dir=tmpdir,
                markdown_path=str(md_path),
                pdf_path=str(pdf_path),
                pdf_sha256=expected_sha,
                canonical_id="VBPL/12/2026/TT-BXD",
            )
            assert not bundle.is_verified

            msg_id = hub3_bridge.enqueue_bundle(bundle, mock_queue)
            assert msg_id == "msg-auto-ok"
            assert bundle.is_verified
            assert bundle.sha_status == ShaVerificationStatus.VERIFIED.value
            mock_queue.enqueue.assert_called_once()

    def test_enqueue_unverified_bundle_auto_verifies_tampered_fails(self, hub3_bridge: Hub3Bridge):
        """Verify enqueue_bundle auto-invokes verify_bundle_sha256 and rejects when PDF on disk is tampered."""
        mock_queue = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "tampered.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 modified tampered content")

            md_path = Path(tmpdir) / "tampered.md"
            md_path.write_text("# Tampered", encoding="utf-8")

            bundle = Hub3BundleInfo(
                slug="sample_tampered",
                category="01_vbpl",
                registry_id="reg-tampered",
                document_number="13/2026/TT-BXD",
                title="Sample Tampered",
                doc_type="Thông tư",
                issued_by="BXD",
                issued_date="2026-01-01",
                effective_date="2026-01-01",
                status="active",
                validity_status="ACTIVE",
                bundle_path="legal_docs/01_vbpl/sample_tampered/",
                bundle_dir=tmpdir,
                markdown_path=str(md_path),
                pdf_path=str(pdf_path),
                pdf_sha256="expected_hash_does_not_match",
                canonical_id="VBPL/13/2026/TT-BXD",
            )
            assert not bundle.is_verified

            with pytest.raises(ValueError, match=r"Security Exception: Cannot enqueue TAMPERED bundle"):
                hub3_bridge.enqueue_bundle(bundle, mock_queue)

            assert bundle.sha_status == ShaVerificationStatus.TAMPERED.value
            mock_queue.enqueue.assert_not_called()

    def test_enqueue_batch_with_in_memory_queue(self, hub3_bridge: Hub3Bridge):
        """Verify enqueue_batch works correctly with InMemoryIngestionQueue."""
        from ingestion.ingestion_queue import InMemoryIngestionQueue

        queue = InMemoryIngestionQueue()
        b1 = Hub3BundleInfo(
            slug="b1", category="01_vbpl", registry_id="1", document_number="01/2026",
            title="b1", doc_type="TT", issued_by="BXD", issued_date="", effective_date="",
            status="active", validity_status="ACTIVE", bundle_path="p1/", bundle_dir="",
            markdown_path="/tmp/b1.md", canonical_id="VBPL/01/2026",
            sha_status=ShaVerificationStatus.VERIFIED.value,
        )
        b2 = Hub3BundleInfo(
            slug="b2", category="02_qcvn", registry_id="2", document_number="QCVN 01",
            title="b2", doc_type="QCVN", issued_by="BXD", issued_date="", effective_date="",
            status="active", validity_status="ACTIVE", bundle_path="p2/", bundle_dir="",
            markdown_path="/tmp/b2.md", canonical_id="VBPL/QCVN_01",
            sha_status=ShaVerificationStatus.VERIFIED.value,
        )

        count = hub3_bridge.enqueue_batch([b1, b2], queue)
        assert count == 2
        assert len(queue.queue) == 2
        assert queue.queue[0]["file_path"] == "/tmp/b1.md"
        assert queue.queue[1]["file_path"] == "/tmp/b2.md"


# ---------------------------------------------------------------------------
# Test Suite: CLI Runner (sync_hub3_bundles.py) & Security Gate
# ---------------------------------------------------------------------------

class TestSyncHub3BundlesCLI:
    """Tests for sync_hub3_bundles CLI runner and security gate."""

    def test_cli_enqueue_auto_enables_verify_sha(self):
        import scripts.sync_hub3_bundles as sync_cli

        args = sync_cli.parse_args(["--enqueue", "--dry-run"])
        assert args.enqueue is True
        assert args.dry_run is True

        with patch("scripts.sync_hub3_bundles.Hub3Bridge") as mock_bridge_cls:
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_bridge.load_master_catalog.return_value = []

            ret = sync_cli.main(["--enqueue", "--dry-run"])
            assert ret == 0

    def test_cli_sync_neo4j_auto_enables_verify_sha(self):
        import scripts.sync_hub3_bundles as sync_cli

        args = sync_cli.parse_args(["--sync-neo4j", "--dry-run"])
        assert args.sync_neo4j is True

        with patch("scripts.sync_hub3_bundles.Hub3Bridge") as mock_bridge_cls:
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_bridge.load_master_catalog.return_value = []

            ret = sync_cli.main(["--sync-neo4j", "--dry-run"])
            assert ret == 0

    def test_cli_tampered_bundle_removed_from_sync(self):
        import scripts.sync_hub3_bundles as sync_cli

        valid_b = Hub3BundleInfo(
            slug="valid_doc", category="01_vbpl", registry_id="1", document_number="01/2026",
            title="Valid", doc_type="TT", issued_by="BXD", issued_date="", effective_date="",
            status="active", validity_status="ACTIVE", bundle_path="p1/", bundle_dir="",
            markdown_path="/tmp/valid.md", canonical_id="VBPL/01/2026",
        )
        tampered_b = Hub3BundleInfo(
            slug="tampered_doc", category="01_vbpl", registry_id="2", document_number="02/2026",
            title="Tampered", doc_type="TT", issued_by="BXD", issued_date="", effective_date="",
            status="active", validity_status="ACTIVE", bundle_path="p2/", bundle_dir="",
            markdown_path="/tmp/tampered.md", canonical_id="VBPL/02/2026",
        )

        with patch("scripts.sync_hub3_bundles.Hub3Bridge") as mock_bridge_cls:
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_bridge.load_master_catalog.return_value = [valid_b, tampered_b]

            def fake_verify(b):
                if b.slug == "tampered_doc":
                    b.sha_status = ShaVerificationStatus.TAMPERED.value
                else:
                    b.sha_status = ShaVerificationStatus.VERIFIED.value
                return b.sha_status

            mock_bridge.verify_bundle_sha256.side_effect = fake_verify
            mock_bridge.build_canonical_id_map.return_value = {"VBPL/01/2026": "VBPL/01/2026"}

            ret = sync_cli.main(["--verify-sha", "--dry-run"])
            assert ret == 0
            args, _ = mock_bridge.build_canonical_id_map.call_args
            surviving_slugs = [b.slug for b in args[0]]
            assert "tampered_doc" not in surviving_slugs
            assert "valid_doc" in surviving_slugs

    def test_cli_tampered_bundle_production_mode_raises(self, monkeypatch):
        import scripts.sync_hub3_bundles as sync_cli

        tampered_b = Hub3BundleInfo(
            slug="tampered_prod", category="01_vbpl", registry_id="1", document_number="01/2026",
            title="Tampered Prod", doc_type="TT", issued_by="BXD", issued_date="", effective_date="",
            status="active", validity_status="ACTIVE", bundle_path="p1/", bundle_dir="",
            markdown_path="/tmp/tampered.md", canonical_id="VBPL/01/2026",
        )

        with patch("scripts.sync_hub3_bundles.Hub3Bridge") as mock_bridge_cls:
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_bridge.load_master_catalog.return_value = [tampered_b]
            mock_bridge.verify_bundle_sha256.return_value = ShaVerificationStatus.TAMPERED.value

            monkeypatch.setenv("PRODUCTION_MODE", "1")
            with pytest.raises(RuntimeError, match=r"Production Security Gate: Aborting sync due to 1 TAMPERED bundles"):
                sync_cli.main(["--verify-sha", "--dry-run"])

    def test_cli_all_tampered_bundles_handled(self):
        import scripts.sync_hub3_bundles as sync_cli

        tampered_b = Hub3BundleInfo(
            slug="tampered_all", category="01_vbpl", registry_id="1", document_number="01/2026",
            title="Tampered All", doc_type="TT", issued_by="BXD", issued_date="", effective_date="",
            status="active", validity_status="ACTIVE", bundle_path="p1/", bundle_dir="",
            markdown_path="/tmp/tampered.md", canonical_id="VBPL/01/2026",
        )

        with patch("scripts.sync_hub3_bundles.Hub3Bridge") as mock_bridge_cls:
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_bridge.load_master_catalog.return_value = [tampered_b]
            mock_bridge.verify_bundle_sha256.return_value = ShaVerificationStatus.TAMPERED.value

            ret = sync_cli.main(["--verify-sha", "--dry-run"])
            assert ret == 0


# ---------------------------------------------------------------------------
# Test Suite: Verdict B-Prime Chunking & Relationships
# ---------------------------------------------------------------------------

class TestVerdictBPrimeChunkingAndRelations:
    """Tests specifically validating Grok 4.7 Verdict B-Prime implementation."""

    def test_anchor_chunking_luat_xay_dung_hierarchy(self, hub3_bridge: Hub3Bridge):
        """Verify Luat Xay dung 2025 chunks are split by HTML anchor and hierarchy parent_id is preserved."""
        if not hub3_bridge.hub3_path.exists():
            pytest.skip("Hub 3 path not present")

        bundles = hub3_bridge.load_master_catalog()
        lxd = next((b for b in bundles if "135_2025_qh15" in b.slug), None)
        assert lxd is not None

        proc_doc = hub3_bridge.convert_bundle_to_processed_doc(lxd)
        assert len(proc_doc.chunks) > 100

        chunk_map = {c.chunk_id: c for c in proc_doc.chunks}

        # Check Dieu 1
        dieu1_id = f"{lxd.canonical_id}::p1::dieu-1"
        assert dieu1_id in chunk_map
        c_dieu1 = chunk_map[dieu1_id]
        assert "Phạm vi điều chỉnh" in c_dieu1.text
        assert c_dieu1.chunk_type == "parent"
        assert c_dieu1.parent_id == ""

        # Check Dieu 3 Khoan 1
        dieu3_k1_id = f"{lxd.canonical_id}::p1::dieu-3-khoan-1"
        assert dieu3_k1_id in chunk_map
        c_k1 = chunk_map[dieu3_k1_id]
        assert "Hoạt động xây dựng gồm" in c_k1.text
        assert c_k1.chunk_type == "child"
        assert c_k1.parent_id == f"{lxd.canonical_id}::p1::dieu-3"

    def test_anchor_chunking_tcvn_span1_preserves_body(self, hub3_bridge: Hub3Bridge):
        """Verify TCVN with 1-line clauses.json span correctly captures body text until next anchor."""
        if not hub3_bridge.hub3_path.exists():
            pytest.skip("Hub 3 path not present")

        bundles = hub3_bridge.load_master_catalog()
        tcvn = next((b for b in bundles if "tcvn_7336_2021" in b.slug), None)
        assert tcvn is not None

        proc_doc = hub3_bridge.convert_bundle_to_processed_doc(tcvn)
        chunk_map = {c.chunk_id: c for c in proc_doc.chunks}

        # Check muc-1-1
        muc_1_1_id = f"{tcvn.canonical_id}::p1::muc-1-1"
        assert muc_1_1_id in chunk_map
        c_muc = chunk_map[muc_1_1_id]
        assert "chữa cháy tự động" in c_muc.text
        assert len(c_muc.text) > 30

    def test_qcvn04_content_fallback_chunking(self, hub3_bridge: Hub3Bridge):
        """Verify QCVN 04 (lacking inline anchors) extracts chunks directly from clauses.json content."""
        if not hub3_bridge.hub3_path.exists():
            pytest.skip("Hub 3 path not present")

        bundles = hub3_bridge.load_master_catalog()
        qcvn04 = next((b for b in bundles if "qcvn_04_2021" in b.slug), None)
        assert qcvn04 is not None

        proc_doc = hub3_bridge.convert_bundle_to_processed_doc(qcvn04)
        assert len(proc_doc.chunks) >= 100
        first_chunk = proc_doc.chunks[0]
        assert first_chunk.chunk_id.startswith(f"{qcvn04.canonical_id}::p1::")
        assert len(first_chunk.text) > 0

    def test_decrees_included_and_guided_by_populated(self, hub3_bridge: Hub3Bridge):
        """Verify decrees section is loaded and relationships.guides is populated from guided_by."""
        if not hub3_bridge.hub3_path.exists():
            pytest.skip("Hub 3 path not present")

        bundles = hub3_bridge.load_master_catalog()
        assert len(bundles) == 70

        # ND 217 guides Luat XD 2025
        nd217 = next((b for b in bundles if "nghi_dinh_217_2026" in b.slug), None)
        assert nd217 is not None
        assert nd217.guided_by is not None or len(nd217.guides) > 0

        proc_doc = hub3_bridge.convert_bundle_to_processed_doc(nd217)
        assert len(proc_doc.relationships.guides) > 0
        assert any("135/2025/QH15" in g or "Luat" in g for g in proc_doc.relationships.guides)


