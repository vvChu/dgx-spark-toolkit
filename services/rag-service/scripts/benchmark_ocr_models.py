#!/usr/bin/env python3
"""Benchmark OCR Vision quality across models.

Renders specific PDF pages to images, sends to each model in the chain,
and compares extraction quality against known ground-truth content.

Usage:
    python3 scripts/benchmark_ocr_models.py [--page 22] [--pdf PATH]
"""
import argparse
import base64
import io
import json
import os
import re
import sys
import time

import httpx

# ── Config ──────────────────────────────────────────────────────────────────
GATEWAY_URL = os.getenv("VLLM_API_BASE", "http://ai-gateway:4000/v1")
API_KEY = os.getenv("LITELLM_MASTER_KEY", "")

MODELS = [
    "gemini-3-flash",
    "gemini-3.1-flash-lite",
    "rag-core",          # Qwen 3.5 35B local
    "gemma-3-27b",
]

SYSTEM_PROMPT = """Bạn là máy OCR thuần túy. NHIỆM VỤ DUY NHẤT: sao chép văn bản trong ảnh.

QUY TẮC BẮT BUỘC:
1. Trích xuất TOÀN BỘ nội dung pháp lý, giữ nguyên thứ tự từ trên xuống dưới
2. Giữ nguyên cấu trúc: Điều, Khoản, Điểm, Chương, Mục, Phần, Phụ lục
3. BẢNG BIỂU → Markdown table (| col1 | col2 |) — CHỈ KHI THẤY BẢNG THẬT TRONG ẢNH
4. Giữ nguyên số hiệu, ngày tháng, tên cơ quan
5. TUYỆT ĐỐI KHÔNG thêm nhận xét, giải thích, đánh số, phân tích
6. KHÔNG mô tả font, style, bold, caps
7. Mỗi đề mục/mục số (1.1, 1.2, 2.3.4...) PHẢI nằm trên dòng riêng biệt
8. KHÔNG dùng markdown heading (#), CHỈ dùng markdown cho bảng biểu (|)
9. KHÔNG viết tiếng Anh
10. CHỈ VĂN BẢN THUẦN TÚY — NGUYÊN VĂN từng chữ trong ảnh
11. KHÔNG tự sáng tạo hoặc suy luận nội dung — chỉ đọc chính xác những gì hiển thị

BỎ QUA HOÀN TOÀN (KHÔNG trích xuất):
- Logo, watermark, header điện tử
- Con dấu, chữ ký
- Số trang đứng riêng"""



# ── Ground-truth snippets for scoring ──────────────────────────────────────
# Key phrases that MUST appear in correct OCR output
GROUND_TRUTH_P21 = {
    "must_contain": [
        "Điều 34",
        "Thẩm quyền phê duyệt",
        "Thủ tướng Chính phủ",
        "quy hoạch xây dựng vùng liên tỉnh",
        "quy hoạch xây dựng vùng tỉnh",
        "vùng chức năng đặc thù",           # NOT "vùng kinh tế đặc biệt"
        "khu kinh tế",                       # NOT "khu sa lạch"
        "khu công nghệ cao",                 # NOT "phòng chống xây dựng"
        "khu du lịch",
        "khu sinh thái",
        "khu bảo tồn",
        "chuyên ngành hạ tầng kỹ thuật",     # NOT "ngãnh hạ tầng kỹ thuật về năng lượng"
        "Bộ Xây dựng tổ chức lập",
    ],
    "must_not_contain": [
        "khu sa lạch",                       # hallucinated content
        "phòng chống xây dựng đa dạng sinh học",  # hallucinated
        "năng lượng",                        # wrong word
        "| STT |",                           # fake table
        "| 1 | a |",                         # fake table
    ],
}


def render_page(pdf_path: str, page_num: int, dpi: int = 300) -> bytes:
    """Render a PDF page to JPEG bytes."""
    import fitz
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("jpeg")


def _strip_preamble(text: str) -> str:
    """Remove English/Vietnamese preamble that LLMs tend to output before actual OCR.

    Strategy:
    1. Apply known preamble regex patterns first
    2. Smart detection: find the first line containing real Vietnamese document content
       (Vietnamese diacritics, legal article markers like Điều/Khoản/Chương, or digits)
       and discard everything before it if the preceding lines are English/explanation text.
    """
    # Step 1: pattern-based removal
    preamble_patterns = [
        r'^Based on (?:the )?(?:visual )?(?:content|image|text)[^\n]*\n+',
        r'^I(?:\'ll| will| can) (?:extract|transcribe|copy|provide)[^\n]*\n+',
        r'^Here(?:\'s| is) (?:the )?(?:extracted|transcribed|text)[^\n]*\n+',
        r'^Looking at (?:the )?(?:image|document)[^\n]*\n+',
        r'^The image (?:shows|contains|displays)[^\n]*\n+',
        r'^(?:Following|Applying) (?:the )?(?:rules|guidelines|instructions)[^\n]*\n+',
        r'^The user (?:wants|asked|requested)[^\n]*\n+',
        r'^I need to (?:follow|extract|apply)[^\n]*\n+',
        r'^(?:OCR|Extracting|Transcribing)[^\n]*\n+',
        # Bullet list of rules Gemma sometimes regurgitates
        r'^(?:- Pure OCR|– Pure OCR|• Pure OCR)[^\n]*\n+',
        # Vietnamese preamble patterns
        r'^Dựa (?:vào|theo) (?:ảnh|hình)[^\n]*\n+',
        r'^Nhìn vào (?:ảnh|hình)[^\n]*\n+',
        r'^Nội dung (?:ảnh|hình|văn bản)[^\n]*\n+',
        r'^Theo (?:ảnh|hình|yêu cầu)[^\n]*\n+',
    ]
    for pattern in preamble_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
    text = text.strip()

    # Step 2: smart skip — if the first N lines are all ASCII/English, skip them
    # Real Vietnamese legal text always contains Unicode diacritics (à,ộ,ẫ,ế...)
    # or legal markers (Điều, Khoản, Chương, số digit sequences)
    vietnamese_pattern = re.compile(
        r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ'
        r'ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ'
        r'ĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬEÉẺẼẸÊẾỀỂỄỆIÍỈĨỊOÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢUÚỦŨỤƯỨỪỬỮỰYÝỶỸỴ]',
        re.UNICODE
    )
    legal_marker = re.compile(r'^(?:Điều|Khoản|Điểm|Chương|Mục|Phần|Phụ lục|\d)', re.IGNORECASE)

    lines = text.split('\n')
    start_idx = 0
    # Scan up to first 8 lines for preamble
    for i, line in enumerate(lines[:8]):
        stripped = line.strip()
        if not stripped:
            continue
        if vietnamese_pattern.search(stripped) or legal_marker.match(stripped):
            start_idx = i
            break
        # This line is preamble (English/explanation) — skip it
        start_idx = i + 1

    return '\n'.join(lines[start_idx:]).strip()


def call_model(model: str, img_bytes: bytes, page_num: int) -> tuple[str, float]:
    """Send image to a specific model and return (text, elapsed_seconds)."""
    b64 = base64.b64encode(img_bytes).decode("utf-8")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + f"\n\n[IGNORE Caching ID: {time.time()}]"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "OCR:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            },
        ],
        "max_tokens": 8192,
        "temperature": 0.0,
    }
    if "rag" in model or "qwen" in model.lower():
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    client = httpx.Client(timeout=300)
    t0 = time.time()
    try:
        resp = client.post(
            f"{GATEWAY_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=payload,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"].get("content", "")
        # Strip thinking tokens
        content = re.sub(r'<think>[\s\S]*?</think>\s*', '', content)
        # Strip preamble for all models (highly effective for verbose outputs)
        content = _strip_preamble(content)
        elapsed = time.time() - t0
        return content.strip(), elapsed
    except Exception as e:
        elapsed = time.time() - t0
        return f"[ERROR: {e}]", elapsed
    finally:
        client.close()


def score_output(text: str, ground_truth: dict) -> dict:
    """Score OCR output against ground truth."""
    text_lower = text.lower()

    hits = []
    misses = []
    for phrase in ground_truth["must_contain"]:
        if phrase.lower() in text_lower:
            hits.append(phrase)
        else:
            misses.append(phrase)

    hallucinations = []
    for phrase in ground_truth["must_not_contain"]:
        if phrase.lower() in text_lower:
            hallucinations.append(phrase)

    total = len(ground_truth["must_contain"])
    accuracy = len(hits) / total * 100 if total else 0
    halluc_count = len(hallucinations)

    # Combined score: accuracy - hallucination penalty
    score = max(0, accuracy - halluc_count * 10)

    return {
        "accuracy": round(accuracy, 1),
        "hits": len(hits),
        "total": total,
        "misses": misses,
        "hallucinations": hallucinations,
        "halluc_count": halluc_count,
        "combined_score": round(score, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark OCR models")
    parser.add_argument("--pdf", default="/app/data/legal_test/Luat_50-2014-QH13_Luat Xay dung_18-6-2014.pdf",
                        help="Path to PDF file")
    parser.add_argument("--page", type=int, default=21,
                        help="Page number (0-indexed) to benchmark")
    parser.add_argument("--dpi", type=int, default=300,
                        help="Render DPI")
    parser.add_argument("--models", nargs="+", default=MODELS,
                        help="Models to benchmark")
    parser.add_argument("--output", default=None,
                        help="Save results to JSON file")
    args = parser.parse_args()

    print(f"═══ OCR Model Benchmark ═══")
    print(f"PDF: {args.pdf}")
    print(f"Page: {args.page} (0-indexed)")
    print(f"DPI: {args.dpi}")
    print(f"Models: {', '.join(args.models)}")
    print()

    # Render page
    print("Rendering page image...", end=" ", flush=True)
    img_bytes = render_page(args.pdf, args.page, args.dpi)
    print(f"OK ({len(img_bytes) / 1024:.0f} KB)")
    print()

    results = {}
    for model in args.models:
        print(f"─── {model} ───")
        text, elapsed = call_model(model, img_bytes, args.page)

        if text.startswith("[ERROR"):
            print(f"  ❌ {text}")
            results[model] = {"error": text, "elapsed": elapsed}
            continue

        scores = score_output(text, GROUND_TRUTH_P21)
        results[model] = {
            "elapsed": round(elapsed, 1),
            "chars": len(text),
            "lines": text.count('\n') + 1,
            **scores,
            "text_preview": text[:300],
        }

        print(f"  ⏱  Time: {elapsed:.1f}s")
        print(f"  📏 Output: {len(text)} chars, {text.count(chr(10))+1} lines")
        print(f"  ✅ Accuracy: {scores['hits']}/{scores['total']} ({scores['accuracy']}%)")
        if scores['misses']:
            print(f"  ❌ Missing: {scores['misses']}")
        if scores['hallucinations']:
            print(f"  🚫 Hallucinated: {scores['hallucinations']}")
        print(f"  🏆 Combined Score: {scores['combined_score']}/100")
        print(f"  📝 Preview: {text[:150]}...")
        print()

    # Summary table
    print("═══ SUMMARY ═══")
    print(f"{'Model':<25} {'Time':>6} {'Chars':>6} {'Accuracy':>9} {'Halluc':>7} {'Score':>7}")
    print("─" * 65)
    for model, r in results.items():
        if "error" in r:
            print(f"{model:<25} {'FAIL':>6}")
        else:
            print(f"{model:<25} {r['elapsed']:>5.1f}s {r['chars']:>6} "
                  f"{r['accuracy']:>8.1f}% {r['halluc_count']:>6} {r['combined_score']:>6.1f}")

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
