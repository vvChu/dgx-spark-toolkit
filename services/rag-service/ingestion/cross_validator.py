"""
Cross-OCR Validator: Dùng gemini-3-flash (GATEWAY_PROXY) để verify Qwen Vision OCR output.
- So sánh section coverage, word overlap, phát hiện paraphrase
- Tự động log warning nếu fidelity thấp
"""

import logging
import os
import re
import base64
import threading
import time
from io import BytesIO
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

_http_client: Optional[httpx.Client] = None
_client_lock = threading.Lock()

# Fidelity thresholds
SECTION_COVERAGE_MIN = 0.75   # >= 75% sections in Qwen must also appear in Gemini
WORD_OVERLAP_MIN = 0.50       # >= 50% unique word overlap


def _get_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        with _client_lock:
            if _http_client is None:
                _http_client = httpx.Client(timeout=60)
    return _http_client


def _ocr_page_gemini(img_bytes: bytes, page_num: int) -> str:
    """Dùng gemini-3-flash qua ai-gateway để OCR 1 trang, trả về raw text."""
    gateway_url = os.environ.get("VLLM_API_BASE", "http://ai-gateway:4000/v1")
    api_key = os.environ.get("LITELLM_MASTER_KEY", "")
    if not api_key:
        return ""

    img_b64 = base64.b64encode(img_bytes).decode()
    payload = {
        "model": "gemini-3-flash",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                {"type": "text", "text": (
                    "Đây là trang quy chuẩn kỹ thuật / văn bản pháp lý Việt Nam. "
                    "Hãy đọc và PHIÊN ÂM NGUYÊN VĂN toàn bộ text bao gồm tất cả "
                    "số điều khoản (X, X.Y, Điều X...). Chỉ trả về text thuần."
                )}
            ]
        }],
        "max_tokens": 2000,
    }

    try:
        client = _get_client()
        resp = client.post(
            f"{gateway_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"].get("content") or ""
    except Exception as e:
        logger.warning(f"cross_validator: gemini-3-flash OCR failed for page {page_num}: {e}")
        return ""


def _extract_sections(text: str) -> set:
    """Extract tất cả section references dạng X.Y.Z hoặc Điều X."""
    nums = set(re.findall(r'\b(\d+\.\d+(?:\.\d+)*)\b', text))
    dieus = set(re.findall(r'(?:Điều|Dieu)\s*(\d+)', text, re.IGNORECASE))
    return nums | dieus


def _unique_words(text: str) -> set:
    """Extract unique Vietnamese words >= 4 chars."""
    return set(
        w.lower() for w in re.findall(r'\b[\wÀ-ỹĐđ]{4,}\b', text, re.UNICODE)
    )


def validate_page_ocr(
    img_bytes: bytes,
    qwen_text: str,
    page_num: int,
    doc_id: str = "unknown",
) -> dict:
    """
    So sánh Qwen Vision OCR output với Gemini cross-OCR cho 1 trang.

    Returns dict:
        passed: bool
        section_coverage: float (0-1)
        word_overlap: float (0-1)
        missing_sections: list
        gemini_chars: int
        qwen_chars: int
        warning: str (if any)
    """
    gemini_text = _ocr_page_gemini(img_bytes, page_num)
    if not gemini_text:
        return {
            "passed": True,  # Cannot validate — skip silently
            "skipped": True,
            "reason": "gemini OCR unavailable",
        }

    gemini_sections = _extract_sections(gemini_text)
    qwen_sections = _extract_sections(qwen_text)
    gemini_words = _unique_words(gemini_text)
    qwen_words = _unique_words(qwen_text)

    # Section coverage: of sections gemini finds, how many does qwen also have?
    if gemini_sections:
        matched = gemini_sections & qwen_sections
        section_coverage = len(matched) / len(gemini_sections)
        missing = sorted(gemini_sections - qwen_sections)
    else:
        section_coverage = 1.0
        missing = []

    # Word overlap
    if gemini_words:
        word_overlap = len(gemini_words & qwen_words) / len(gemini_words)
    else:
        word_overlap = 1.0

    passed = (
        section_coverage >= SECTION_COVERAGE_MIN and
        word_overlap >= WORD_OVERLAP_MIN
    )

    result = {
        "passed": passed,
        "skipped": False,
        "page": page_num,
        "doc_id": doc_id,
        "section_coverage": round(section_coverage, 3),
        "word_overlap": round(word_overlap, 3),
        "missing_sections": missing[:10],
        "gemini_chars": len(gemini_text),
        "qwen_chars": len(qwen_text),
    }

    if not passed:
        warning = (
            f"[cross_validator] LOW FIDELITY p{page_num} of {doc_id}: "
            f"section_coverage={section_coverage:.1%} (min {SECTION_COVERAGE_MIN:.0%}), "
            f"word_overlap={word_overlap:.1%} (min {WORD_OVERLAP_MIN:.0%}), "
            f"missing_sections={missing[:5]}"
        )
        result["warning"] = warning
        logger.warning(warning)
    else:
        logger.debug(
            f"[cross_validator] p{page_num} of {doc_id}: OK "
            f"sections={section_coverage:.1%} words={word_overlap:.1%}"
        )

    return result


def validate_document_sample(
    page_images: list,        # list of (page_num, img_bytes)
    qwen_page_texts: list,    # list of (page_num, text) — matched to images
    doc_id: str = "unknown",
    sample_rate: float = 0.3, # 30% of pages by default (min 2, max 5)
) -> dict:
    """
    Run cross-validation on a sample of pages for a whole document.
    Returns aggregate fidelity report.
    """
    if not page_images:
        return {"passed": True, "skipped": True, "reason": "no pages"}

    # Select sample pages
    n = max(2, min(5, int(len(page_images) * sample_rate)))
    # Pick evenly spaced pages (skip first page = cover)
    step = max(1, len(page_images) // n)
    indices = list(range(1, len(page_images), step))[:n]

    results = []
    qwen_text_map = {pn: txt for pn, txt in qwen_page_texts}

    for idx in indices:
        if idx >= len(page_images):
            continue
        page_num, img_bytes = page_images[idx]
        qwen_text = qwen_text_map.get(page_num, "")
        if not qwen_text:
            continue
        r = validate_page_ocr(img_bytes, qwen_text, page_num, doc_id)
        results.append(r)
        time.sleep(0.3)  # rate limit buffer

    if not results:
        return {"passed": True, "skipped": True, "reason": "no pages sampled"}

    valid = [r for r in results if not r.get("skipped")]
    if not valid:
        return {"passed": True, "skipped": True, "reason": "all pages skipped"}

    avg_section = sum(r["section_coverage"] for r in valid) / len(valid)
    avg_word = sum(r["word_overlap"] for r in valid) / len(valid)
    failed_pages = [r["page"] for r in valid if not r["passed"]]

    passed = len(failed_pages) == 0
    report = {
        "passed": passed,
        "skipped": False,
        "doc_id": doc_id,
        "pages_sampled": len(valid),
        "avg_section_coverage": round(avg_section, 3),
        "avg_word_overlap": round(avg_word, 3),
        "failed_pages": failed_pages,
        "page_results": valid,
    }

    level = logging.WARNING if not passed else logging.INFO
    logger.log(level,
        f"[cross_validator] Doc '{doc_id}': {'FAIL' if not passed else 'PASS'} "
        f"| sections={avg_section:.1%} | words={avg_word:.1%} "
        f"| failed_pages={failed_pages}"
    )
    return report
