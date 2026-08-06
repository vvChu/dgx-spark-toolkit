"""LLM Vision extraction module — gemini-3.1-flash-lite primary, gemini-3-flash fallback, rag-core last resort.

Benchmark results (2026-03-30):
  gemini-3.1-flash-lite : 6.2s  @ 100/100 accuracy  ← PRIMARY (fastest + best)
  gemini-3-flash        : 8.3s  @ 100/100 accuracy  ← FALLBACK
  rag-core (Qwen 35B)   : 16.1s @ 100/100 accuracy  ← LAST RESORT (local GPU)
  gemma-3-27b           : REMOVED from vision chain  → TEXT-ONLY tasks only (verbose output, preamble issues)
"""
import base64
import json
import logging
import os
import re
import time

import httpx

from ingestion.cleaning_utils import clean_llm_text
from core.circuit_breaker import get_circuit_breaker

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────────
# Benchmark results (2026-03-30): flash-lite=6.2s@100
PRIMARY_MODEL = os.getenv("PRIMARY_VISION_MODEL", "ocr-primary")
FALLBACK_MODEL = os.getenv("FALLBACK_VISION_MODEL", "ocr-fallback")
GATEWAY_URL = os.getenv("VLLM_API_BASE", "http://ai-gateway:4000/v1")
API_KEY = os.getenv("LITELLM_MASTER_KEY", "")

# OCR fallback chain: flash-lite → flash → rag-core (gemma-3-27b REMOVED: verbose output, preamble issues)
# GEMMA_OCR_MODEL intentionally disabled for vision tasks

# Per-task model routing — lightweight tasks offloaded to fast remote models
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "text-gemma")
METADATA_MODEL = os.getenv("METADATA_MODEL", "text-gemma")
METADATA_FALLBACK = os.getenv("METADATA_FALLBACK", "rag-core")         # Text-only fallback (local GPU, no quota)

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
                # Granular timeout: connect fast, read generous for OCR, avoid 5-min hangs
                _http_client = httpx.Client(
                    timeout=httpx.Timeout(
                        connect=15.0,  # TCP connect: fail fast but allow queue buffer
                        read=180.0,    # OCR read: high DPI needs a lot of time
                        write=15.0,    # Upload image payload
                        pool=15.0,     # Connection pool wait
                    )
                )
    return _http_client


def _call_model(messages: list, model: str, max_tokens: int = 4096,
                temperature: float = 0.0, disable_thinking: bool = True) -> str:
    """Send a request to a specific model via AIGatewayClient."""
    from core.ai_gateway_client import AIGatewayClient
    client = AIGatewayClient()
    extra = {}
    if disable_thinking and ("rag" in model or "qwen" in model.lower()):
        extra = {"chat_template_kwargs": {"enable_thinking": False}}
    try:
        return client.complete_sync(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra,
        )
    except Exception as e:
        logger.warning(f"AIGatewayClient call to {model} failed: {e}")
        return ""

    # Kích hoạt Adaptive Micro-Sleep 1.5s để làm giãn nhịp gọi API,
    # phân bổ mượt load vào 15 RPM của Gemini Flash Lite (Tránh Burst Spike)
    time.sleep(1.5)

    queue_retries = 0
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.post(
                f"{GATEWAY_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )

            if resp.status_code == 429:
                if queue_retries < 5:
                    queue_retries += 1
                    logger.warning(f"[HANG_DOI] 429 RateLimit trên {model}. Active Queue Pause 60s để săn dư lượng Quota... (lần {queue_retries}/5)")
                    time.sleep(60)
                    # Gửi lại API request này mà không tính vào số attempt thất bại thông thường
                    resp = client.post(
                        f"{GATEWAY_URL}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=payload,
                    )
                    if resp.status_code == 429:
                        continue # Vòng lặp For sẽ tự kích hoạt retry fallback nếu Queue Pause 5 phút thất bại
                else:         
                    wait = _INITIAL_BACKOFF * (2 ** attempt)
                    logger.warning(f"Rate limited (429) trên {model} (Queue cạn). Rơi tự do sang Fallback trong {wait}s ({attempt+1}/{_MAX_RETRIES})")
                    time.sleep(wait)
                    continue

            resp.raise_for_status()
            data = resp.json()

            if not isinstance(data, dict) or "choices" not in data:
                logger.warning(f"Invalid response from {model}: {data}")
                cb.record_failure(Exception("Invalid response"))
                return ""

            content = data["choices"][0].get("message", {}).get("content") or ""
            # Strip thinking tokens from models that leak them (Gemini, Qwen)
            content = re.sub(r'<think>[\s\S]*?</think>\s*', '', content)
            tp_match = re.match(
                r'(?:Thinking Process|Internal Monologue|Reasoning):?\s*\n[\s\S]*?\n\n([\s\S]+)',
                content, re.IGNORECASE
            )
            if tp_match:
                content = tp_match.group(1)
            cb.record_success()
            return content.strip()

        except Exception as e:
            cb.record_failure(e)
            if attempt == _MAX_RETRIES - 1:
                logger.error(f"Model {model} failed after {_MAX_RETRIES} attempts: {e}")
                return ""
            wait = _INITIAL_BACKOFF * (2 ** attempt)
            logger.warning(f"Model {model} attempt {attempt+1} failed: {e}. Retry in {wait}s")
            time.sleep(wait)

    return ""


def _strip_preamble(text: str) -> str:
    """Remove English/Vietnamese preamble that LLMs output before OCR content.

    Uses two-pass approach:
    1. Regex patterns for known preamble phrases
    2. Smart line-skip: skip leading lines that have no Vietnamese diacritics or legal markers
    """
    preamble_patterns = [
        r'^Based on (?:the )?(?:visual )?(?:content|image|text)[^\n]*\n+',
        r'^I(?:\'ll| will| can) (?:extract|transcribe|copy|provide)[^\n]*\n+',
        r'^Here(?:\'s| is) (?:the )?(?:extracted|transcribed|text)[^\n]*\n+',
        r'^Looking at (?:the )?(?:image|document)[^\n]*\n+',
        r'^The image (?:shows|contains|displays|analysis)[^\n]*\n+',
        r'^(?:Following|Applying) (?:the )?(?:rules|guidelines|instructions)[^\n]*\n+',
        r'^The user (?:wants|asked|requested)[^\n]*\n+',
        r'^I need to (?:follow|extract|apply)[^\n]*\n+',
        r'^(?:OCR|Extracting|Transcribing)[^\n]*\n+',
        r'^\*\*Image Analysis:\*\*[^\n]*\n+',
        r'^\*\*[A-Z][^\n]*\*\*[^\n]*\n+',  # **Heading:** preamble lines
        r'^- (?:Top|Bottom|Left|Right|Center)[^\n]*\n+',  # Layout description bullets
        r'^Dựa (?:vào|theo) (?:ảnh|hình)[^\n]*\n+',
        r'^Nhìn vào (?:ảnh|hình)[^\n]*\n+',
        r'^Nội dung (?:ảnh|hình|văn bản)[^\n]*\n+',
        r'^Theo (?:ảnh|hình|yêu cầu)[^\n]*\n+',
    ]
    for pattern in preamble_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
    text = text.strip()

    # Smart skip: if first lines contain no Vietnamese content, discard them
    viet_chars = re.compile(
        r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ'
        r'ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ]',
        re.UNICODE
    )
    legal_start = re.compile(
        r'^(?:Điều|Khoản|Điểm|Chương|Mục|Phần|Phụ lục|\d)', re.IGNORECASE
    )
    lines = text.split('\n')
    start_idx = 0
    for i, line in enumerate(lines[:10]):
        stripped = line.strip()
        if not stripped:
            continue
        if viet_chars.search(stripped) or legal_start.match(stripped):
            start_idx = i
            break
        start_idx = i + 1

    return '\n'.join(lines[start_idx:]).strip()


def _call_llm(messages: list, max_tokens: int = 4096,
              temperature: float = 0.0, task: str = "extract",
              primary_model: str | None = None,
              fallback_model: str | None = None,
              is_vision: bool = False) -> str:
    """Call LLM via gateway; if primary fails, automatically tries fallback_model.
    
    Args:
        messages: Chat messages
        max_tokens: Maximum response tokens
        temperature: Sampling temperature
        task: Task label for logging
        primary_model: Override primary model (if provided).
        fallback_model: Fallback model to try if primary returns empty.
    """
    p_model = primary_model or PRIMARY_MODEL

    t0 = time.time()
    result = _call_model(messages, p_model, max_tokens, temperature,
                         disable_thinking=("rag" in p_model or "qwen" in p_model.lower()))

    if result:
        # Post-process LLM output to strip verbose preamble
        result = _strip_preamble(result)
        if not result:
            logger.warning(f"  LLM Vision [{task}] → {p_model}: preamble stripped left empty")
        else:
            logger.info(f"  LLM Vision [{task}] → {p_model} OK ({time.time()-t0:.1f}s, {len(result)} chars)")
            return result

    # Primary failed or empty — try explicit fallback_model if provided
    if fallback_model and fallback_model != p_model:
        logger.warning(f"  LLM Vision [{task}] → {p_model} failed. Trying fallback: {fallback_model}")
        t1 = time.time()
        f_result = _call_model(messages, fallback_model, max_tokens, temperature,
                               disable_thinking=("rag" in fallback_model or "qwen" in fallback_model.lower()))
        if f_result:
            f_result = _strip_preamble(f_result)
            if f_result:
                logger.info(f"  LLM Vision [{task}] → {fallback_model} OK (fallback, {time.time()-t1:.1f}s, {len(f_result)} chars)")
                return f_result

    logger.error(f"  LLM Vision [{task}] → all models failed (primary={p_model}, fallback={fallback_model})")
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM EXTRACT PAGE — OCR via multimodal LLM
# ═══════════════════════════════════════════════════════════════════════════════

_EXTRACT_SYSTEM = """Bạn là chuyên gia bóc tách tài liệu (OCR) Hệ thống Văn bản Pháp luật Việt Nam (QCVN, TCVN, Nghị định, Thông tư...).
CHỈ xuất văn bản thuần túy và cấu trúc từ ảnh bằng Markdown. KHÔNG BAO GIỜ tự sáng tạo nội dung.

QUY TẮC BẮT BUỘC ĐỐI VỚI VĂN BẢN QUY PHẠM PHÁP LUẬT:
1. BẢO TOÀN CẤU TRÚC PHÁP LÝ: Giữ nguyên vẹn hệ thống phân cấp (Phần, Chương, Mục, Tiểu mục, Điều, Khoản, Điểm...). Mỗi đề mục này PHẢI nằm trên dòng riêng biệt.
2. BẢNG BIỂU KỸ THUẬT (QCVN/TCVN): Nếu phát hiện Bảng (Table), BẮT BUỘC phải vẽ lại dưới dạng thẻ Markdown Table (ví dụ: `| Cột 1 | Cột 2 |`). Tôn trọng các điểm neo và tọa độ nếu có. Không được làm vỡ cột quy chuẩn tải trọng/hoá chất/kích thước.
3. KÝ HIỆU VÀ ĐƠN VỊ: Giữ nguyên tuyệt đối các đơn vị đo lường (m2, kg/m3, kPa), công thức hóa học, và ký hiệu toán học đặc thù của QCVN/TCVN.
4. KHÔNG SỬ DỤNG (#) Heading markdown để tránh phá luồng Chunking hệ thống. Chỉ dùng Markdown cho định dạng Bảng (|...|) và Bôi đậm (**...**) nếu cần nhấn mạnh nội dung.

BỎ QUA HOÀN TOÀN (KHÔNG trích xuất):
- Logo, phôi nền watermark, header điện tử (CỔNG THÔNG TIN ĐIỆN TỬ, chinhphu.vn, thời gian ký).
- Chữ viết tay bổ sung, bút đỏ, con dấu đỏ, chữ ký điện tử.
- Các khối phân phối văn bản cuối trang ("Nơi nhận:", "Lưu: VT, ...").
- Tên/chức danh mang tính thủ tục hành chính ("KT. BỘ TRƯỞNG", "PHÓ THỦ TƯỚNG", "TM.").
- Số trang đứng đơn lẻ."""



def llm_extract_page(img_bytes: bytes, page_num: int = 0,
                     digital_text: str = "", model_override: str | None = None) -> dict:
    """Extract text from a scanned PDF page image using LLM Vision.

    Args:
        img_bytes: JPEG bytes of the page image
        page_num: 1-indexed page number
        digital_text: Any digital text already extracted by fitz (for reference)

    Returns:
        dict with keys: text, is_table, layout, source
    """
    b64 = base64.b64encode(img_bytes).decode("utf-8")

    user_prompt = "Hãy bắt đầu bóc tách (OCR) cấu trúc Văn bản này:"

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

    raw = _call_llm(messages, max_tokens=8192, temperature=0.0, task=f"ocr_p{page_num}", is_vision=True, primary_model=model_override)
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

    # Primary model (Gemma 27B) returned markdown analysis instead of JSON.
    # Fallback chain: smaller Gemma → local GPU Qwen (all text models, NOT vision models)
    _meta_fallbacks = [
        os.getenv("TEXT_METADATA_FALLBACK_1", "text-gemma-12b"),
        os.getenv("TEXT_METADATA_FALLBACK_2", "text-gemma-4b"),
        METADATA_FALLBACK,  # rag-core (Qwen 35B local)
    ]
    # Reinforce JSON-only on retries (Gemma sometimes needs explicit reminder)
    retry_messages = [
        {"role": "system", "content": _META_SYSTEM},
        {"role": "user", "content": f"Chỉ trả về JSON. Không giải thích.\n\nMetadata:\n\n{text_head[:5000]}"},
    ]
    for retry_model in _meta_fallbacks:
        if retry_model and retry_model != METADATA_MODEL:
            logger.warning(f"Metadata JSON parse failed, retrying with {retry_model}...")
            raw_retry = _call_model(retry_messages, retry_model, max_tokens=300, temperature=0.0,
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
