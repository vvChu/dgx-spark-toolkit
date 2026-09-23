"""Unit tests for RemoteSuryaClient and OCR microservice integration."""
import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from PIL import Image
import pytest

from ingestion.ocr_client import RemoteSuryaClient
from ingestion.vision import SuryaExtractor


def create_dummy_image(color="white", size=(100, 100)) -> Image.Image:
    """Helper to generate dummy PIL images."""
    return Image.new("RGB", size, color=color)


def dummy_image_bytes() -> bytes:
    img = create_dummy_image()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestRemoteSuryaClient:
    """Test suite for RemoteSuryaClient."""

    def test_alias_compatibility(self):
        """SuryaExtractor in vision.py must alias to RemoteSuryaClient."""
        assert SuryaExtractor is RemoteSuryaClient

    def test_client_init(self):
        """Client must initialize with correct base URL and timeout."""
        client = RemoteSuryaClient(base_url="http://custom-worker:9000/")
        assert client.base_url == "http://custom-worker:9000"
        assert client.timeout.read == 150.0
        assert client.available is True
        assert client.device == "cpu"

    @patch("ingestion.ocr_client.httpx.Client.post")
    def test_process_page_success(self, mock_post):
        """Successful worker response should return parsed ocr_raw and layout segments."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ocr_raw": [
                [[[10, 10], [50, 10], [50, 30], [10, 30]], ["Điều 1", 0.95]]
            ],
            "layout": [
                {
                    "bbox": [10, 10, 100, 50],
                    "label": "header",
                    "polygon": [[10, 10], [100, 10], [100, 50], [10, 50]],
                },
                {
                    "bbox": [10, 60, 200, 300],
                    "label": "table",
                    "polygon": [[10, 60], [200, 60], [200, 300], [10, 300]],
                }
            ],
        }
        mock_post.return_value = mock_resp

        client = RemoteSuryaClient(base_url="http://test-worker:8000")
        img_bytes = dummy_image_bytes()
        ocr_raw, layout = client.process_page(img_bytes, page_num=1)

        assert len(ocr_raw) == 1
        assert ocr_raw[0][1][0] == "Điều 1"
        assert ocr_raw[0][1][1] == 0.95

        assert len(layout) == 2
        # Check SimpleNamespace compatibility with vision.py
        seg0 = layout[0]
        assert isinstance(seg0, SimpleNamespace)
        assert getattr(seg0, "label") == "header"
        assert getattr(seg0, "bbox") == [10, 10, 100, 50]
        assert len(getattr(seg0, "polygon")) == 4

        seg1 = layout[1]
        assert getattr(seg1, "label") == "table"

    @patch("ingestion.ocr_client.httpx.Client.post")
    def test_image_hash_caching(self, mock_post):
        """Calling process_page, ocr, or extract_layout for same image should hit cache."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ocr_raw": [[[[0, 0], [10, 0], [10, 10], [0, 10]], ["Cached Text", 0.99]]],
            "layout": [{"bbox": [0, 0, 50, 50], "label": "text", "polygon": [[0, 0], [50, 0], [50, 50], [0, 50]]}],
        }
        mock_post.return_value = mock_resp

        client = RemoteSuryaClient(base_url="http://test-worker:8000")
        img_pil = create_dummy_image(color="blue")

        # Call ocr() first
        raw = client.ocr(img_pil, page_num=1)
        assert len(raw) == 1
        assert mock_post.call_count == 1

        # Call extract_layout() with identical image — should NOT call POST again
        layout = client.extract_layout(img_pil)
        assert len(layout) == 1
        assert mock_post.call_count == 1

    @patch("ingestion.ocr_client.httpx.Client.post")
    def test_worker_http_error_fallback(self, mock_post):
        """Worker 500 error should gracefully return empty lists."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        client = RemoteSuryaClient(base_url="http://test-worker:8000")
        ocr_raw, layout = client.process_page(dummy_image_bytes())
        assert ocr_raw == []
        assert layout == []

    @patch("ingestion.ocr_client.httpx.Client.post")
    def test_worker_timeout_fallback(self, mock_post):
        """Read timeout should gracefully return empty lists without raising."""
        mock_post.side_effect = httpx.ReadTimeout("Request timed out")

        client = RemoteSuryaClient(base_url="http://test-worker:8000")
        ocr_raw, layout = client.process_page(dummy_image_bytes())
        assert ocr_raw == []
        assert layout == []

    def test_empty_input(self):
        """Empty or invalid input returns empty lists immediately."""
        client = RemoteSuryaClient()
        assert client.process_page(b"") == ([], [])
        assert client.process_page(None) == ([], [])
        assert client.process_page(12345) == ([], [])
