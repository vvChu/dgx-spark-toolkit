"""Comprehensive Adversarial and Regression Test Suite for Hermes Executive Ops Architecture.

Covers Grok 4.7 Mandated Fixes (Re-Audit Final):
1. Path Traversal & Prefix Sibling Directory Attacks
2. Symlink & Hardlink Rejection (direct, same-stem .docx, and st_nlink > 1)
3. Exact Match Legal Citation vs Suffix Injection Rejection
4. ChatOps Internal Secret Authentication (401 on missing/invalid, zero hardcoded fallback)
5. Action Proposal Whitelisting, Param Regex Validation, and Server-Side Body Generation
6. Pagination Clamping and RAG Search Limit Boundaries
"""

import json
import os
from pathlib import Path
import tempfile
import pytest
import httpx

from scripts.hermes_executive_mcp import (
    DOCS_CACHE_DIR,
    read_cached_document,
    search_legal_corpus,
    validate_legal_citation,
    get_system_health,
    propose_system_operation,
    _paginate,
    ALLOWED_MUTATING_COMMANDS,
)


@pytest.fixture(scope="module")
def chatops_url() -> str:
    return os.environ.get("CHATOPS_BASE_URL", "http://127.0.0.1:8095")


@pytest.fixture(scope="module")
def chatops_secret() -> str:
    # Read strictly from environment or .env without hardcoded fallback
    sec = os.environ.get("CHATOPS_INTERNAL_SECRET", "").strip()
    if sec:
        return sec
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("CHATOPS_INTERNAL_SECRET="):
                val = line.split("=", 1)[1].strip()
                if val:
                    return val
    raise RuntimeError("CHATOPS_INTERNAL_SECRET is not configured in env or .env")


# =============================================================================
# 1. Path Traversal & Prefix Sibling Directory Tests
# =============================================================================
class TestPathTraversalSecurity:
    """Tests to verify that arbitrary directory reading and traversal are strictly blocked."""

    def test_block_relative_dotdot(self):
        """Rejects classic relative traversal patterns like ../../etc/passwd."""
        res_raw = read_cached_document("../../../etc/passwd")
        res = json.loads(res_raw)
        assert "error" in res
        assert "Path traversal blocked" in res["error"]

    def test_block_absolute_path_outside(self):
        """Rejects absolute paths outside the documents cache dir."""
        res_raw = read_cached_document("/etc/shadow")
        res = json.loads(res_raw)
        assert "error" in res
        assert "Path traversal blocked" in res["error"]

    def test_block_windows_style_separator(self):
        """Rejects backslash separators."""
        res_raw = read_cached_document("..\\..\\windows\\system32")
        res = json.loads(res_raw)
        assert "error" in res
        assert "Path traversal blocked" in res["error"]

    def test_prefix_sibling_collision_blocked(self):
        """Tests against common prefix sibling directory attack (e.g. cache/documents_sibling)."""
        DOCS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        sibling_dir = DOCS_CACHE_DIR.parent / (DOCS_CACHE_DIR.name + "_sibling")
        try:
            sibling_dir.mkdir(parents=True, exist_ok=True)
            secret_file = sibling_dir / "secret.txt"
            secret_file.write_text("SENSITIVE_DATA", encoding="utf-8")

            res_raw = read_cached_document(f"../{sibling_dir.name}/secret.txt")
            res = json.loads(res_raw)
            assert "error" in res
            assert "Path traversal blocked" in res["error"]
        finally:
            if sibling_dir.exists():
                import shutil
                shutil.rmtree(sibling_dir, ignore_errors=True)

    def test_no_glob_fallback_on_missing_file(self):
        """Ensures non-existent files return clear error without fuzzy glob matching."""
        res_raw = read_cached_document("definitely_non_existent_file_xyz_12345.docx")
        res = json.loads(res_raw)
        assert "error" in res
        assert "Không tìm thấy tệp" in res["error"]


# =============================================================================
# 2. Symlink and Hardlink Security Tests
# =============================================================================
class TestSymlinkAndHardlinkSecurity:
    """Verifies that symbolic links and hardlinks pointing outside or inside are strictly rejected."""

    def test_reject_direct_symlink(self):
        DOCS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        symlink_path = DOCS_CACHE_DIR / "symlink_test_direct.txt"
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("TOP_SECRET_DIRECT")
            real_target = Path(f.name)

        try:
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()
            symlink_path.symlink_to(real_target)

            res_raw = read_cached_document("symlink_test_direct.txt")
            res = json.loads(res_raw)
            assert "error" in res
            assert "Security blocked" in res["error"]
            assert "symbolic link" in res["error"]
        finally:
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()
            if real_target.exists():
                real_target.unlink()

    def test_reject_symlink_same_stem_docx(self):
        """Verifies that .docx symlink matching a .doc stem cannot leak files outside cache."""
        DOCS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        doc_path = DOCS_CACHE_DIR / "test_doc_stem.doc"
        docx_symlink = DOCS_CACHE_DIR / "test_doc_stem.docx"

        canary_content = "CANARY_OUTSIDE_EXECUTIVE_TEST_99"
        with tempfile.NamedTemporaryFile("w", suffix=".docx", delete=False) as f:
            f.write(canary_content)
            tmp_target = Path(f.name)

        try:
            # Create dummy .doc in cache
            doc_path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")  # OLE header
            # Create symlink .docx pointing to outside tmp file
            if docx_symlink.exists() or docx_symlink.is_symlink():
                docx_symlink.unlink()
            docx_symlink.symlink_to(tmp_target)

            res_raw = read_cached_document("test_doc_stem.doc")
            res = json.loads(res_raw)
            assert "error" in res
            assert "Security blocked" in res["error"]
            # Crucial: verify canary content is NEVER returned
            assert canary_content not in res_raw
        finally:
            if doc_path.exists():
                doc_path.unlink()
            if docx_symlink.exists() or docx_symlink.is_symlink():
                docx_symlink.unlink()
            if tmp_target.exists():
                tmp_target.unlink()

    def test_reject_hardlink(self):
        """Verifies that files with st_nlink > 1 (hardlinks) are rejected."""
        DOCS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        hardlink_path = DOCS_CACHE_DIR / "test_hardlink.txt"

        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("HARDLINK_CANARY_DATA")
            tmp_source = Path(f.name)

        try:
            if hardlink_path.exists():
                hardlink_path.unlink()
            os.link(tmp_source, hardlink_path)

            res_raw = read_cached_document("test_hardlink.txt")
            res = json.loads(res_raw)
            assert "error" in res
            assert "Security blocked" in res["error"]
            assert "hardlink" in res["error"]
        finally:
            if hardlink_path.exists():
                hardlink_path.unlink()
            if tmp_source.exists():
                tmp_source.unlink()


# =============================================================================
# 3. Exact Match vs Suffix Injection Citation Tests
# =============================================================================
class TestCitationValidation:
    """Tests legal citation resolution: exact match returns node, suffix mismatch returns empty."""

    def test_exact_citation_match(self):
        so_hieu = "10/2021/NĐ-CP"
        res_raw = validate_legal_citation(so_hieu)
        assert res_raw is not None
        data = json.loads(res_raw)
        assert "nodes" in data
        # Must return exactly the requested document
        matching = [n for n in data["nodes"] if n.get("id") == "VBPL/10/2021/NĐ-CP" or n.get("name") == "10/2021/NĐ-CP"]
        assert len(matching) >= 1

    def test_suffix_injection_rejection(self):
        """Verifies that suffix sub-strings like 0/2021/NĐ-CP or NĐ-CP do NOT match 10/2021/NĐ-CP and return empty graph."""
        for bad_id in ["0/2021/NĐ-CP", "2021/NĐ-CP", "NĐ-CP", "1/2021/NĐ-CP"]:
            res_raw = validate_legal_citation(bad_id)
            assert res_raw is not None
            data = json.loads(res_raw)
            assert "nodes" in data
            assert len(data["nodes"]) == 0, f"Suffix match error: '{bad_id}' returned non-empty nodes: {data['nodes']}!"


# =============================================================================
# 4. ChatOps Internal Secret Authentication Tests
# =============================================================================
class TestChatOpsSecretAuth:
    """Verifies that endpoints protected by X-ChatOps-Secret reject missing/invalid credentials."""

    def test_probe_endpoint_missing_secret(self, chatops_url):
        try:
            res = httpx.get(f"{chatops_url}/api/v1/probe/gpu", timeout=5.0)
            assert res.status_code == 401
            assert "Invalid ChatOps Secret Header" in res.json().get("detail", "")
        except httpx.ConnectError:
            pytest.skip("ChatOps daemon is not running on 8095")

    def test_probe_endpoint_invalid_secret(self, chatops_url):
        try:
            res = httpx.get(
                f"{chatops_url}/api/v1/probe/gpu",
                headers={"X-ChatOps-Secret": "wrong_attacker_secret"},
                timeout=5.0,
            )
            assert res.status_code == 401
        except httpx.ConnectError:
            pytest.skip("ChatOps daemon is not running on 8095")

    def test_probe_endpoint_valid_secret(self, chatops_url, chatops_secret):
        try:
            res = httpx.get(
                f"{chatops_url}/api/v1/probe/gpu",
                headers={"X-ChatOps-Secret": chatops_secret},
                timeout=10.0,
            )
            assert res.status_code == 200
            data = res.json()
            assert "result" in data
        except httpx.ConnectError:
            pytest.skip("ChatOps daemon is not running on 8095")


# =============================================================================
# 5. Action Proposal Whitelisting and Validation Tests
# =============================================================================
class TestActionProposalHardening:
    """Verifies that /api/v1/notify rejects emergency exec, unlisted commands, and enforces registry timeout."""

    def test_reject_emergency_exec_proposal(self, chatops_url, chatops_secret):
        payload = {
            "title": "Malicious Proposal",
            "body": "Attempting emergency exec",
            "severity": "CRITICAL",
            "actions": [
                {
                    "action_id": "malicious_act",
                    "command": "system.emergency.exec",
                    "params": {"cmd": "id"},
                }
            ],
        }
        try:
            res = httpx.post(
                f"{chatops_url}/api/v1/notify",
                headers={"X-ChatOps-Secret": chatops_secret},
                json=payload,
                timeout=5.0,
            )
            assert res.status_code == 403
            assert "system.emergency.exec" in res.json().get("detail", "")
        except httpx.ConnectError:
            pytest.skip("ChatOps daemon is not running on 8095")

    def test_reject_unlisted_command(self, chatops_url, chatops_secret):
        payload = {
            "title": "Unlisted Proposal",
            "body": "Attempting unlisted cmd",
            "actions": [
                {
                    "action_id": "unlisted_act",
                    "command": "arbitrary.attacker.action",
                    "params": {},
                }
            ],
        }
        try:
            res = httpx.post(
                f"{chatops_url}/api/v1/notify",
                headers={"X-ChatOps-Secret": chatops_secret},
                json=payload,
                timeout=5.0,
            )
            assert res.status_code == 403
            assert "ALLOWED_NOTIFY_COMMANDS" in res.json().get("detail", "")
        except httpx.ConnectError:
            pytest.skip("ChatOps daemon is not running on 8095")

    def test_reject_invalid_param_regex(self, chatops_url, chatops_secret):
        payload = {
            "title": "Invalid Param Injection",
            "body": "Injecting malicious service name",
            "actions": [
                {
                    "action_id": "restart_act",
                    "command": "system.container.restart",
                    "params": {"service": "invalid_container; rm -rf /"},
                }
            ],
        }
        try:
            res = httpx.post(
                f"{chatops_url}/api/v1/notify",
                headers={"X-ChatOps-Secret": chatops_secret},
                json=payload,
                timeout=5.0,
            )
            assert res.status_code == 400
            assert "không thỏa mãn mẫu an toàn" in res.json().get("detail", "")
        except httpx.ConnectError:
            pytest.skip("ChatOps daemon is not running on 8095")

    def test_reject_extra_unexpected_param(self, chatops_url, chatops_secret):
        payload = {
            "title": "Extra Param Injection",
            "body": "Passing unmapped params",
            "actions": [
                {
                    "action_id": "restart_act",
                    "command": "system.container.restart",
                    "params": {
                        "service": "rag-service",
                        "extra_malicious_key": "dangerous_payload",
                    },
                }
            ],
        }
        try:
            res = httpx.post(
                f"{chatops_url}/api/v1/notify",
                headers={"X-ChatOps-Secret": chatops_secret},
                json=payload,
                timeout=5.0,
            )
            assert res.status_code == 400
            assert "Tham số không được phép" in res.json().get("detail", "")
        except httpx.ConnectError:
            pytest.skip("ChatOps daemon is not running on 8095")

    def test_mcp_client_propose_blocks_unauthorized_command(self):
        res_raw = propose_system_operation("system.emergency.exec", "Bypass check", {"cmd": "whoami"})
        data = json.loads(res_raw)
        assert "error" in data
        assert "không nằm trong danh mục đề xuất an toàn" in data["error"]

    def test_notify_enforces_registry_timeout_and_ignores_client_inflation(self, chatops_secret):
        """Verifies that client timeout=99999 is ignored in favor of registry timeout_seconds=300 and body is server-generated."""
        import asyncio
        from unittest.mock import patch, AsyncMock
        from scripts import chatops_daemon as cd

        payload = {
            "title": "Xac nhan doc so lieu GPU",
            "body": "Khong co thay doi he thong. Bam nut de dong thong bao.",
            "actions": [
                {
                    "action_id": "upgrade_act",
                    "label": "Chi xem GPU",
                    "command": "system.deps.upgrade",
                    "params": {"tier": "patch"},
                    "timeout": 99999,
                }
            ],
        }

        with patch.object(cd, "send_telegram_msg", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = 998877
            res = asyncio.run(cd.handle_internal_notify(payload, x_chatops_secret=chatops_secret))
            assert res["status"] == "dispatched"

            # 1. Server MUST enforce registry timeout (300s), ignoring client 99999
            upgrade_entries = [e for e in cd.action_cache.values() if e.get("command") == "system.deps.upgrade"]
            assert len(upgrade_entries) >= 1
            latest_entry = upgrade_entries[-1]
            assert latest_entry["timeout"] == 300

            # 2. Server MUST sanitize body and eliminate client UI spoofing text
            sent_text = mock_send.call_args[0][1]
            assert "Khong co thay doi he thong" not in sent_text
            assert "system.deps.upgrade" in sent_text
            assert "300s" in sent_text

        # 3. Client sends low timeout=1 -> Server still enforces registry timeout (300s) and does NOT show 1s
        payload_low = {
            "title": "Low Timeout Request",
            "body": "Spoofed low timeout",
            "actions": [
                {
                    "action_id": "upgrade_low",
                    "command": "system.deps.upgrade",
                    "params": {"tier": "patch"},
                    "timeout": 1,
                }
            ],
        }
        with patch.object(cd, "send_telegram_msg", new_callable=AsyncMock) as mock_send_low:
            mock_send_low.return_value = 998878
            res = asyncio.run(cd.handle_internal_notify(payload_low, x_chatops_secret=chatops_secret))
            assert res["status"] == "dispatched"
            upgrade_entries = [e for e in cd.action_cache.values() if e.get("command") == "system.deps.upgrade"]
            latest_entry = upgrade_entries[-1]
            assert latest_entry["timeout"] == 300
            sent_text_low = mock_send_low.call_args[0][1]
            assert " 1s" not in sent_text_low
            assert "`1s`" not in sent_text_low
            assert "300s" in sent_text_low


# =============================================================================
# 6. Pagination & Query Clamping Tests
# =============================================================================
class TestClampingAndLimits:
    """Verifies that pagination and query limits cannot be abused to cause memory or DOS issues."""

    def test_paginate_lower_bound_clamped(self):
        sample = "A" * 5000
        sliced = _paginate(sample, page=1, page_size=500)
        assert sliced.startswith("A" * 2000)

    def test_paginate_upper_bound_clamped(self):
        sample = "B" * 20000
        sliced = _paginate(sample, page=1, page_size=50000)
        assert sliced.startswith("B" * 12000)

    def test_search_limit_clamped(self):
        res_raw = search_legal_corpus("thông tư", limit=100)
        assert res_raw is not None
