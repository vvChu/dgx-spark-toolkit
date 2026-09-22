"""Unit tests for api.routers.preview (SECURITY-CRITICAL path traversal)."""
import os
import tempfile
from unittest.mock import patch, MagicMock

os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

from api.routers.preview import _SAFE_SOURCE_RE, _resolve_pdf


class TestSafeSourceRegex:
    def test_accepts_valid_ids(self):
        for s in ["TT/123-2024", "doc_name.pdf", "ns/number", "simple123"]:
            assert _SAFE_SOURCE_RE.match(s), f"Should accept: {s}"

    def test_rejects_traversal(self):
        # Note: ".." is caught by a separate check in the endpoint, not the regex
        # The regex allows ./- chars. These are rejected because they contain
        # chars outside [a-zA-Z0-9._/\-]
        assert not _SAFE_SOURCE_RE.match("foo;rm -rf")  # semicolon + space
        assert not _SAFE_SOURCE_RE.match("foo bar")  # space
        assert not _SAFE_SOURCE_RE.match("$HOME")  # dollar sign
        assert not _SAFE_SOURCE_RE.match("foo'bar")  # quote


class TestResolvePdf:
    def test_direct_match(self):
        with tempfile.TemporaryDirectory() as d:
            pdf = os.path.join(d, "test.pdf")
            open(pdf, "w").close()
            assert _resolve_pdf("test", d) == pdf

    def test_walk_match(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "sub")
            os.makedirs(sub)
            pdf = os.path.join(sub, "abc_test_xyz.pdf")
            open(pdf, "w").close()
            result = _resolve_pdf("test", d)
            assert result is not None
            assert result.endswith(".pdf")

    def test_no_match(self):
        with tempfile.TemporaryDirectory() as d:
            assert _resolve_pdf("nonexistent", d) is None


class TestPreviewEndpoint:
    def test_dotdot_rejected(self, client):
        resp = client.get("/preview?source=../../etc/passwd&page=1")
        assert resp.status_code == 400

    def test_invalid_chars_rejected(self, client):
        resp = client.get("/preview?source=foo;rm+-rf&page=1")
        assert resp.status_code == 400

    def test_not_found(self, client):
        with patch("api.routers.preview.get_settings") as mock_s:
            mock_s.return_value = MagicMock(PDF_DIR="/nonexistent")
            resp = client.get("/preview?source=missing_doc&page=1")
            assert resp.status_code == 404

    def test_pdf_source_dir_override(self, client):
        with tempfile.TemporaryDirectory() as d:
            pdf = os.path.join(d, "doc_env.pdf")
            open(pdf, "w").close()
            with patch.dict(os.environ, {"PDF_SOURCE_DIR": d}):
                with patch("api.routers.preview.get_settings") as mock_s:
                    mock_s.return_value = MagicMock(PDF_DIR="/nonexistent")
                    resp = client.get("/preview?source=doc_env&page=1")
                    # 500 render error on 0-byte file verifies 404 was bypassed and file was found
                    assert resp.status_code == 500
                    assert "Render error" in resp.json()["detail"]
