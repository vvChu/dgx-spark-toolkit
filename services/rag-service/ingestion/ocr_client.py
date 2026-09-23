import hashlib
import io
import logging
import os
import threading
from types import SimpleNamespace
from typing import Any, List, Optional, Tuple

import httpx
from PIL import Image

from core.circuit_breaker import get_circuit_breaker

logger = logging.getLogger(__name__)


class RemoteSuryaClient:
    """Client for remote Surya OCR Worker microservice.

    Provides drop-in compatibility for SuryaExtractor with:
    - process_page(img_bytes, page_num) -> (ocr_raw, layout)
    - ocr(img_pil, langs=['vi'], page_num=0) -> ocr_raw
    - extract_layout(img_pil) -> layout
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or os.environ.get("OCR_WORKER_URL", "http://ocr-worker:8000")).rstrip("/")
        # Granular timeout — 150s read buffer for CPU inference
        self.timeout = httpx.Timeout(connect=10.0, read=150.0, write=30.0, pool=10.0)
        self._client: Optional[httpx.Client] = None
        self._lock = threading.Lock()

        # Circuit breaker to prevent cascade failures when worker is down/overloaded
        self.cb = get_circuit_breaker("ocr-worker", failure_threshold=3, recovery_timeout=30.0)

        # Image cache to avoid redundant calls if ocr() and extract_layout() are called separately
        self._last_img_hash: Optional[str] = None
        self._last_ocr_raw: List[Any] = []
        self._last_layout: List[Any] = []

    def _get_http_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            with self._lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.Client(timeout=self.timeout)
        return self._client

    @property
    def available(self) -> bool:
        """Surya is considered available as long as circuit is not open."""
        return not self.cb.is_open()

    @property
    def device(self) -> str:
        return "cpu"

    def process_page(self, img_input: Any, page_num: int = 0) -> Tuple[List[Any], List[Any]]:
        """Process page image and return (ocr_raw, layout).

        Args:
            img_input: Image bytes or PIL Image.
            page_num: Page number for logging.

        Returns:
            Tuple of (ocr_raw, layout_segments) where layout_segments are
            SimpleNamespace objects matching vision.py segment schema.
        """
        # Convert PIL to bytes if needed
        if isinstance(img_input, Image.Image):
            buf = io.BytesIO()
            img_input.save(buf, format="PNG")
            img_bytes = buf.getvalue()
        elif isinstance(img_input, (bytes, bytearray)):
            img_bytes = bytes(img_input)
        else:
            logger.error(f"[RemoteSuryaClient] Unsupported image input type: {type(img_input)}")
            return [], []

        if not img_bytes:
            return [], []

        # Check circuit breaker
        if not self.cb.allow_request():
            logger.warning(f"[RemoteSuryaClient] Circuit breaker OPEN for ocr-worker. Skipping page {page_num}.")
            return [], []

        # Check in-memory cache
        img_hash = hashlib.sha256(img_bytes).hexdigest()
        with self._lock:
            if self._last_img_hash == img_hash:
                return self._last_ocr_raw, self._last_layout

        client = self._get_http_client()
        url = f"{self.base_url}/process"
        files = {"file": ("page.png", img_bytes, "image/png")}

        try:
            resp = client.post(url, files=files)
            if resp.status_code != 200:
                logger.error(f"[RemoteSuryaClient] Worker returned HTTP {resp.status_code}: {resp.text}")
                self.cb.record_failure()
                return [], []

            data = resp.json()
            self.cb.record_success()

            ocr_raw = data.get("ocr_raw", [])
            raw_layout = data.get("layout", [])

            # Map layout to SimpleNamespace for full backward compatibility with vision.py:558-620
            layout_segments = []
            for item in raw_layout:
                if isinstance(item, dict):
                    layout_segments.append(
                        SimpleNamespace(
                            bbox=item.get("bbox"),
                            label=item.get("label", "text"),
                            polygon=item.get("polygon", []),
                        )
                    )
                else:
                    layout_segments.append(item)

            with self._lock:
                self._last_img_hash = img_hash
                self._last_ocr_raw = ocr_raw
                self._last_layout = layout_segments

            return ocr_raw, layout_segments

        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            logger.error(f"[RemoteSuryaClient] Connection error contacting ocr-worker ({url}): {e}")
            self.cb.record_failure()
            return [], []
        except httpx.ReadTimeout as e:
            logger.error(f"[RemoteSuryaClient] Read timeout (150s) waiting for ocr-worker on page {page_num}: {e}")
            self.cb.record_failure()
            return [], []
        except Exception as e:
            logger.error(f"[RemoteSuryaClient] Unexpected error calling ocr-worker: {e}", exc_info=True)
            self.cb.record_failure()
            return [], []

    def ocr(self, img_pil: Image.Image, langs: Optional[List[str]] = None, page_num: int = 0) -> List[Any]:
        """Backward-compatible wrapper for SuryaExtractor.ocr()."""
        ocr_raw, _ = self.process_page(img_pil, page_num=page_num)
        return ocr_raw

    def extract_layout(self, img_pil: Image.Image) -> List[Any]:
        """Backward-compatible wrapper for SuryaExtractor.extract_layout()."""
        _, layout = self.process_page(img_pil)
        return layout

    def close(self):
        """Close HTTP client connection pool."""
        with self._lock:
            if self._client and not self._client.is_closed:
                self._client.close()
                self._client = None
