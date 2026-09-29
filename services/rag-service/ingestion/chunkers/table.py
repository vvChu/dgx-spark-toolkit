import hashlib
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

_redis_table_cache = None


def _get_redis_cache():
    """Get Redis client for table summary cache.

    Invariant: Strictly uses Redis DB 3 (SemanticCache L2) to prevent
    polluting Redis DB 1 (reserved exclusively for ingest:queue).
    """
    global _redis_table_cache
    if _redis_table_cache is not None:
        return _redis_table_cache
    try:
        import redis
        from retrieval.tier0_cache import format_redis_db3_url

        raw_url = os.environ.get("REDIS_TABLE_CACHE_URL") or os.environ.get(
            "REDIS_CACHE_URL", "redis://litellm-redis:6379/3"
        )
        url = format_redis_db3_url(raw_url)
        _redis_table_cache = redis.from_url(url, decode_responses=True, socket_timeout=2.0)
        return _redis_table_cache
    except Exception:
        return None


def _is_broken_ocr_table(text: str) -> bool:
    """Detect if a table text has broken OCR structure (misaligned columns, missing pipes, noise)."""
    if not text:
        return False
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < 2:
        return False
    pipe_count = text.count("|")
    if pipe_count > 2:
        pipe_counts = [line.count("|") for line in lines]
        if max(pipe_counts) != min(pipe_counts) and min(pipe_counts) == 0:
            return True
    if re.search(r'\.{4,}|\s{5,}\d+', text):
        return True
    return False


def _correct_broken_table_with_vision(table_text: str, image_bytes: Optional[bytes] = None, doc_id: str = "") -> str:
    """Auto-correct broken OCR tables using Multimodal Vision (Gemini 3.5 Flash Lite)."""
    try:
        from core.ai_gateway_client import AIGatewayClient
        client = AIGatewayClient()

        prompt = (
            "Dưới đây là nội dung một bảng biểu trong văn bản pháp luật bị lỗi OCR (mất cột, vỡ cấu trúc dòng).\n"
            "Hãy dựng lại bảng này dưới dạng Markdown Table chuẩn hóa, giữ nguyên toàn bộ số liệu và văn bản chính xác.\n"
            "Chỉ trả về Markdown Table, không kèm theo văn bản dẫn dắt khác.\n\n"
            f"Dữ liệu bảng thô:\n{table_text[:3500]}"
        )

        if image_bytes:
            table_vision_model = os.getenv("TABLE_VISION_MODEL", "ocr-primary")
            reconstructed = client.complete_vision_sync(
                image_bytes,
                prompt=prompt,
                model=table_vision_model,
            )
        else:
            table_text_model = os.getenv("TABLE_CORRECTION_MODEL", "text-auto")
            reconstructed = client.complete_sync(
                [{"role": "user", "content": prompt}],
                model=table_text_model,
                model_chain=[table_text_model, "text-gemma-12b", "rag-core"],
            )

        if reconstructed and "|" in reconstructed and len(reconstructed) > 20:
            return reconstructed.strip()
    except Exception as e:
        logger.debug(f"[TABLE-VISION-CORRECT] Vision table correction skipped: {e}")

    return table_text


def _generate_table_summary(table_text: str, doc_id: str) -> str:
    """Generate a concise summary of a large table via LLM with Redis caching.

    Uses the AI Gateway (Gemini Flash) for fast, cost-free summarization.
    Falls back gracefully if the gateway is unavailable.
    """
    content_hash = hashlib.md5(table_text[:3000].encode("utf-8")).hexdigest()
    cache_key = f"cache:table_summary:{content_hash}"
    r = _get_redis_cache()
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                logger.debug(f"[TABLE-SUM] Redis cache hit for table hash {content_hash[:8]}")
                return cached
        except Exception:
            pass

    model = os.getenv("TABLE_SUMMARY_MODEL", "text-gemma")
    prompt = (
        "Tóm tắt bảng dữ liệu sau bằng tiếng Việt. "
        "Nêu rõ: (1) Mục đích của bảng, (2) Tên các cột chính, "
        "(3) Số dòng/mục dữ liệu, (4) Các giá trị nổi bật. "
        "Trả lời ngắn gọn trong 2-3 câu.\n\n"
        f"Bảng:\n{table_text[:3000]}"
    )

    from core.ai_gateway_client import get_ai_gateway_client
    client = get_ai_gateway_client()
    try:
        content = client.complete_sync(
            [{"role": "user", "content": prompt}],
            model=model,
            max_tokens=200,
            temperature=0.1,
        )
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        if r and content:
            try:
                r.setex(cache_key, 604800, content)
            except Exception:
                pass
        return content
    except Exception as e:
        logger.debug(f"[TABLE-SUM] LLM call failed: {e}")
        return ""
