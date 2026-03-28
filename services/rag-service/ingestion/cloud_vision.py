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
PRIMARY_MODEL = os.getenv("PRIMARY_VISION_MODEL", "gemini-3-flash")            # Fast free tier (3-5s) — 1500 RPD
FALLBACK_MODEL = os.getenv("FALLBACK_VISION_MODEL", "gemini-3.1-flash-lite")   # 2nd free tier — 6000 RPD → then rag-core via LiteLLM
GATEWAY_URL = os.getenv("VLLM_API_BASE", "http://ai-gateway:4000/v1")
API_KEY = os.getenv("LITELLM_MASTER_KEY", "")

# Per-task model routing — lightweight tasks offloaded to fast remote models
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "gemini-3.1-flash-lite")    # Text-only, 400 tokens — 2.5x faster
METADATA_MODEL = os.getenv("METADATA_MODEL", "gemini-3.1-flash-lite")  # JSON extraction, 300 tokens
METADATA_FALLBACK = os.getenv("METADATA_FALLBACK", "gemma-3-27b")      # High-quota fallback for JSON retry

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

            content = data["choices"][0].get("message", {}).get("content") or ""
            # Strip thinking tokens from models that leak them (Gemini, Qwen)
            # Pattern 1: <think>...</think> XML tags
            content = re.sub(r'<think>[\s\S]*?</think>\s*', '', content)
            # Pattern 2: "Thinking Process:" text preamble before actual content
            # Only strip if there's actual content after the thinking block
            tp_match = re.match(
                r'(?:Thinking Process|Internal Monologue|Reasoning):?\s*\n[\s\S]*?\n\n([\s\S]+)',
                content, re.IGNORECASE
            )
            if tp_match:
                content = tp_match.group(1)
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
              temperature: float = 0.0, task: str = "extract",
              primary_model: str | None = None,
              fallback_model: str | None = None) -> str:
    """Call LLM with full failover chain: primary → fallback → rag-core.

    Args:
        messages: Chat messages (system + user with optional image_url)
        max_tokens: Maximum response tokens
        temperature: Sampling temperature
        task: Task label for logging
        primary_model: Override primary model (default: gemini-3-flash)
        fallback_model: Override fallback model (default: gemini-3.1-flash-lite)

    Returns:
        Response text (empty string on total failure)
    """
    p_model = primary_model or PRIMARY_MODEL
    f_model = fallback_model or FALLBACK_MODEL

    # Build fallback chain: primary → fallback → rag-core (local GPU last resort)
    # Deduplicate: skip any model that's the same as a previous one
    chain = [p_model]
    if f_model != p_model:
        chain.append(f_model)
    # Always add rag-core as the last resort (local GPU, no quota limits)
    if "rag-core" not in chain:
        chain.append("rag-core")

    for i, model in enumerate(chain):
        t0 = time.time()
        result = _call_model(messages, model, max_tokens, temperature,
                             disable_thinking=("rag" in model or "qwen" in model.lower()))
        if result:
            logger.info(f"  LLM Vision [{task}] → {model} OK ({time.time()-t0:.1f}s, {len(result)} chars)")
            return result

        if i < len(chain) - 1:
            logger.warning(f"  LLM Vision [{task}] → {model} failed, falling back to {chain[i+1]}")
        else:
            logger.error(f"  LLM Vision [{task}] → ALL models failed: {chain}")

    return ""


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
7. Mỗi đề mục/mục số (1.1, 1.2, 2.3.4...) PHẢI nằm trên dòng riêng biệt
8. KHÔNG dùng markdown heading (#), CHỈ dùng markdown cho bảng biểu (|)
9. KHÔNG viết tiếng Anh
10. CHỈ VĂN BẢN THUẦN TÚY

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

    raw = _call_llm(messages, max_tokens=8192, temperature=0.0, task=f"ocr_p{page_num}")
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

    raw = _call_llm(messages, max_tokens=1500, temperature=0.1, task="summary",
                    primary_model=SUMMARY_MODEL, fallback_model=PRIMARY_MODEL)
    return clean_llm_text(raw, is_summary=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM METADATA — structured metadata extraction
# ═══════════════════════════════════════════════════════════════════════════════

_META_SYSTEM = """Trích xuất metadata từ văn bản pháp luật Việt Nam.
Trả về JSON THUẦN TÚY (không markdown, không giải thích) với các trường:

{
  "doc_number": "Số hiệu văn bản đầy đủ (ví dụ: 16/2025/TT-BXD, 87/2023/NĐ-CP, 1417/QĐ-TTg). Trích xuất từ tiêu đề, tên file, hoặc dòng 'Số:' trong văn bản",
  "date": "Ngày ban hành (DD/MM/YYYY)",
  "authority": "Cơ quan ban hành",
  "doc_type": "Loại văn bản (Thông tư, Quyết định, Nghị định, Công văn...)",
  "title": "Tiêu đề/trích yếu"
}

Nếu không tìm thấy → để trống "". KHÔNG đoán. CHỈ JSON."""


def _extract_json_from_llm(raw: str) -> dict | None:
    """Robustly extract a JSON object from LLM output.

    Handles common failure modes:
    1. "Thinking Process:" preamble before JSON
    2. Markdown code fences (```json ... ```)
    3. Nested JSON objects (brace-balanced matching)
    """
    if not raw:
        return None

    # Step 1: Strip markdown code fences first
    fence_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
    if fence_match:
        raw = fence_match.group(1)

    # Step 2: Find the first '{' — everything before it is preamble
    brace_start = raw.find('{')
    if brace_start == -1:
        return None

    # Step 3: Brace-balanced extraction from the first '{'
    depth = 0
    for i in range(brace_start, len(raw)):
        if raw[i] == '{':
            depth += 1
        elif raw[i] == '}':
            depth -= 1
            if depth == 0:
                candidate = raw[brace_start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # If this balanced block fails, try the next '{'
                    next_brace = raw.find('{', brace_start + 1)
                    if next_brace != -1 and next_brace < i:
                        brace_start = next_brace
                        depth = 0
                        # restart scan from new position
                        return _extract_json_from_llm(raw[next_brace:])
                    return None

    return None


def llm_extract_metadata(text_head: str) -> dict:
    """Extract structured metadata from document text using LLM."""
    if not text_head.strip():
        return {}

    messages = [
        {"role": "system", "content": _META_SYSTEM},
        {"role": "user", "content": f"Metadata:\n\n{text_head[:5000]}"},
    ]

    raw = _call_llm(messages, max_tokens=300, temperature=0.0, task="metadata",
                    primary_model=METADATA_MODEL, fallback_model=PRIMARY_MODEL)
    if not raw:
        return {}

    # Try direct parse first (fast path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Robust extraction: handles thinking preambles, code fences, nested JSON
    result = _extract_json_from_llm(raw)
    if result is not None:
        return result

    # Primary model failed JSON parse — cascade through fallback chain
    # Chain: gemini-3.1-flash-lite → gemma-3-27b → rag-core (Qwen 35B)
    for retry_model in [METADATA_FALLBACK, PRIMARY_MODEL]:
        if retry_model and retry_model != METADATA_MODEL:
            logger.warning(f"Metadata JSON parse failed, retrying with {retry_model}...")
            raw_retry = _call_model(messages, retry_model, max_tokens=300, temperature=0.0,
                                    disable_thinking=True)
            if raw_retry:
                try:
                    return json.loads(raw_retry)
                except json.JSONDecodeError:
                    result_retry = _extract_json_from_llm(raw_retry)
                    if result_retry is not None:
                        return result_retry

    logger.warning(f"Could not parse metadata JSON after all retries: {raw[:200]}")
    return {}


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKWARD COMPATIBILITY — old names still work
# ═══════════════════════════════════════════════════════════════════════════════

# These aliases ensure existing imports don't break
cloud_extract_page = llm_extract_page
cloud_generate_summary = llm_generate_summary
cloud_extract_metadata = llm_extract_metadata
