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
from typing import Any, Dict, List, Optional

from ingestion.cleaning_utils import clean_llm_text
from core.ai_gateway_client import get_ai_gateway_client

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────────
# Benchmark results (2026-03-30): flash-lite=6.2s@100
PRIMARY_MODEL = os.getenv("PRIMARY_VISION_MODEL", "ocr-primary")
FALLBACK_MODEL = os.getenv("FALLBACK_VISION_MODEL", "ocr-fallback")
GATEWAY_URL = os.getenv("VLLM_API_BASE", "http://ai-gateway:4000/v1")
API_KEY = os.getenv("LITELLM_MASTER_KEY", "")

# Per-task model routing — lightweight tasks offloaded to fast remote models
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "text-gemma")
METADATA_MODEL = os.getenv("METADATA_MODEL", "text-gemma")
METADATA_FALLBACK = os.getenv("METADATA_FALLBACK", "rag-core")  # Text-only fallback (local GPU, no quota)


def _call_model(messages: List[Dict[str, Any]], model: str, max_tokens: int = 4096,
                temperature: float = 0.0, disable_thinking: bool = True) -> str:
    """Send a request to a specific model via AIGatewayClient."""
    client = get_ai_gateway_client()
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


def _call_llm(messages: List[Dict[str, Any]], max_tokens: int = 4096,
              temperature: float = 0.0, task: str = "extract",
              primary_model: Optional[str] = None,
              fallback_model: Optional[str] = None,
              is_vision: bool = False) -> str:
    """Call LLM via AIGatewayClient with fallback cascade.

    Args:
        messages: Chat messages
        max_tokens: Maximum response tokens
        temperature: Sampling temperature
        task: Task label for logging
        primary_model: Override primary model (if provided).
        fallback_model: Fallback model to try if primary returns empty.
        is_vision: Flag indicating if call contains image payload.
    """
    client = get_ai_gateway_client()
    p_model = primary_model or PRIMARY_MODEL
    chain = [p_model]
    if fallback_model and fallback_model != p_model:
        chain.append(fallback_model)
    if "rag-core" not in chain:
        chain.append("rag-core")

    t0 = time.time()
    try:
        raw = client.complete_sync(
            messages,
            model=p_model,
            model_chain=chain,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if raw:
            raw = _strip_preamble(raw)
            logger.info(f"  LLM [{task}] → {p_model} OK ({time.time()-t0:.1f}s, {len(raw)} chars)")
            return raw
    except Exception as e:
        logger.warning(f"  LLM [{task}] call failed across chain {chain}: {e}")

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
                     digital_text: str = "", model_override: Optional[str] = None) -> dict:
    """Extract text from a scanned PDF page image using LLM Vision.

    Args:
        img_bytes: JPEG bytes of the page image
        page_num: 1-indexed page number
        digital_text: Any digital text already extracted by fitz (for reference)
        model_override: Optional model override.

    Returns:
        dict with keys: text, is_table, layout, source
    """
    client = get_ai_gateway_client()
    target_model = model_override or PRIMARY_MODEL
    user_prompt = "Hãy bắt đầu bóc tách (OCR) cấu trúc Văn bản này:"

    t0 = time.time()
    try:
        raw = client.complete_vision_sync(
            img_bytes,
            prompt=user_prompt,
            system_prompt=_EXTRACT_SYSTEM,
            model=target_model,
            model_chain=[target_model, FALLBACK_MODEL, "rag-core"],
            max_tokens=8192,
            temperature=0.0,
        )
    except Exception as e:
        logger.error(f"  LLM Vision [ocr_p{page_num}] → all models failed: {e}")
        return {"text": "", "is_table": False, "layout": [], "source": "llm_failed"}

    if not raw:
        return {"text": "", "is_table": False, "layout": [], "source": "llm_failed"}

    raw = _strip_preamble(raw)
    if not raw:
        logger.warning(f"  LLM Vision [ocr_p{page_num}] → {target_model}: preamble stripped left empty")
        return {"text": "", "is_table": False, "layout": [], "source": "llm_failed"}

    logger.info(f"  LLM Vision [ocr_p{page_num}] → {target_model} OK ({time.time()-t0:.1f}s, {len(raw)} chars)")
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


def _extract_json_from_llm(raw: str) -> Optional[dict]:
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
