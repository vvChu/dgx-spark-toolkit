"""Pre-OCR image enhancement for scanned Vietnamese legal documents.

Optimized for the dominant scan profile in the corpus:
  - 200 DPI, 1-bit CCITT (Kodak Alaris Smart Touch scanners)
  - Grayscale with faded tông xám, noisy backgrounds
  - Dấu tiếng Việt (ơ/ờ/ở, ư/ừ/ử) that blur at low resolution

Pipeline: Upscale → Deskew → Denoise → Adaptive Binarize → CLAHE Contrast

Usage:
    from ingestion.image_preprocessor import preprocess_page_image

    enhanced_bytes = preprocess_page_image(raw_jpeg_bytes, dpi=200)
    # Pass enhanced_bytes to LLM Vision / Surya OCR
"""

import io
import logging
import os
import time

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Prometheus metrics for preprocessing performance
try:
    from prometheus_client import Histogram, Counter
    PREPROCESS_TIME = Histogram(
        "image_preprocess_seconds", "Time spent on image preprocessing per page",
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
    )
    PREPROCESS_COUNT = Counter(
        "image_preprocess_total", "Total pages preprocessed",
        ["result"]  # success, skipped, failed
    )
except (ImportError, ValueError):
    class _DummyMetric:
        def observe(self, v): pass
        def labels(self, **kw): return self
        def inc(self, amount=1): pass
    PREPROCESS_TIME = _DummyMetric()
    PREPROCESS_COUNT = _DummyMetric()

# Toggle via environment variable (default ON for production)
ENABLED = os.environ.get("IMAGE_PREPROCESS", "1") == "1"
# Watermark/seal removal — opt-in only (default OFF to avoid removing content)
REMOVE_WATERMARKS = os.environ.get("REMOVE_WATERMARKS", "0") == "1"


class ImagePreprocessor:
    """Pre-OCR image enhancement optimized for Vietnamese legal scans.

    Each step is idempotent and gracefully falls back to the input image
    if it encounters unexpected image formats or processing errors.
    """

    def __init__(
        self,
        upscale_threshold_dpi: int = 250,
        upscale_factor: float = 1.5,
        denoise_strength: int = 10,
        clahe_clip_limit: float = 2.0,
        clahe_grid_size: tuple = (8, 8),
    ):
        self.upscale_threshold_dpi = upscale_threshold_dpi
        self.upscale_factor = upscale_factor
        self.denoise_strength = denoise_strength
        self.clahe_clip_limit = clahe_clip_limit
        self.clahe_grid_size = clahe_grid_size

    def enhance(self, img_bytes: bytes, dpi: int = 200) -> bytes:
        """Full enhancement pipeline: Upscale → Deskew → Denoise → Binarize → CLAHE."""
        t_start = time.monotonic()
        try:
            # Decode
            arr = np.frombuffer(img_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                logger.warning("[PREPROCESS] Failed to decode image — returning original")
                return img_bytes

            # Convert to grayscale for processing
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Step 1: Upscale low-DPI scans
            gray = self._upscale(gray, dpi)

            # Step 2: Deskew
            gray = self._deskew(gray)

            # Step 3: Denoise
            gray = self._denoise(gray)

            # Step 4: Adaptive binarization
            gray = self._binarize(gray)

            # Step 5: CLAHE contrast enhancement
            gray = self._clahe(gray)

            # Step 6: Watermark/seal removal (opt-in)
            if REMOVE_WATERMARKS:
                gray = self._remove_seals(img, gray)

            # Encode back to JPEG
            success, encoded = cv2.imencode(".jpg", gray, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not success:
                logger.warning("[PREPROCESS] JPEG encoding failed — returning original")
                return img_bytes

            result = encoded.tobytes()
            PREPROCESS_TIME.observe(time.monotonic() - t_start)
            PREPROCESS_COUNT.labels(result="success").inc()
            return result

        except Exception as e:
            PREPROCESS_COUNT.labels(result="failed").inc()
            logger.warning(f"[PREPROCESS] Enhancement failed: {e} — returning original")
            return img_bytes

    def _upscale(self, gray: np.ndarray, dpi: int) -> np.ndarray:
        """Upscale low-resolution scans using bicubic interpolation.

        For 200 DPI input at 1.5x → ~300 DPI equivalent, which significantly
        improves recognition of Vietnamese diacritics (ơ/ờ/ở, ư/ừ/ử).
        """
        if dpi >= self.upscale_threshold_dpi:
            return gray

        h, w = gray.shape[:2]
        new_w = int(w * self.upscale_factor)
        new_h = int(h * self.upscale_factor)

        upscaled = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        logger.debug(f"[PREPROCESS] Upscaled {w}×{h} → {new_w}×{new_h} (DPI {dpi} → ~{int(dpi * self.upscale_factor)})")
        return upscaled

    def _deskew(self, gray: np.ndarray) -> np.ndarray:
        """Detect and correct scan skew using contour analysis.

        Uses cv2.minAreaRect on thresholded contours to find the dominant
        text angle. Only corrects if skew is between 0.5° and 10°.
        """
        try:
            # Threshold to detect text regions
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

            # Find contours and fit minimum bounding rectangles
            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) < 100:
                return gray

            angle = cv2.minAreaRect(coords)[-1]

            # Normalize angle: minAreaRect returns angles in [-90, 0)
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            # Only correct meaningful skew (0.5° to 10°)
            if abs(angle) < 0.5 or abs(angle) > 10:
                return gray

            h, w = gray.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(
                gray, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )
            logger.debug(f"[PREPROCESS] Deskewed by {angle:.2f}°")
            return rotated

        except Exception as e:
            logger.debug(f"[PREPROCESS] Deskew failed: {e}")
            return gray

    def _denoise(self, gray: np.ndarray) -> np.ndarray:
        """Reduce scan noise while preserving text edges.

        Uses Non-Local Means denoising — effective for the speckle noise
        common in CCITT fax compression scans.
        """
        try:
            denoised = cv2.fastNlMeansDenoising(
                gray, None,
                h=self.denoise_strength,
                templateWindowSize=7,
                searchWindowSize=21,
            )
            return denoised
        except Exception as e:
            logger.debug(f"[PREPROCESS] Denoise failed: {e}")
            return gray

    def _binarize(self, gray: np.ndarray) -> np.ndarray:
        """Adaptive binarization — superior to raw CCITT 1-bit.

        Uses Gaussian adaptive thresholding which handles uneven lighting
        and preserves thin strokes of Vietnamese diacritics.
        """
        try:
            binary = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=15,  # Neighborhood for threshold calculation
                C=8,           # Constant subtracted from mean
            )
            return binary
        except Exception as e:
            logger.debug(f"[PREPROCESS] Binarization failed: {e}")
            return gray

    def _clahe(self, gray: np.ndarray) -> np.ndarray:
        """Contrast Limited Adaptive Histogram Equalization.

        Enhances faded text and diacritics without over-amplifying noise.
        Particularly effective for documents with uneven scan quality
        (e.g., stamped/sealed areas with lighter text).
        """
        try:
            clahe = cv2.createCLAHE(
                clipLimit=self.clahe_clip_limit,
                tileGridSize=self.clahe_grid_size,
            )
            enhanced = clahe.apply(gray)
            return enhanced
        except Exception as e:
            logger.debug(f"[PREPROCESS] CLAHE failed: {e}")
            return gray

    def _remove_seals(self, color_img: np.ndarray, gray: np.ndarray) -> np.ndarray:
        """Remove red/blue seals (con dấu) and watermarks from scanned pages.

        Vietnamese government documents typically have circular red seals
        and blue stamps overlaid on text. This step:
        1. Detects seal regions via HSV color masks (red + blue ranges)
        2. Creates a combined mask of seal areas
        3. Inpaints those regions with surrounding background

        Safety: Only modifies regions where seal colors are detected.
        Text in black/gray is preserved.
        """
        try:
            if color_img is None or len(color_img.shape) < 3:
                return gray

            hsv = cv2.cvtColor(color_img, cv2.COLOR_BGR2HSV)

            # Red seal mask (wraps around hue=0/180)
            red_lower1 = np.array([0, 70, 50])
            red_upper1 = np.array([10, 255, 255])
            red_lower2 = np.array([160, 70, 50])
            red_upper2 = np.array([180, 255, 255])
            red_mask = cv2.inRange(hsv, red_lower1, red_upper1) | cv2.inRange(hsv, red_lower2, red_upper2)

            # Blue seal/stamp mask
            blue_lower = np.array([100, 50, 50])
            blue_upper = np.array([130, 255, 255])
            blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)

            # Combined mask
            seal_mask = red_mask | blue_mask

            # Dilate to cover edges
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            seal_mask = cv2.dilate(seal_mask, kernel, iterations=2)

            # Only proceed if seal area is reasonable (<15% of page)
            seal_ratio = np.sum(seal_mask > 0) / seal_mask.size
            if seal_ratio > 0.15:
                logger.debug(f"[PREPROCESS] Seal mask too large ({seal_ratio:.1%}) — skipping removal")
                return gray

            if seal_ratio < 0.001:
                # No significant seal detected
                return gray

            # Resize mask to match gray dimensions if needed
            if seal_mask.shape != gray.shape:
                seal_mask = cv2.resize(seal_mask, (gray.shape[1], gray.shape[0]))

            # Inpaint seal regions
            result = cv2.inpaint(gray, seal_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
            logger.debug(f"[PREPROCESS] Removed seal/watermark ({seal_ratio:.1%} of page)")
            return result

        except Exception as e:
            logger.debug(f"[PREPROCESS] Seal removal failed: {e}")
            return gray


# ─── Module-level singleton ──────────────────────────────────────────────────

_preprocessor: ImagePreprocessor | None = None


def _get_preprocessor() -> ImagePreprocessor:
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = ImagePreprocessor()
    return _preprocessor


def preprocess_page_image(img_bytes: bytes, dpi: int = 200) -> bytes:
    """Public API: Preprocess a scanned page image for OCR.

    If IMAGE_PREPROCESS env var is "0", returns the input unchanged.

    Args:
        img_bytes: Raw JPEG/PNG bytes of the scanned page.
        dpi: Known or estimated DPI of the scan.

    Returns:
        Enhanced JPEG bytes (or original bytes if disabled/error).
    """
    if not ENABLED:
        PREPROCESS_COUNT.labels(result="skipped").inc()
        return img_bytes

    return _get_preprocessor().enhance(img_bytes, dpi=dpi)
