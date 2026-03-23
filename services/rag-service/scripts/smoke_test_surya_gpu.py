#!/usr/bin/env python3
"""Surya GPU Smoke Test — verify CUDA initialization and OCR on DGX Spark.

This script tests whether Surya OCR can initialize on CUDA and process
a sample image. Run inside the Docker container where Surya is available.

Usage (inside container):
    python3 scripts/smoke_test_surya_gpu.py

Usage (from host, via docker exec):
    docker exec rag-watcher-1 python3 scripts/smoke_test_surya_gpu.py
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def check_cuda():
    """Check CUDA availability and GPU info."""
    logger.info("=" * 60)
    logger.info("🔍 CUDA / GPU Check")
    logger.info("=" * 60)

    try:
        import torch
        logger.info(f"  PyTorch version:   {torch.__version__}")
        logger.info(f"  CUDA available:    {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"  CUDA version:      {torch.version.cuda}")
            logger.info(f"  GPU count:         {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                name = torch.cuda.get_device_name(i)
                mem = torch.cuda.get_device_properties(i).total_mem / 1e9
                logger.info(f"  GPU {i}: {name} ({mem:.1f} GB)")
            return True
        else:
            logger.warning("  ⚠️  CUDA not available — Surya will use CPU")
            return False
    except ImportError:
        logger.error("  ❌ PyTorch not installed")
        return False


def check_surya_import():
    """Check if Surya OCR modules can be imported."""
    logger.info(f"\n{'='*60}")
    logger.info("📦 Surya Import Check")
    logger.info("=" * 60)

    modules = [
        "surya.recognition",
        "surya.detection",
        "surya.layout",
    ]
    all_ok = True
    for mod in modules:
        try:
            __import__(mod)
            logger.info(f"  ✅ {mod}")
        except ImportError as e:
            logger.error(f"  ❌ {mod}: {e}")
            all_ok = False
    return all_ok


def test_surya_init(device: str = "auto"):
    """Test Surya model initialization on the specified device."""
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 Surya Init Test (device={device})")
    logger.info("=" * 60)

    os.environ["SURYA_DEVICE"] = device

    try:
        from ingestion.vision import SuryaExtractor
        t0 = time.time()
        engine = SuryaExtractor()
        init_time = time.time() - t0

        if engine.available:
            logger.info(f"  ✅ Surya initialized on: {engine.device}")
            logger.info(f"  ⏱  Init time: {init_time:.1f}s")
            return engine
        else:
            logger.error(f"  ❌ Surya failed to initialize")
            return None
    except Exception as e:
        logger.error(f"  ❌ Surya init error: {e}")
        return None


def test_ocr(engine, device_name: str):
    """Run OCR on a synthetic test image."""
    logger.info(f"\n{'='*60}")
    logger.info(f"📝 OCR Test ({device_name})")
    logger.info("=" * 60)

    try:
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        # Create a test image with Vietnamese text
        img = Image.new("RGB", (800, 200), color="white")
        draw = ImageDraw.Draw(img)

        # Use default font (no Vietnamese support, but tests the pipeline)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except Exception:
            font = ImageFont.load_default()

        draw.text((20, 30), "CONG HOA XA HOI CHU NGHIA VIET NAM", fill="black", font=font)
        draw.text((20, 80), "Dieu 1. Pham vi dieu chinh", fill="black", font=font)
        draw.text((20, 130), "So: 12/2025/ND-CP Ha Noi, ngay 15 thang 3 nam 2025", fill="black", font=font)

        t0 = time.time()
        results = engine.ocr(img, langs=["vi"])
        ocr_time = time.time() - t0

        if results:
            texts = [r[1][0] for r in results if r and len(r) > 1 and r[1]]
            full_text = " ".join(texts)
            logger.info(f"  ✅ OCR returned {len(results)} lines in {ocr_time:.2f}s")
            logger.info(f"  📄 Text: {full_text[:120]}...")
            return True
        else:
            logger.warning(f"  ⚠️  OCR returned 0 results in {ocr_time:.2f}s")
            return False

    except Exception as e:
        logger.error(f"  ❌ OCR test failed: {e}")
        return False


def test_image_preprocess():
    """Verify image preprocessing pipeline works."""
    logger.info(f"\n{'='*60}")
    logger.info("🖼️  Image Preprocessing Test")
    logger.info("=" * 60)

    try:
        import cv2
        import numpy as np
        from ingestion.image_preprocessor import ImagePreprocessor

        proc = ImagePreprocessor()

        # Create synthetic noisy scan
        img = np.random.randint(100, 200, (300, 500, 3), dtype=np.uint8)
        # Add some "text" lines
        for y in range(50, 250, 25):
            img[y:y+2, 30:470] = 0

        _, encoded = cv2.imencode(".jpg", img)
        raw_bytes = encoded.tobytes()

        t0 = time.time()
        enhanced = proc.enhance(raw_bytes, dpi=200)
        proc_time = time.time() - t0

        logger.info(f"  ✅ Preprocessing OK: {len(raw_bytes)} → {len(enhanced)} bytes in {proc_time:.3f}s")
        return True

    except Exception as e:
        logger.error(f"  ❌ Preprocessing failed: {e}")
        return False


def main():
    logger.info("🧪 SURYA GPU SMOKE TEST")
    logger.info(f"   Device: {os.environ.get('SURYA_DEVICE', 'auto')}")
    logger.info(f"   CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES', 'not set')}")

    results = {}

    # 1. CUDA check
    results["cuda"] = check_cuda()

    # 2. Import check
    results["imports"] = check_surya_import()

    # 3. Image preprocessing check
    results["preprocess"] = test_image_preprocess()

    # 4. Surya init
    if results["imports"]:
        engine = test_surya_init("auto")
        results["init"] = engine is not None

        # 5. OCR test
        if engine:
            results["ocr"] = test_ocr(engine, engine.device)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("📊 SUMMARY")
    logger.info("=" * 60)
    for k, v in results.items():
        status = "✅" if v else "❌"
        logger.info(f"  {status} {k}")

    all_pass = all(results.values())
    logger.info(f"\n{'✅ ALL TESTS PASSED' if all_pass else '⚠️  SOME TESTS FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
