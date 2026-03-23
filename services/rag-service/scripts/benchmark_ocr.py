#!/usr/bin/env python3
"""OCR Benchmark: Compare accuracy with/without image preprocessing.

Samples N scanned PDFs from the source directory, renders pages, and runs
OCR with and without the image preprocessing pipeline. Outputs a comparison
report with character counts, Vietnamese word detection rates, and quality
scores.

Usage:
    python3 scripts/benchmark_ocr.py [--samples 50] [--dpi 200]
"""
import argparse
import io
import logging
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


# ---------- Vietnamese quality heuristics ----------

# Common Vietnamese words (prepositions, conjunctions, articles)
_VN_WORDS = {
    "của", "và", "các", "trong", "theo", "tại", "về", "cho", "với", "được",
    "là", "có", "từ", "đến", "trên", "sau", "trước", "giữa", "như", "hoặc",
    "nhưng", "nếu", "khi", "đã", "sẽ", "phải", "không", "chưa", "này",
    "đó", "những", "một", "hai", "ba", "năm", "quy", "định", "điều",
}

_VN_DIACRITICS = re.compile(r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]", re.IGNORECASE)


def score_vietnamese_quality(text: str) -> dict:
    """Score OCR output quality for Vietnamese legal text."""
    if not text or len(text) < 10:
        return {"chars": 0, "words": 0, "vn_words": 0, "vn_ratio": 0.0, "diacritics": 0, "score": 0.0}

    words = text.split()
    vn_words = sum(1 for w in words if w.lower() in _VN_WORDS)
    diacritics = len(_VN_DIACRITICS.findall(text))

    # Quality score (0-100)
    score = 0.0
    # Character density (more text = likely better extraction)
    score += min(30, len(text) / 50)
    # Vietnamese word ratio (higher = better)
    vn_ratio = vn_words / len(words) if words else 0
    score += vn_ratio * 40
    # Diacritics density (Vietnamese text should have many)
    diacr_ratio = diacritics / len(text) if text else 0
    score += min(30, diacr_ratio * 300)

    return {
        "chars": len(text),
        "words": len(words),
        "vn_words": vn_words,
        "vn_ratio": round(vn_ratio, 3),
        "diacritics": diacritics,
        "score": round(min(100, score), 1),
    }


def find_scanned_pdfs(source_dir: str, max_samples: int = 50) -> list[str]:
    """Find candidate scanned PDFs by checking text density."""
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF (fitz) not available. Run inside Docker or install pymupdf.")
        return []

    candidates = []
    for root, _, files in os.walk(source_dir):
        for f in files:
            if not f.lower().endswith(".pdf"):
                continue
            path = os.path.join(root, f)
            try:
                doc = fitz.open(path)
                if doc.page_count < 2:
                    doc.close()
                    continue
                # Sample page 2 (page 1 often has special layout)
                page = doc[1]
                text = page.get_text("text")
                # Low text = likely scanned
                if len(text.strip()) < 200:
                    candidates.append(path)
                doc.close()
            except Exception:
                continue

            if len(candidates) >= max_samples * 3:
                break  # Enough candidates to sample from

    # Random sample
    import random
    random.seed(42)
    return random.sample(candidates, min(max_samples, len(candidates)))


def benchmark_page(page_bytes: bytes, dpi: int) -> dict:
    """Run OCR with and without preprocessing, return comparison."""
    from ingestion.image_preprocessor import ImagePreprocessor

    preprocessor = ImagePreprocessor()

    # --- Without preprocessing ---
    t0 = time.time()
    raw_score = score_vietnamese_quality(
        _simple_ocr(page_bytes)
    )
    raw_time = time.time() - t0

    # --- With preprocessing ---
    t0 = time.time()
    enhanced = preprocessor.enhance(page_bytes, dpi=dpi)
    preproc_score = score_vietnamese_quality(
        _simple_ocr(enhanced)
    )
    preproc_time = time.time() - t0

    return {
        "raw": {**raw_score, "time_ms": round(raw_time * 1000)},
        "enhanced": {**preproc_score, "time_ms": round(preproc_time * 1000)},
        "improvement": {
            "chars_delta": preproc_score["chars"] - raw_score["chars"],
            "score_delta": round(preproc_score["score"] - raw_score["score"], 1),
            "vn_words_delta": preproc_score["vn_words"] - raw_score["vn_words"],
        }
    }


def _simple_ocr(img_bytes: bytes) -> str:
    """Simple text extraction using pytesseract or fallback to char counting."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        return pytesseract.image_to_string(img, lang="vie")
    except ImportError:
        pass

    # Fallback: use Surya if available
    try:
        from ingestion.vision import _get_ocr_engine
        from PIL import Image
        engine = _get_ocr_engine()
        if engine and engine.available:
            img = Image.open(io.BytesIO(img_bytes))
            results = engine.ocr(img, langs=["vi"])
            return "\n".join([r[1][0] for r in results if r and len(r) > 1 and r[1]])
    except Exception:
        pass

    return ""


def run_benchmark(source_dir: str, num_samples: int = 50, dpi: int = 200):
    """Main benchmark runner."""
    import fitz

    logger.info(f"🔍 Finding scanned PDFs in {source_dir}...")
    pdf_files = find_scanned_pdfs(source_dir, num_samples)
    logger.info(f"📄 Found {len(pdf_files)} scanned PDFs for benchmarking\n")

    if not pdf_files:
        logger.error("No scanned PDFs found. Check source directory.")
        return

    results = []
    for i, pdf_path in enumerate(pdf_files):
        fname = os.path.basename(pdf_path)
        try:
            doc = fitz.open(pdf_path)
            # Sample page 2 (or 1 if single page)
            page_idx = min(1, doc.page_count - 1)
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("jpeg")
            doc.close()

            result = benchmark_page(img_bytes, dpi)
            result["file"] = fname
            result["page"] = page_idx + 1
            results.append(result)

            delta = result["improvement"]["score_delta"]
            symbol = "↑" if delta > 0 else "↓" if delta < 0 else "="
            logger.info(f"  [{i+1:3d}/{len(pdf_files)}] {fname[:45]:45s} "
                       f"raw={result['raw']['score']:5.1f} → enhanced={result['enhanced']['score']:5.1f} "
                       f"({symbol}{abs(delta):.1f})")

        except Exception as e:
            logger.warning(f"  [{i+1:3d}/{len(pdf_files)}] {fname[:45]:45s} FAILED: {e}")

    # Summary
    if not results:
        logger.error("\nNo results collected.")
        return

    improved = sum(1 for r in results if r["improvement"]["score_delta"] > 0)
    degraded = sum(1 for r in results if r["improvement"]["score_delta"] < 0)
    unchanged = len(results) - improved - degraded
    avg_delta = sum(r["improvement"]["score_delta"] for r in results) / len(results)
    avg_chars_delta = sum(r["improvement"]["chars_delta"] for r in results) / len(results)

    logger.info(f"\n{'='*70}")
    logger.info(f"📊 BENCHMARK RESULTS ({len(results)} pages)")
    logger.info(f"{'='*70}")
    logger.info(f"  Improved:  {improved:3d} ({improved/len(results)*100:.0f}%)")
    logger.info(f"  Degraded:  {degraded:3d} ({degraded/len(results)*100:.0f}%)")
    logger.info(f"  Unchanged: {unchanged:3d} ({unchanged/len(results)*100:.0f}%)")
    logger.info(f"  Avg score delta:  {avg_delta:+.1f}")
    logger.info(f"  Avg chars delta:  {avg_chars_delta:+.0f}")
    logger.info(f"{'='*70}")

    # Top improvements
    results.sort(key=lambda r: r["improvement"]["score_delta"], reverse=True)
    logger.info(f"\n🏆 Top 5 improvements:")
    for r in results[:5]:
        logger.info(f"  +{r['improvement']['score_delta']:.1f}  {r['file'][:50]}")

    # Worst degradations
    if degraded:
        logger.info(f"\n⚠️  Top degradations:")
        for r in results[-min(5, degraded):]:
            if r["improvement"]["score_delta"] < 0:
                logger.info(f"  {r['improvement']['score_delta']:.1f}  {r['file'][:50]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OCR Benchmark: preprocessing comparison")
    parser.add_argument("--samples", type=int, default=50, help="Number of PDFs to sample")
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI")
    parser.add_argument("--source-dir", default="/app/data/legal_docs_source",
                       help="Source directory for PDFs")
    args = parser.parse_args()
    run_benchmark(args.source_dir, args.samples, args.dpi)
