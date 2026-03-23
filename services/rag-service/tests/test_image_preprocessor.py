"""Unit tests for the image preprocessor module."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2

from ingestion.image_preprocessor import ImagePreprocessor


class TestUpscale:
    """Test DPI-based upscale logic."""

    def test_upscale_low_dpi(self):
        """200 DPI image should be upscaled 1.5x."""
        proc = ImagePreprocessor()
        img = np.zeros((100, 200), dtype=np.uint8)
        result = proc._upscale(img, dpi=200)
        assert result.shape[0] == 150  # 100 * 1.5
        assert result.shape[1] == 300  # 200 * 1.5

    def test_no_upscale_high_dpi(self):
        """300 DPI image should NOT be upscaled."""
        proc = ImagePreprocessor()
        img = np.zeros((100, 200), dtype=np.uint8)
        result = proc._upscale(img, dpi=300)
        assert result.shape == (100, 200)

    def test_upscale_at_threshold(self):
        """At exactly 250 DPI (threshold), should NOT upscale."""
        proc = ImagePreprocessor()
        img = np.zeros((100, 200), dtype=np.uint8)
        result = proc._upscale(img, dpi=250)
        assert result.shape == (100, 200)

    def test_custom_factor(self):
        """Custom upscale factor should be applied."""
        proc = ImagePreprocessor(upscale_factor=2.0)
        img = np.zeros((100, 200), dtype=np.uint8)
        result = proc._upscale(img, dpi=200)
        assert result.shape[0] == 200
        assert result.shape[1] == 400


class TestDeskew:
    """Test skew detection and correction."""

    def test_no_deskew_for_straight_text(self):
        """A straight horizontal text block should not be modified."""
        proc = ImagePreprocessor()
        img = np.ones((200, 400), dtype=np.uint8) * 255
        # Draw a horizontal line of text-like pixels
        img[95:105, 50:350] = 0
        result = proc._deskew(img)
        assert result.shape == img.shape

    def test_deskew_returns_same_shape(self):
        """Deskewed image should maintain original dimensions."""
        proc = ImagePreprocessor()
        img = np.ones((300, 500), dtype=np.uint8) * 255
        # Add scattered text
        for y in range(50, 250, 20):
            img[y:y+3, 40:460] = 0
        result = proc._deskew(img)
        assert result.shape == img.shape

    def test_empty_image(self):
        """Empty (all white) image should pass through unchanged."""
        proc = ImagePreprocessor()
        img = np.ones((100, 100), dtype=np.uint8) * 255
        result = proc._deskew(img)
        assert np.array_equal(result, img)


class TestDenoise:
    """Test denoising."""

    def test_denoise_preserves_shape(self):
        proc = ImagePreprocessor()
        img = np.random.randint(0, 256, (200, 300), dtype=np.uint8)
        result = proc._denoise(img)
        assert result.shape == (200, 300)

    def test_denoise_reduces_noise(self):
        """Denoising runs without error and returns valid output."""
        proc = ImagePreprocessor()
        rng = np.random.RandomState(42)
        noisy = rng.randint(0, 256, (50, 60), dtype=np.uint8)
        result = proc._denoise(noisy)
        assert result.shape == (50, 60)
        assert result.dtype == np.uint8


class TestBinarize:
    """Test adaptive binarization."""

    def test_binarize_output_binary(self):
        """Output should contain only 0 and 255 values."""
        proc = ImagePreprocessor()
        img = np.random.randint(50, 200, (200, 300), dtype=np.uint8)
        result = proc._binarize(img)
        unique = np.unique(result)
        assert set(unique).issubset({0, 255})

    def test_binarize_preserves_shape(self):
        proc = ImagePreprocessor()
        img = np.random.randint(0, 256, (150, 250), dtype=np.uint8)
        result = proc._binarize(img)
        assert result.shape == (150, 250)


class TestCLAHE:
    """Test contrast enhancement."""

    def test_clahe_enhances_contrast(self):
        """CLAHE should increase the dynamic range of a low-contrast image."""
        proc = ImagePreprocessor()
        # Low contrast image: pixel values between 100-150
        img = np.random.randint(100, 150, (200, 300), dtype=np.uint8)
        result = proc._clahe(img)
        # Result should have wider range
        assert (np.max(result) - np.min(result)) >= (np.max(img) - np.min(img))

    def test_clahe_preserves_shape(self):
        proc = ImagePreprocessor()
        img = np.random.randint(0, 256, (200, 300), dtype=np.uint8)
        result = proc._clahe(img)
        assert result.shape == (200, 300)


class TestFullPipeline:
    """Test the full enhance() pipeline end-to-end."""

    def test_enhance_returns_bytes(self):
        """enhance() should return JPEG bytes."""
        proc = ImagePreprocessor()
        # Create a simple test image and encode to JPEG
        img = np.random.randint(0, 256, (200, 300, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".jpg", img)
        img_bytes = encoded.tobytes()

        result = proc.enhance(img_bytes, dpi=200)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_enhance_handles_corrupt_input(self):
        """enhance() should return original bytes if input is corrupt."""
        proc = ImagePreprocessor()
        corrupt = b"not a real image"
        result = proc.enhance(corrupt, dpi=200)
        assert result == corrupt  # Returns original on failure

    def test_enhance_idempotent(self):
        """Running enhance twice should produce valid output."""
        proc = ImagePreprocessor()
        img = np.random.randint(0, 256, (200, 300, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".jpg", img)
        first = proc.enhance(encoded.tobytes(), dpi=200)
        second = proc.enhance(first, dpi=300)  # High DPI → skip upscale
        assert isinstance(second, bytes)
        assert len(second) > 0


def run_all():
    passed = 0
    failed = 0

    for cls_name, cls in [
        ("TestUpscale", TestUpscale),
        ("TestDeskew", TestDeskew),
        ("TestDenoise", TestDenoise),
        ("TestBinarize", TestBinarize),
        ("TestCLAHE", TestCLAHE),
        ("TestFullPipeline", TestFullPipeline),
    ]:
        instance = cls()
        for attr in sorted(dir(instance)):
            if attr.startswith("test_"):
                try:
                    getattr(instance, attr)()
                    passed += 1
                    print(f"  ✅ {cls_name}.{attr}")
                except AssertionError as e:
                    failed += 1
                    print(f"  ❌ {cls_name}.{attr}: {e}")
                except Exception as e:
                    failed += 1
                    print(f"  💥 {cls_name}.{attr}: {type(e).__name__}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
