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

    def __init__(self, base_url: Optional[str] = None, *args, **kwargs):
        default_url = os.environ.get("OCR_WORKER_URL")
        if not default_url:
            try:
                from core.config import get_settings
                default_url = get_settings().OCR_WORKER_URL
            except Exception:
                default_url = "http://ocr-worker:8000"
        self.base_url = (base_url or default_url).rstrip("/")
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

    @staticmethod
    def is_service_failure(result: Any) -> bool:
        """Check if process_page result represents a service failure (None, None) or invalid/None result."""
        if result is None or not isinstance(result, (tuple, list)):
            return True
        if len(result) == 0:
            return True
        return result[0] is None or (len(result) > 1 and result[1] is None)

    def process_page(self, img_input: Any, page_num: int = 0) -> Tuple[Optional[List[Any]], Optional[List[Any]]]:
        """Process page image and return (ocr_raw, layout).

        Args:
            img_input: Image bytes, bytearray, PIL Image, or numpy ndarray.
            page_num: Page number for logging.

        Returns:
            Tuple of (ocr_raw, layout_segments) where layout_segments are
            SimpleNamespace objects matching vision.py segment schema.
            Returns (None, None) on service error (HTTP error, timeout, circuit breaker open).
            Returns ([], []) when the page is legitimately empty.
        """
        # Convert PIL or numpy array to bytes if needed
        if isinstance(img_input, Image.Image):
            buf = io.BytesIO()
            img_input.save(buf, format="PNG")
            img_bytes = buf.getvalue()
        elif isinstance(img_input, (bytes, bytearray)):
            img_bytes = bytes(img_input)
        elif hasattr(img_input, "__array_interface__") or hasattr(img_input, "__cuda_array_interface__"):
            try:
                pil_img = Image.fromarray(img_input)
                buf = io.BytesIO()
                pil_img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
            except Exception as e:
                logger.error(f"[RemoteSuryaClient] Failed to convert image array: {e}")
                return None, None
        else:
            logger.error(f"[RemoteSuryaClient] Unsupported image input type: {type(img_input)}")
            return [], []

        if not img_bytes:
            return [], []

        # Check circuit breaker
        if not self.cb.allow_request():
            logger.warning(f"[RemoteSuryaClient] Circuit breaker OPEN for ocr-worker. Skipping page {page_num}.")
            return None, None

        # Check in-memory cache
        img_hash = hashlib.sha256(img_bytes).hexdigest()
        with self._lock:
            if self._last_img_hash == img_hash:
                return list(self._last_ocr_raw), list(self._last_layout)

        client = self._get_http_client()
        url = f"{self.base_url}/process"
        files = {"file": ("page.png", img_bytes, "image/png")}

        try:
            resp = client.post(url, files=files)
            if resp.status_code != 200:
                logger.error(f"[RemoteSuryaClient] Worker returned HTTP {resp.status_code}: {resp.text}")
                self.cb.record_failure()
                return None, None

            data = resp.json()
            self.cb.record_success()

            ocr_raw = data.get("ocr_raw")
            if ocr_raw is None:
                ocr_raw = []
            raw_layout = data.get("layout")
            if raw_layout is None:
                raw_layout = []

            # Map layout to SimpleNamespace for full backward compatibility with vision.py:558-620
            layout_segments = []
            for item in raw_layout:
                if isinstance(item, dict):
                    bbox = item.get("bbox")
                    polygon = item.get("polygon") or []
                    # Defensively validate bbox: ensure a 4-element list of numbers
                    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                        if polygon and len(polygon) >= 4:
                            try:
                                xs = [p[0] for p in polygon]
                                ys = [p[1] for p in polygon]
                                bbox = [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]
                            except Exception:
                                bbox = [0.0, 0.0, 0.0, 0.0]
                        else:
                            bbox = [0.0, 0.0, 0.0, 0.0]
                    else:
                        bbox = [float(v) for v in bbox[:4]]

                    label = item.get("label") or "text"
                    layout_segments.append(
                        SimpleNamespace(
                            bbox=bbox,
                            label=str(label),
                            polygon=polygon,
                        )
                    )
                else:
                    layout_segments.append(item)

            with self._lock:
                self._last_img_hash = img_hash
                self._last_ocr_raw = ocr_raw
                self._last_layout = layout_segments

            return list(ocr_raw), list(layout_segments)

        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            logger.error(f"[RemoteSuryaClient] Connection error contacting ocr-worker ({url}): {e}")
            self.cb.record_failure()
            return None, None
        except httpx.ReadTimeout as e:
            logger.error(f"[RemoteSuryaClient] Read timeout (150s) waiting for ocr-worker on page {page_num}: {e}")
            self.cb.record_failure()
            return None, None
        except Exception as e:
            logger.error(f"[RemoteSuryaClient] Unexpected error calling ocr-worker: {e}", exc_info=True)
            self.cb.record_failure()
            return None, None

    def ocr(self, img_pil: Image.Image, langs: Optional[List[str]] = None, page_num: int = 0) -> List[Any]:
        """Backward-compatible wrapper for SuryaExtractor.ocr()."""
        ocr_raw, _ = self.process_page(img_pil, page_num=page_num)
        return ocr_raw if ocr_raw is not None else []

    def extract_layout(self, img_pil: Image.Image) -> List[Any]:
        """Backward-compatible wrapper for SuryaExtractor.extract_layout()."""
        _, layout = self.process_page(img_pil)
        return layout if layout is not None else []

    def close(self):
        """Close HTTP client connection pool."""
        with self._lock:
            if self._client and not self._client.is_closed:
                self._client.close()
                self._client = None
