"""LLM Vision extraction module — Qwen 35B primary, Gemini 2.5 Flash fallback.

Uses multimodal LLM to extract text, layout, and tables from PDF page images.
Qwen 35B (local, 3.2s) is the primary engine; Gemini 2.5 Flash (cloud, 15.6s)
is the automatic fallback when Qwen is unavailable or fails.
"""
import base64
import json
import logging
import os
import re
import time

import httpx

from ingestion.cleaning_utils import clean_llm_text

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────────
PRIMARY_MODEL = os.getenv("PRIMARY_VISION_MODEL", "rag-core")          # Qwen 35B local
FALLBACK_MODEL = os.getenv("FALLBACK_VISION_MODEL", "gemini-2.5-flash") # Gemini cloud
GATEWAY_URL = os.getenv("VLLM_API_BASE", "http://ai-gateway:4000/v1")
API_KEY = os.getenv("LITELLM_MASTER_KEY", "")

_MAX_RETRIES = 3
_INITIAL_BACKOFF = 2  # seconds

# ── Shared HTTP Client ──────────────────────────────────────────────────────────
import threading as _threading

_http_client: httpx.Client | None = None
_http_lock = _threading.Lock()


def _get_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        with _http_lock:
            if _http_client is None:
                _http_client = httpx.Client(timeout=300)
    return _http_client


def _call_model(messages: list, model: str, max_tokens: int = 4096,
                temperature: float = 0.0, disable_thinking: bool = True) -> str:
    """Send a request to a specific model via AI Gateway with retry logic."""
    api_key = API_KEY or os.getenv("LITELLM_MASTER_KEY", "")

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    # Disable thinking mode for Qwen models to get clean output
    if disable_thinking and "rag" in model or "qwen" in model.lower():
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    client = _get_client()
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.post(
                f"{GATEWAY_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )

            if resp.status_code == 429:
                wait = _INITIAL_BACKOFF * (2 ** attempt)
                logger.warning(f"Rate limited (429) on {model}. Retry in {wait}s ({attempt+1}/{_MAX_RETRIES})")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()

            if not isinstance(data, dict) or "choices" not in data:
                logger.warning(f"Invalid response from {model}: {data}")
                return ""

            content = data["choices"][0].get("message", {}).get("content", "")
            return content.strip()

        except Exception as e:
            if attempt == _MAX_RETRIES - 1:
                logger.error(f"Model {model} failed after {_MAX_RETRIES} attempts: {e}")
                return ""
            wait = _INITIAL_BACKOFF * (2 ** attempt)
            logger.warning(f"Model {model} attempt {attempt+1} failed: {e}. Retry in {wait}s")
            time.sleep(wait)

    return ""


def _call_llm(messages: list, max_tokens: int = 4096,
              temperature: float = 0.0, task: str = "extract") -> str:
    """Call LLM with automatic failover: Qwen primary → Gemini fallback.

    Args:
        messages: Chat messages (system + user with optional image_url)
        max_tokens: Maximum response tokens
        temperature: Sampling temperature
        task: Task label for logging

    Returns:
        Response text (empty string on total failure)
    """
    # ── Try primary (Qwen 35B local) ──
    t0 = time.time()
    result = _call_model(messages, PRIMARY_MODEL, max_tokens, temperature, disable_thinking=True)
    if result:
        logger.info(f"  LLM Vision [{task}] → {PRIMARY_MODEL} OK ({time.time()-t0:.1f}s, {len(result)} chars)")
        return result

    # ── Fallback to Gemini ──
    logger.warning(f"  LLM Vision [{task}] → {PRIMARY_MODEL} failed, falling back to {FALLBACK_MODEL}")
    t0 = time.time()
    result = _call_model(messages, FALLBACK_MODEL, max_tokens, temperature, disable_thinking=False)
    if result:
        logger.info(f"  LLM Vision [{task}] → {FALLBACK_MODEL} OK ({time.time()-t0:.1f}s, {len(result)} chars)")
    else:
        logger.error(f"  LLM Vision [{task}] → Both {PRIMARY_MODEL} and {FALLBACK_MODEL} failed!")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM EXTRACT PAGE — OCR via multimodal LLM
# ═══════════════════════════════════════════════════════════════════════════════

_EXTRACT_SYSTEM = """Bạn là máy OCR. CHỈ xuất văn bản thuần túy từ ảnh.

QUY TẮC BẮT BUỘC:
1. Trích xuất TOÀN BỘ nội dung pháp lý, giữ nguyên thứ tự từ trên xuống dưới
2. Giữ nguyên cấu trúc: Điều, Khoản, Điểm, Chương, Mục, Phần, Phụ lục
3. BẢNG BIỂU → Markdown table (| col1 | col2 |)
4. Giữ nguyên số hiệu, ngày tháng, tên cơ quan
5. TUYỆT ĐỐI KHÔNG thêm nhận xét, giải thích, đánh số, phân tích
6. KHÔNG mô tả font, style, bold, caps
7. KHÔNG dùng markdown ngoại trừ bảng biểu
8. KHÔNG viết tiếng Anh
9. CHỈ VĂN BẢN THUẦN TÚY

BỎ QUA HOÀN TOÀN (KHÔNG trích xuất):
- Logo, watermark, header điện tử (VGP, CỔNG THÔNG TIN ĐIỆN TỬ, chinhphu.vn, email, thời gian ký)
- Chữ viết tay, ghi chú tay (TTĐT(2), TT(2), bút đỏ...)
- Con dấu điện tử, con dấu đỏ, chữ ký số, chữ ký tay
- Khối "Nơi nhận:" và toàn bộ danh sách phân phối sau đó
- Tên/chức danh người ký (KT. THỦ TƯỚNG, PHÓ THỦ TƯỚNG, TM., tên riêng)
- Mã lưu trữ (Lưu: VT, KGVX...)
- Số trang đứng riêng"""


def llm_extract_page(img_bytes: bytes, page_num: int = 0,
                     digital_text: str = "") -> dict:
    """Extract text from a scanned PDF page image using LLM Vision.

    Args:
        img_bytes: JPEG bytes of the page image
        page_num: 1-indexed page number
        digital_text: Any digital text already extracted by fitz (for reference)

    Returns:
        dict with keys: text, is_table, layout, source
    """
    b64 = base64.b64encode(img_bytes).decode("utf-8")

    user_prompt = "OCR:"
    if digital_text and len(digital_text) > 50:
        user_prompt += f"\n\nTham khảo bản nháp (có thể sai):\n---\n{digital_text[:3000]}\n---"

    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        },
    ]

    raw = _call_llm(messages, max_tokens=4096, temperature=0.0, task=f"ocr_p{page_num}")
    if not raw:
        return {"text": "", "is_table": False, "layout": [], "source": "llm_failed"}

    text = clean_llm_text(raw)

    # Detect table presence
    has_table = bool(re.search(r'\|.*\|.*\n\|[-:\s|]+\|', text))

    return {
        "text": text,
        "is_table": has_table,
        "layout": [],
        "source": "llm_vision",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM SUMMARY — Vietnamese-only document summary
# ═══════════════════════════════════════════════════════════════════════════════

_SUMMARY_SYSTEM = """Bạn là chuyên gia tóm tắt văn bản pháp luật Việt Nam.
CHỈ viết bằng tiếng Việt. KHÔNG BAO GIỜ viết tiếng Anh.
Tạo bản tóm tắt ngắn gọn, rõ ràng, giữ nguyên ý chính.

QUY TẮC BẮT BUỘC:
- Tối đa 1500 ký tự
- KHÔNG giải thích quá trình suy nghĩ
- KHÔNG viết "Internal Monologue", "Drafting", "Strategy"
- KHÔNG đánh số bước phân tích (1. **, 2. **)
- KHÔNG dùng markdown (**, ##, *)
- Chỉ xuất nội dung tóm tắt thuần túy"""


def llm_generate_summary(full_text: str) -> str:
    """Generate a Vietnamese-only summary using LLM (Qwen → Gemini fallback)."""
    if not full_text.strip():
        return ""

    messages = [
        {"role": "system", "content": _SUMMARY_SYSTEM},
        {"role": "user", "content": f"Tóm tắt văn bản pháp luật sau:\n\n{full_text[:15000]}"},
    ]

    raw = _call_llm(messages, max_tokens=400, temperature=0.1, task="summary")
    return clean_llm_text(raw, is_summary=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM METADATA — structured metadata extraction
# ═══════════════════════════════════════════════════════════════════════════════

_META_SYSTEM = """Trích xuất metadata từ văn bản pháp luật Việt Nam.
Trả về JSON THUẦN TÚY (không markdown, không giải thích) với các trường:

{
  "doc_number": "Số hiệu văn bản (ví dụ: 10/2023/TT-BTP)",
  "date": "Ngày ban hành (DD/MM/YYYY)",
  "authority": "Cơ quan ban hành",
  "doc_type": "Loại văn bản (Thông tư, Quyết định, Nghị định, Công văn...)",
  "title": "Tiêu đề/trích yếu"
}

Nếu không tìm thấy → để trống "". KHÔNG đoán. CHỈ JSON."""


def llm_extract_metadata(text_head: str) -> dict:
    """Extract structured metadata from document text using LLM."""
    if not text_head.strip():
        return {}

    messages = [
        {"role": "system", "content": _META_SYSTEM},
        {"role": "user", "content": f"Metadata:\n\n{text_head[:5000]}"},
    ]

    raw = _call_llm(messages, max_tokens=300, temperature=0.0, task="metadata")
    if not raw:
        return {}

    # Parse JSON from response
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting JSON from markdown code block
        match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # Try finding raw JSON object
        match = re.search(r'\{[^{}]*\}', raw)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    logger.warning(f"Could not parse metadata JSON: {raw[:200]}")
    return {}


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKWARD COMPATIBILITY — old names still work
# ═══════════════════════════════════════════════════════════════════════════════

# These aliases ensure existing imports don't break
cloud_extract_page = llm_extract_page
cloud_generate_summary = llm_generate_summary
cloud_extract_metadata = llm_extract_metadata
