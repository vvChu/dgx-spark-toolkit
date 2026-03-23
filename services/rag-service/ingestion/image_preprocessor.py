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

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Toggle via environment variable (default ON for production)
ENABLED = os.environ.get("IMAGE_PREPROCESS", "1") == "1"


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
        """Full enhancement pipeline: Upscale → Deskew → Denoise → Binarize → CLAHE.

        Args:
            img_bytes: Raw JPEG/PNG bytes of the scanned page.
            dpi: Known or estimated DPI of the scan.

        Returns:
            Enhanced JPEG bytes ready for OCR.
        """
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

            # Encode back to JPEG
            success, encoded = cv2.imencode(".jpg", gray, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not success:
                logger.warning("[PREPROCESS] JPEG encoding failed — returning original")
                return img_bytes

            result = encoded.tobytes()
            logger.debug(
                f"[PREPROCESS] Enhanced: {len(img_bytes)} → {len(result)} bytes, "
                f"size {gray.shape[1]}×{gray.shape[0]}"
            )
            return result

        except Exception as e:
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
        return img_bytes

    return _get_preprocessor().enhance(img_bytes, dpi=dpi)
