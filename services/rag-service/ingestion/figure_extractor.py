"""
figure_extractor.py — AI-powered figure description injection for RAG pipeline.

For digital PDFs that contain embedded figure images (Hình X.Y), this module:
1. Detects embedded images on each page using fitz (PyMuPDF)
2. Finds nearby "Hình X.Y" text labels to name each figure
3. Calls the vision LLM (Qwen via ai-gateway) to describe the figure
4. Injects a concise caption `[Hình X.Y: <description>]` into the page text,
   providing semantic context to RAG chunks that previously had empty figure refs.

Usage from pipeline.py:
    from ingestion.figure_extractor import describe_page_figures

    page_text = describe_page_figures(
        doc=fitz_doc,
        page_num=i,
        page_text=raw_text,
        pdf_path=file_path,
    )
"""

import re
import io
import os
import logging
import base64
import time
import httpx
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ─── Settings ───────────────────────────────────────────────────────────────

# Minimum image area (px²) to consider a real figure (filter out tiny images,
# icons, watermarks, etc.)
_MIN_IMAGE_AREA = 10_000       # 100×100 pixels or larger
# Lookahead distance (in pixels on the page) to find a Hình label after an image
_LABEL_LOOKAHEAD_PTS = 120     # ~4cm below or above the image bbox
# Maximum chars per figure description (keeps chunks concise)
_MAX_DESC_CHARS = 300

# Model for figure descriptions — prefer lightweight remote models for speed.
# gemini-3-flash: ~1.5s (remote)  vs  rag-core: ~7.8s (local 35B GPU)
# Fallback chain: try all remote vision models before using local GPU.
_FIGURE_MODEL = os.environ.get("FIGURE_DESC_MODEL", "ocr-primary")
_FIGURE_FALLBACK_CHAIN = [
    "ocr-fallback",  # Fast remote backup
    "ocr-tier3",            # backup
    "ocr-tier4",         # backup
    "rag-core",               # Local 35B GPU — last resort
]
# Max concurrent figure descriptions per page
_MAX_CONCURRENT_FIGURES = 3

# Pattern to find "Hình X", "Hình A.1", "Hình B1", etc.
_HINH_LABEL_RE = re.compile(
    r"Hình\s+(?:[A-Z]\.?)?\d+(?:[.\-]\d+)*\s*[-–—]?\s*(?:[^\n]{0,80})?",
    re.IGNORECASE
)

# Pattern to match an existing injected caption (to avoid double-injection)
_INJECTED_CAPTION_RE = re.compile(r"\[Hình\s+[\d.]+[^]]*\]")


# ─── Vision LLM call ────────────────────────────────────────────────────────

_http_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=120)
    return _http_client


def _describe_figure(img_bytes: bytes, hint_label: str = "", page_num: int = 0) -> str:
    """Call the vision LLM to describe a figure image.

    Uses gemini-3-flash (fast remote) by default, falls back to rag-core
    (local 35B) if the remote model fails.

    Args:
        img_bytes: PNG or JPEG bytes of the figure.
        hint_label: Optional "Hình X.Y — Title" string to give the model context.
        page_num: For logging.

    Returns:
        A short description string (≤ _MAX_DESC_CHARS chars), or "" on failure.
    """
    gateway_url = os.environ.get("VLLM_API_BASE", "http://ai-gateway:4000/v1")
    api_key = os.environ.get("LITELLM_MASTER_KEY", "")
    if not api_key:
        logger.warning("[FIGURE] LITELLM_MASTER_KEY not set — skipping figure description")
        return ""

    b64 = base64.b64encode(img_bytes).decode()
    hint = f"Nhãn hình: {hint_label}\n" if hint_label else ""
    prompt = (
        f"{hint}"
        "Đây là hình kỹ thuật từ tài liệu quy chuẩn Việt Nam. "
        "Hãy mô tả ngắn gọn nội dung kỹ thuật của hình trong 1-2 câu tiếng Việt. "
        "CHỈ mô tả nội dung kỹ thuật thực tế (kích thước, cấu tạo, sơ đồ, v.v.). "
        "KHÔNG giải thích thêm. Tối đa 50 từ."
    )

    # Try preferred model first, then fallback chain
    models_to_try = [_FIGURE_MODEL] + [
        m for m in _FIGURE_FALLBACK_CHAIN if m != _FIGURE_MODEL
    ]

    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                    ]
                }
            ],
            "max_tokens": 120,
            "temperature": 0.1,
        }
        # Only add extra_body for local vLLM models (Qwen thinking mode)
        if model in ("rag-core", "qwen3.5-35b"):
            payload["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

        for attempt in range(2):
            try:
                t0 = time.time()
                resp = _get_client().post(
                    f"{gateway_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.debug(f"[FIGURE] 429 rate limit ({model}) page {page_num+1}, retry in {wait}s")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                content = (resp.json()["choices"][0]["message"].get("content") or "").strip()
                elapsed = time.time() - t0
                logger.info(f"  LLM Vision [ocr_p{page_num+1}] → {model} OK ({elapsed:.1f}s, {len(content)} chars)")
                return content[:_MAX_DESC_CHARS]
            except Exception as e:
                if attempt < 1:
                    time.sleep(1)
                else:
                    logger.warning(f"[FIGURE] {model} failed on page {page_num+1}: {e}")
                    break  # Try next model

    return ""


# ─── Image extraction ────────────────────────────────────────────────────────

def _extract_page_images(doc, page_num: int) -> list[dict]:
    """Extract all embedded images from a fitz page with their bboxes.

    Returns:
        List of dicts: {xref, rect, area, img_bytes}
    """
    try:
        import fitz
    except ImportError:
        return []

    page = doc[page_num]
    result = []

    for img in page.get_images(full=True):
        xref = img[0]
        try:
            rects = page.get_image_rects(xref, transform=False)
            if not rects:
                continue
            rect = rects[0]
            area = rect.width * rect.height
            if area < _MIN_IMAGE_AREA:
                continue  # Skip tiny/decorative images

            # Extract image bytes as PNG
            pix = doc.extract_image(xref)
            img_bytes = pix.get("image", b"")
            if not img_bytes:
                continue

            result.append({
                "xref": xref,
                "rect": rect,
                "area": area,
                "img_bytes": img_bytes,
            })
        except Exception as e:
            logger.debug(f"[FIGURE] image xref={xref} extraction failed: {e}")
            continue

    return result


# ─── Label matching ──────────────────────────────────────────────────────────

def _find_nearest_hinh_label(page, rect) -> str:
    """Find the nearest "Hình X.Y" label to an image rect on the page.

    Searches in text blocks below, above, and beside the image rect.
    Returns the label string or "" if not found.
    """
    page_text = page.get_text("dict")  # get by blocks for positional matching
    blocks = page_text.get("blocks", [])
    image_y_center = (rect.y0 + rect.y1) / 2
    image_x_center = (rect.x0 + rect.x1) / 2

    best_label = ""
    best_dist = float("inf")

    for block in blocks:
        if block.get("type") != 0:  # type 0 = text block
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                m = _HINH_LABEL_RE.match(text)
                if not m:
                    continue
                # Compute distance from image center to span bbox center
                bbx = span.get("bbox", [0, 0, 0, 0])
                span_y = (bbx[1] + bbx[3]) / 2
                span_x = (bbx[0] + bbx[2]) / 2
                dist = ((span_x - image_x_center)**2 + (span_y - image_y_center)**2) ** 0.5
                if dist < best_dist and abs(span_y - image_y_center) < _LABEL_LOOKAHEAD_PTS * 3:
                    best_dist = dist
                    best_label = m.group(0).strip()

    return best_label


# ─── Main public function ────────────────────────────────────────────────────

def describe_page_figures(
    doc,                     # fitz.Document
    page_num: int,           # 0-indexed
    page_text: str,          # raw text already extracted for this page
    pdf_path: str = "",      # for logging
    max_figures_per_page: int = 3,  # cap to avoid too many API calls per page
) -> str:
    """Extract and describe embedded figures on a page, injecting captions.

    For each figure found on the page:
    1. Check if there's already an injected caption (skip if so)
    2. Find the nearest "Hình X.Y" label
    3. Call vision LLM for a description
    4. Append `\\n[Hình X.Y: <description>]` to page_text

    Args:
        doc: Open fitz.Document object.
        page_num: 0-indexed page number.
        page_text: Raw text for this page (will be returned with captions appended).
        pdf_path: Path for logging context.
        max_figures_per_page: Maximum figures to describe per page.

    Returns:
        page_text with figure captions appended (unchanged if no figures found).
    """
    # Skip if already has injected captions (idempotent)
    if _INJECTED_CAPTION_RE.search(page_text):
        return page_text

    images = _extract_page_images(doc, page_num)
    if not images:
        return page_text

    page = doc[page_num]
    captions = []

    # Sort images by area descending (describe biggest/most important first)
    images.sort(key=lambda x: x["area"], reverse=True)
    selected = images[:max_figures_per_page]

    # Pre-compute labels (fast, no I/O)
    labels = []
    for img_info in selected:
        labels.append(_find_nearest_hinh_label(page, img_info["rect"]))

    # Describe figures in PARALLEL using ThreadPoolExecutor
    # This sends multiple requests to gemini-3-flash concurrently
    def _do_describe(idx):
        return idx, _describe_figure(
            img_bytes=selected[idx]["img_bytes"],
            hint_label=labels[idx],
            page_num=page_num,
        )

    results = {}
    with ThreadPoolExecutor(max_workers=min(len(selected), _MAX_CONCURRENT_FIGURES)) as executor:
        futures = [executor.submit(_do_describe, i) for i in range(len(selected))]
        for future in as_completed(futures):
            try:
                idx, desc = future.result()
                if desc:
                    results[idx] = desc
            except Exception as e:
                logger.warning(f"[FIGURE] Parallel describe failed: {e}")

    # Build captions in order
    for idx in range(len(selected)):
        if idx in results:
            tag = labels[idx] if labels[idx] else f"Hình trang {page_num+1}"
            captions.append(f"[{tag}: {results[idx]}]")
            logger.info(f"  [FIGURE] Page {page_num+1}: described '{labels[idx] or 'unnamed'}' ({len(results[idx])} chars)")

    if captions:
        page_text = page_text + "\n\n" + "\n".join(captions)

    return page_text
