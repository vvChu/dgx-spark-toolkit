#!/usr/bin/env python3
"""OCR Benchmark Suite — Measure Surya v0.17.1 performance on Vietnamese legal documents.

Usage (inside rag-service container):
    python3 tests/ocr_benchmark.py

Or from host:
    docker exec rag-service python3 tests/ocr_benchmark.py

Outputs:
    - Per-page timing (detection, recognition, layout)
    - Character count & line count
    - Difficulty score from image preprocessor
    - Summary JSON for tracking improvements over time
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SURYA_DEVICE", "cpu")
os.environ.setdefault("MILVUS_HOST", "milvus-standalone")
os.environ.setdefault("VLLM_API_BASE", "http://ai-gateway:4000/v1")


def find_test_pdfs() -> list[str]:
    """Find available test PDFs."""
    candidates = [
        "/app/data/legal_test/20210402_QD347-BXD_Huong dan ap dung BIM_CT dan dung+HTKT.pdf",
        "/app/data/legal_test/Luat_50-2014-QH13_Luat Xay dung_18-6-2014.pdf",
        "/app/data/legal_test/Luat_31-2024-QH15_Luat Dat dai_thaytheLuat45-2013.pdf",
    ]
    return [p for p in candidates if os.path.exists(p)]


def render_page(doc, page_idx: int, dpi: int = 200):
    """Render a PDF page to PIL Image."""
    import fitz
    from PIL import Image

    page = doc[page_idx]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def benchmark_page(img, page_num: int, det, rec, layout_pred) -> dict:
    """Run full OCR pipeline on a single page image and collect metrics."""
    result = {"page": page_num, "errors": []}

    # Detection
    t0 = time.time()
    try:
        det_results = det([img])
        n_boxes = len(det_results[0].bboxes)
        result["detection_time_s"] = round(time.time() - t0, 2)
        result["text_regions"] = n_boxes
    except Exception as e:
        result["errors"].append(f"detection: {e}")
        result["detection_time_s"] = round(time.time() - t0, 2)
        result["text_regions"] = 0
        return result

    # Recognition
    t1 = time.time()
    try:
        polygons = [bbox.polygon for bbox in det_results[0].bboxes]
        rec_results = rec([img], polygons=[polygons])
        lines = rec_results[0].text_lines
        result["recognition_time_s"] = round(time.time() - t1, 2)
        result["text_lines"] = len(lines)
        result["total_chars"] = sum(len(l.text) for l in lines)
        # Sample text (first 3 lines)
        result["sample_lines"] = [l.text for l in lines[:3]]
        # Average confidence
        confs = [l.confidence for l in lines if hasattr(l, 'confidence')]
        result["avg_confidence"] = round(sum(confs) / len(confs), 3) if confs else 0.0
    except Exception as e:
        result["errors"].append(f"recognition: {e}")
        result["recognition_time_s"] = round(time.time() - t1, 2)
        result["text_lines"] = 0
        result["total_chars"] = 0

    # Layout
    t2 = time.time()
    try:
        layout_results = layout_pred([img])
        from collections import Counter
        labels = Counter([b.label for b in layout_results[0].bboxes])
        result["layout_time_s"] = round(time.time() - t2, 2)
        result["layout_labels"] = dict(labels)
    except Exception as e:
        result["errors"].append(f"layout: {e}")
        result["layout_time_s"] = round(time.time() - t2, 2)
        result["layout_labels"] = {}

    # Difficulty score
    try:
        from ingestion.image_preprocessor import compute_page_difficulty
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        difficulty = compute_page_difficulty(img_bytes.getvalue())
        result["difficulty"] = difficulty
    except Exception as e:
        result["difficulty"] = {"error": str(e)}

    result["total_time_s"] = round(
        result.get("detection_time_s", 0)
        + result.get("recognition_time_s", 0)
        + result.get("layout_time_s", 0), 2
    )

    return result


def main():
    import fitz
    import importlib.metadata

    pdfs = find_test_pdfs()
    if not pdfs:
        print("❌ No test PDFs found. Place PDFs in /app/data/legal_test/")
        sys.exit(1)

    version = importlib.metadata.version("surya-ocr")
    print("=" * 70)
    print(f"  OCR Benchmark — Surya v{version}")
    print(f"  Device: {os.environ.get('SURYA_DEVICE', 'auto')}")
    print(f"  Test files: {len(pdfs)}")
    print("=" * 70)

    # Load predictors once
    print("\n⏳ Loading predictors...")
    t_load = time.time()
    from surya.detection import DetectionPredictor
    from surya.foundation import FoundationPredictor
    from surya.recognition import RecognitionPredictor
    from surya.layout import LayoutPredictor

    det = DetectionPredictor()
    fp = FoundationPredictor()
    rec = RecognitionPredictor(fp)
    layout = LayoutPredictor(fp)
    print(f"  ✅ Predictors loaded ({time.time() - t_load:.1f}s)")

    all_results = []
    max_pages_per_doc = int(os.environ.get("BENCHMARK_MAX_PAGES", "3"))

    for pdf_path in pdfs:
        doc = fitz.open(pdf_path)
        basename = os.path.basename(pdf_path)
        n_pages = min(len(doc), max_pages_per_doc)

        print(f"\n📄 {basename} ({len(doc)} pages, testing {n_pages})")
        print("-" * 60)

        doc_results = {"file": basename, "total_pages": len(doc), "pages": []}

        for page_idx in range(n_pages):
            print(f"  Page {page_idx + 1}/{n_pages}...", end=" ", flush=True)
            img = render_page(doc, page_idx)
            page_result = benchmark_page(img, page_idx + 1, det, rec, layout)
            doc_results["pages"].append(page_result)

            status = "✅" if not page_result.get("errors") else "⚠️"
            print(
                f"{status} {page_result['text_regions']} regions, "
                f"{page_result.get('text_lines', 0)} lines, "
                f"{page_result.get('total_chars', 0)} chars — "
                f"{page_result['total_time_s']}s"
            )
            if page_result.get("sample_lines"):
                for line in page_result["sample_lines"][:2]:
                    print(f"      → {line[:80]}")

        doc.close()
        all_results.append(doc_results)

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    total_pages = sum(len(d["pages"]) for d in all_results)
    total_time = sum(p["total_time_s"] for d in all_results for p in d["pages"])
    total_chars = sum(p.get("total_chars", 0) for d in all_results for p in d["pages"])
    total_lines = sum(p.get("text_lines", 0) for d in all_results for p in d["pages"])

    print(f"  Pages processed:  {total_pages}")
    print(f"  Total time:       {total_time:.1f}s ({total_time / total_pages:.1f}s/page)")
    print(f"  Total characters: {total_chars:,}")
    print(f"  Total lines:      {total_lines:,}")
    print(f"  Avg chars/page:   {total_chars / total_pages:,.0f}")

    # Save JSON report
    report = {
        "surya_version": version,
        "device": os.environ.get("SURYA_DEVICE", "auto"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {
            "total_pages": total_pages,
            "total_time_s": round(total_time, 2),
            "avg_time_per_page_s": round(total_time / total_pages, 2),
            "total_chars": total_chars,
            "total_lines": total_lines,
        },
        "documents": all_results,
    }

    report_path = os.environ.get(
        "BENCHMARK_REPORT_PATH",
        "/app/tests/benchmark_report.json"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  📊 Report saved: {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
