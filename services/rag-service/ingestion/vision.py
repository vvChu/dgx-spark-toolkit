import logging
import os
import sys
import time
import io
from typing import Any, Optional
import numpy as np
try:
    import cv2
except ImportError:
    cv2 = None
import re

from ingestion.rag_router import RAGRouter
from ingestion.ocr_client import RemoteSuryaClient
import httpx
from PIL import Image
from ingestion.cleaning_utils import clean_llm_text

# Backwards-compatibility alias
SuryaExtractor = RemoteSuryaClient

# Optional cross-validator (gemini-3-flash) — enabled via CROSS_VALIDATE_OCR=1
try:
    from ingestion.cross_validator import validate_page_ocr as _cross_validate
    _CROSS_VALIDATE_ENABLED = os.environ.get("CROSS_VALIDATE_OCR", "1") == "1"
except ImportError:
    _cross_validate = None
    _CROSS_VALIDATE_ENABLED = False

logger = logging.getLogger(__name__)


# Global components — initialized lazily on first use to avoid loading heavy ML
# models at import time (e.g. when vision.py is imported in test or API contexts).
import threading as _threading

_router: "RAGRouter | None" = None
_ocr_engine: "RemoteSuryaClient | None" = None
_components_lock = _threading.Lock()


def _get_router() -> "RAGRouter":
    global _router
    if _router is None:
        with _components_lock:
            if _router is None:
                _router = RAGRouter()
    return _router


def _get_ocr_engine() -> "RemoteSuryaClient":
    global _ocr_engine
    if _ocr_engine is None:
        with _components_lock:
            if _ocr_engine is None:
                _ocr_engine = RemoteSuryaClient()
    return _ocr_engine


# Module-level shared HTTP client — reused across all vision fallback calls
# (avoids opening a new TCP connection per page in the thread pool)
_vision_http_client: httpx.Client | None = None
_vision_http_client_lock = _threading.Lock()


def _get_vision_http_client() -> httpx.Client:
    global _vision_http_client
    if _vision_http_client is None:
        with _vision_http_client_lock:
            if _vision_http_client is None:
                # Granular timeout — prevents permanent hang on large PDF pages
                # rag-core (local GPU) ~45-75s/page, cloud ~10-50s/page
                # read=150s gives 2× buffer even for slowest local GPU call
                _vision_http_client = httpx.Client(
                    timeout=httpx.Timeout(
                        connect=10.0,   # TCP handshake: fail fast
                        read=150.0,     # OCR response: rag-core max ~75s → 2× buffer
                        write=20.0,     # Image upload (base64)
                        pool=10.0,      # Connection pool wait
                    )
                )
    return _vision_http_client


class DummyMetric:
    def inc(self, amount=1): pass
    def set(self, val): pass


try:
    from prometheus_client import Counter, Gauge
    VISION_FALLBACK_COUNT = Counter('vision_fallback_total_vision', 'Total pages routed to Vision Fallback inside vision.py')
    OCR_PROCESSED_COUNT = Counter('ocr_processed_total', 'Total pages processed by OCR')
    OCR_AVG_CONF = Gauge('ocr_avg_conf', 'Average OCR confidence per page')
except (ImportError, ValueError) as e:
    logger.warning(f"Prometheus metrics init failed in vision.py ({e}). Using DummyMetrics.")
    VISION_FALLBACK_COUNT = DummyMetric()
    OCR_PROCESSED_COUNT = DummyMetric()
    OCR_AVG_CONF = DummyMetric()


def evaluate_ocr_quality(ocr_raw, page_num, total_pages):
    """
    Heuristic score: 0-100 logic.
    - OCR Confidence
    - Table density penalty
    - Keyword / Page position bonus
    """
    if not ocr_raw:
        return 0, 0.0

    valid_lines = [line for line in ocr_raw if line and len(line) >= 2 and line[1] and len(line[1]) >= 2]
    total_conf = sum([line[1][1] for line in valid_lines if isinstance(line[1][1], (int, float))])
    avg_conf = total_conf / len(valid_lines) if len(valid_lines) > 0 else 0
    full_text = "\n".join([line[1][0] for line in valid_lines if isinstance(line[1][0], str)])

    score = avg_conf * 100

    # Table Penalty (high density of pipes or grid signs means OCR might flatten it poorly)
    if full_text.count('|') > 5 or full_text.count('---+') > 2:
        score -= 20

    keyword_bonus = 0
    if page_num == 1:
        keyword_bonus += 15  # Metadata page
    elif page_num == total_pages:
        keyword_bonus += 10  # Signatures page

    # Legal Keywords indicating important structural zones
    for kw in ["cộng hòa", "độc lập", "nơi nhận", "ký thay", "mục lục", "phụ lục"]:
        if kw in full_text.lower():
            keyword_bonus += 5

    final_score = max(0, min(100, score + keyword_bonus))
    return final_score, avg_conf


def is_blank_page(img_bytes: bytes, surya_text: str = "", ocr_raw: Any = "NOT_PASSED") -> bool:
    """[Fix #1] Detect near-blank pages (signature, spacer) to prevent LLM prompt leakage.

    A page is considered blank if:
    - ocr_raw is not None (if worker failed, ocr_raw is None -> never consider blank), AND
    - Image has >90% near-white pixels (pixel value > 230), AND
    - Surya OCR extracted fewer than 60 meaningful characters

    Edge case: pages with small watermark/logo in corner may have ~75-80% white ratio
    — the combination of pixel check + text length check handles this gracefully:
    if Surya extracted >60 chars from the watermark, we safely skip blank detection.
    """
    if ocr_raw is None:
        return False
    try:
        if len(surya_text.strip()) > 60:
            return False  # Enough text — definitely not blank
        # Use numpy for ~50x faster pixel iteration vs Python list comprehension
        img_pil = Image.open(io.BytesIO(img_bytes)).convert('L')  # Grayscale
        arr = np.array(img_pil)
        if arr.size == 0:
            return True
        white_ratio = float((arr > 230).mean())
        return white_ratio > 0.90
    except Exception:
        return False  # Fail-safe: assume not blank


def is_toc_page(text: str) -> bool:
    """[Fix #2] Detect Table of Contents (Mục lục) page by structural patterns.

    TOC pages contain repeating patterns of:
      '1. QUY ĐỊNH CHUNG 5'  or  '1.1. Phạm vi điều chỉnh 5'
    where section titles are immediately followed by page numbers.

    Guards against false positives on technical parameter tables by requiring either:
    - Explicit 'MỤC LỤC' / 'mục lục' keyword on the page, OR
    - >= 3 lines matching TOC pattern (strong signal), OR
    - Inline TOC pattern ("1. TITLE 5 1.1. ... 7")
    """
    if not text or len(text) < 50:
        return False

    text_lower = text.lower()
    # Strong signal: explicit TOC keyword
    has_toc_keyword = 'mục lục' in text_lower or 'nội dung' in text_lower

    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    toc_line_count = sum(
        1 for line in lines
        if re.search(
            r'^\d+\.\d*\.?\s+[A-ZĐÀÁẢÃẠ].*\d{1,3}\s*$'   # '1.1. Title 5'
            r'|^\d+\.\s+[A-ZĐÀÁẢÃẠ].*\d{1,3}\s*$',          # '1. TITLE 5'
            line
        )
    )
    # Inline TOC pattern: "1. QUY ĐỊNH CHUNG 5 1.1. ...5"
    inline_toc = bool(re.search(
        r'\d+\.\s+[A-ZĐÀÁẢÃẠ]{3,}.*?\d+\s+\d+\.\d+',
        text
    ))

    # Require strong evidence: keyword + pattern, OR very strong pattern signal
    is_toc = (has_toc_keyword and toc_line_count >= 2) \
             or toc_line_count >= 4 \
             or inline_toc

    if is_toc:
        import hashlib
        page_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        logger.info(f"TOC page detected (hash={page_hash}, toc_lines={toc_line_count}, keyword={has_toc_keyword})")
    return is_toc


def call_vision_fallback(img_bytes, ocr_text, page_num, model="gemini-3-flash"):
    """Call Vision LLM for fallback extraction via LiteLLM"""
    import base64
    base64_image = base64.b64encode(img_bytes).decode('utf-8')
    prompt = (
        "Bạn là AI chuyên đọc và sao chép nguyên văn tài liệu pháp lý kỹ thuật Việt Nam. "
        "Dưới đây là bản nháp OCR của trang (có thể có lỗi nhận diện ký tự):\n---\n"
        f"{ocr_text}\n---\n"
        "Nhìn vào ảnh, hãy PHIÊN ÂM NGUYÊN VĂN toàn bộ nội dung trang, CHỈ sửa các lỗi OCR rõ ràng (ký tự bị nhận sai). "
        "QUY TẮC BẮT BUỘC:\n"
        "1. TUYỆT ĐỐI KHÔNG được diễn giải, tóm tắt, rút gọn, thêm, bỏ bớt hay thay đổi ý nghĩa bất kỳ câu văn nào.\n"
        "2. Chép NGUYÊN VĂN từng chữ, từng con số, từng dấu câu đúng như trong tài liệu gốc.\n"
        "3. Giữ nguyên tất cả số điều khoản (Điều X, X.Y, X.Y.Z), số liệu kỹ thuật, đơn vị đo lường.\n"
        "4. Giữ nguyên cấu trúc 'Điều', 'Chương', 'Mục', 'Phần' và thụt lề.\n"
        "5. NẾU TRANG CÓ BẢNG BIỂU, BẮT BUỘC chuyển sang MARKDOWN TABLE, giữ nguyên chính xác từng ô dữ liệu.\n"
        "6. SỬA LỖI DÍNH CHỮ: Nếu thấy các từ bị dính không có khoảng trắng (ví dụ: 'cóthể', 'BộXây'), hãy tách chúng đúng cách.\n"
        "7. NỐI LUỒNG VĂN BẢN: Nếu thấy Header/Footer/Số trang xen giữa một câu đang dở, hãy bỏ chúng đi và nối câu lại.\n"
        "8. XÓA RÁC TRANG: Bỏ qua các nội dung lặp (tiêu đề đầu trang, số trang 'Trang X/Y', watermark).\n"
        "Trả về CHỈ nội dung đã sao chép, không giải thích, không thêm bất kỳ nội dung nào ngoài tài liệu."
    )

    from core.ai_gateway_client import get_ai_gateway_client
    client = get_ai_gateway_client()
    try:
        content = client.complete_vision_sync(
            base64_image,
            prompt=prompt,
            model=model,
            model_chain=[model, "ocr-primary", "ocr-fallback", "rag-core"],
            max_tokens=8192,
            temperature=0.1,
        )
        return clean_llm_text(content)
    except Exception as e:
        logger.error(f"Vision fallback failed for page {page_num}: {e}")
        return ""


def call_table_vision_llm(img_data, ocr_text, page_num, is_pil=False):
    """Specialized call to convert a table image into a clean Markdown table via AIGatewayClient."""
    from core.ai_gateway_client import get_ai_gateway_client
    from io import BytesIO

    if is_pil:
        bio = BytesIO()
        img_data.save(bio, format="JPEG")
        img_bytes = bio.getvalue()
    else:
        img_bytes = img_data

    prompt = (
        "Bạn là chuyên gia sao chép NGUYÊN VĂN bảng biểu từ tài liệu kỹ thuật pháp lý sang Markdown. "
        "Dưới đây là văn bản thô trích xuất từ vùng bảng:\n---\n"
        f"{ocr_text}\n---\n"
        "Dựa vào ảnh, hãy chuyển bảng sang MARKDOWN TABLE với các quy tắc SAU ĐÂY:\n"
        "1. CHÉP NGUYÊN VĂN từng ô — KHÔNG được sửa đổi, dịch hay diễn giải nội dung ô nào.\n"
        "2. Giữ nguyên CẤU TRÚC hàng và cột, không gộp hay tách ô.\n"
        "3. KHÔNG bỏ sót bất kỳ ô nào, đặc biệt các số liệu kỹ thuật, đơn vị đo, tiêu chuẩn tham chiếu.\n"
        "4. Không thêm văn bản giải thích — chỉ trả về bảng Markdown thuần túy.\n"
        "5. Nếu có merged cells, điền lại dữ liệu vào từng ô riêng để Markdown đọc được.\n"
    )

    _TABLE_MODEL = os.environ.get("TABLE_VISION_MODEL", "gemini-3-flash")
    client = get_ai_gateway_client()
    try:
        content = client.complete_vision_sync(
            img_bytes,
            prompt=prompt,
            model=_TABLE_MODEL,
            model_chain=[_TABLE_MODEL, "ocr-primary", "rag-core"],
            max_tokens=8192,
            temperature=0.0,
        )
        if content:
            logger.info(f"  Table→Markdown page {page_num} OK ({len(content)} chars)")
            return clean_llm_text(content)
    except Exception as e:
        logger.warning(f"Table-to-Markdown failed for page {page_num}: {e}")

    return ocr_text


def hybrid_extract_page(img_bytes, page_num, total_pages):
    """
    Multi-Signal Vision Fallback Router using Surya OCR + Blackwell GPU.
    Enhanced with per-segment Table-to-Markdown reconstruction.
    """
    if OCR_PROCESSED_COUNT:
        OCR_PROCESSED_COUNT.inc()

    # Apply image preprocessing — full mode for Surya OCR (with binarize)
    page_difficulty = {}  # Will hold difficulty features for dynamic thresholding
    try:
        from ingestion.image_preprocessor import preprocess_page_image, preprocess_for_llm, compute_page_difficulty
        enhanced_bytes = preprocess_page_image(img_bytes, dpi=200, mode="full")
        # Keep a lightly processed copy for LLM Vision fallback (no binarize)
        llm_enhanced_bytes = preprocess_for_llm(img_bytes, dpi=200)
        # Compute page difficulty features for dynamic thresholding
        page_difficulty = compute_page_difficulty(img_bytes)
        if page_difficulty.get('difficulty_score', 0) > 0:
            logger.info(
                f"Page {page_num} difficulty: score={page_difficulty['difficulty_score']:.0f} "
                f"noise={page_difficulty['noise_level']:.0f} skew={page_difficulty['skew_angle']:.1f}° "
                f"contrast={page_difficulty['contrast_ratio']:.0f} density={page_difficulty['text_density']:.2f}"
            )
    except Exception:
        enhanced_bytes = img_bytes
        llm_enhanced_bytes = img_bytes

    # Convert enhanced bytes to PIL for Surya
    img_pil = Image.open(io.BytesIO(enhanced_bytes))

    # 1. Primary OCR Pass (Remote Surya Worker Microservice)
    ocr_raw = None
    layout = None
    ocr_engine = _get_ocr_engine()
    if ocr_engine and ocr_engine.available:
        ocr_raw, layout = ocr_engine.process_page(enhanced_bytes, page_num=page_num)
    else:
        logger.warning(f"Page {page_num}: OCR engine unavailable or not initialized.")

    bbox_list = [line[0] for line in ocr_raw] if ocr_raw else []

    # 2. Layout-Aware Segment Processing
    layout_segments = []
    has_table = False

    if ocr_raw and layout:
        # Sort layout elements top-to-bottom defensively
        def _get_seg_top(seg_obj):
            b = getattr(seg_obj, 'bbox', None)
            if isinstance(b, (list, tuple)) and len(b) > 1:
                try:
                    return float(b[1])
                except (ValueError, TypeError):
                    return 0.0
            return 0.0

        sorted_layout = sorted(layout, key=_get_seg_top)

        for seg in sorted_layout:
            seg_bbox = getattr(seg, 'bbox', None)
            if not isinstance(seg_bbox, list) or len(seg_bbox) < 4:
                continue

            seg_label = getattr(seg, 'label', 'text').lower()
            seg_text_lines = []

            # Map OCR lines to this segment
            for line in ocr_raw:
                line_bbox = line[0]
                line_data = line[1]
                if not line_data:
                    continue
                line_text = line_data[0]

                if isinstance(line_bbox, list) and len(line_bbox) == 4:
                    try:
                        # Center point intersection
                        cx = sum([p[0] for p in line_bbox]) / 4
                        cy = sum([p[1] for p in line_bbox]) / 4
                        if (seg_bbox[0] <= cx <= seg_bbox[2]) and (seg_bbox[1] <= cy <= seg_bbox[3]):
                            seg_text_lines.append(line_text)
                    except Exception:
                        pass

            if seg_text_lines or seg_label == 'table':
                raw_seg_text = "\n".join(filter(None, seg_text_lines))

                # SPECIAL HANDLING: Table Reconstruction
                if seg_label == 'table':
                    has_table = True
                    logger.info(f"  Page {page_num}: Detected table segment. Reconstructing as Markdown...")
                    try:
                        # Crop the table from the original PIL image
                        # seg_bbox is [xmin, ymin, xmax, ymax]
                        margin = 5
                        left = max(0, seg_bbox[0] - margin)
                        top = max(0, seg_bbox[1] - margin)
                        right = min(img_pil.width, seg_bbox[2] + margin)
                        bottom = min(img_pil.height, seg_bbox[3] + margin)

                        cropped_table = img_pil.crop((left, top, right, bottom))
                        recon_table = call_table_vision_llm(cropped_table, ocr_text=raw_seg_text, page_num=page_num, is_pil=True)

                        layout_segments.append({
                            "label": "table",
                            "text": recon_table,
                            "bbox": seg_bbox
                        })
                    except Exception as e:
                        logger.error(f"  Failed to reconstruct table on page {page_num}: {e}")
                        layout_segments.append({"label": "table", "text": raw_seg_text, "bbox": seg_bbox})
                else:
                    layout_segments.append({
                        "label": seg_label,
                        "text": raw_seg_text,
                        "bbox": seg_bbox
                    })

    # Assemble final text from segments (preserves layout order)
    if layout_segments:
        full_text = "\n\n".join([s["text"] for s in layout_segments])
    else:
        full_text = "\n".join([line[1][0] for line in ocr_raw]) if ocr_raw else ""

    # 3. Quality Assessment & Page-Level Fallback
    score, avg_conf = evaluate_ocr_quality(ocr_raw, page_num, total_pages)
    if OCR_AVG_CONF:
        OCR_AVG_CONF.set(avg_conf)

    vision_text = ""
    # Dynamic Thresholding — adjust fallback threshold based on page difficulty
    # Base thresholds: 55 for table pages, 70 for text pages
    base_threshold = 55 if has_table else 70
    diff_score = page_difficulty.get('difficulty_score', 0)
    if diff_score >= 50:
        # Very damaged page → raise threshold aggressively to force Vision Fallback
        threshold = min(90, base_threshold + 20)
        logger.info(f"Page {page_num}: HIGH difficulty ({diff_score:.0f}) → threshold raised to {threshold}")
    elif diff_score >= 25:
        # Moderately damaged → slight boost
        threshold = base_threshold + 10
    else:
        threshold = base_threshold

    # Force vision fallback on Annex pages that likely contain tables missed by the layout analyzer
    import re
    looks_like_annex_table = not has_table and bool(re.search(r'(?i)(phụ lục\s+\d+|đơn vị\s*:|tổng cộng|số tt|ghi chú)', full_text))
    if looks_like_annex_table:
        threshold = 80  # Higher threshold to strongly incentivize fallback for likely tables

    if ocr_raw is None:
        logger.warning(
            f"Page {page_num}: Remote OCR worker failed (ocr_raw is None). "
            "Bypassing blank page detection to prevent data loss and triggering Vision Fallback directly."
        )
        if VISION_FALLBACK_COUNT:
            VISION_FALLBACK_COUNT.inc()
        vision_text = call_vision_fallback(llm_enhanced_bytes, ocr_text="", page_num=page_num, model="gemini-3-flash")
    else:
        # [Fix #1] Blank page guard — prevent prompt leakage on signature/spacer pages
        if is_blank_page(img_bytes, surya_text=full_text, ocr_raw=ocr_raw):
            logger.info(f"Page {page_num}: Detected near-blank page (signature/spacer). Skipping Vision LLM.")
            return {"text": "", "bbox": bbox_list, "layout": layout_segments, "score": 0.0}

        # [Fix #2] TOC page guard — exclude table of contents from content
        if is_toc_page(full_text):
            logger.info(f"Page {page_num}: Detected TOC (Mục lục) page. Skipping to prevent noise in content.")
            return {"text": "", "bbox": bbox_list, "layout": layout_segments, "score": score}

        if score < threshold or looks_like_annex_table:
            logger.info(f"Page {page_num} score {score:.1f} < {threshold} (or seems like annex table). Triggering Primary Vision Fallback (gemini-3-flash).")
            if VISION_FALLBACK_COUNT:
                VISION_FALLBACK_COUNT.inc()
            vision_text = call_vision_fallback(llm_enhanced_bytes, ocr_text=full_text, page_num=page_num, model="gemini-3-flash")

    if vision_text:
        final_text = vision_text
        layout_segments = []  # Clear bad layout so we don't ignore the vision text in chunking

        # 4. Cross-OCR Validation (optional — enable via CROSS_VALIDATE_OCR=1)
        if _CROSS_VALIDATE_ENABLED and _cross_validate is not None and ocr_raw is not None:
            try:
                cv_result = _cross_validate(vision_text, full_text, page_num)
                if not cv_result.get("skipped"):
                    if not cv_result.get("passed"):
                        logger.warning(
                            f"[CrossValidate] p{page_num}: LOW FIDELITY "
                            f"sections={cv_result.get('section_coverage',0):.0%} "
                            f"words={cv_result.get('word_overlap',0):.0%} "
                            f"missing={cv_result.get('missing_sections',[])[:5]}"
                        )
                        from ingestion.cross_validator import retry_with_best
                        vision_text = retry_with_best(llm_enhanced_bytes, page_num, vision_text, full_text)
                    else:
                        logger.info(f"[CrossValidate] p{page_num}: OK sections={cv_result.get('section_coverage',0):.0%} words={cv_result.get('word_overlap',0):.0%}")
            except Exception as e:
                logger.debug(f"[CrossValidate] p{page_num}: skipped ({e})")
    else:
        final_text = full_text

    return {
        "text": final_text,
        "bbox": bbox_list,
        "score": score,
        "is_table": has_table,
        "layout": layout_segments,
        "source": "vision" if vision_text else ("surya" if ocr_raw is not None else "failed")
    }


def extract_metadata_and_relations(ocr_result: dict):
    """Gọi RAGRouter xử lý metadata + relation"""
    text = ocr_result.get("text", "")
    if not text.strip():
        return {}
    return _get_router().process(text)

# --- Compatibility Layer ---


class VisionExtractor:
    """Compatibility class to satisfy existing imports without breaking summary generation."""

    def __init__(self):
        self.gateway_url = os.environ.get("VLLM_API_BASE", "http://ai-gateway:4000/v1")
        self.api_url = f"{self.gateway_url}/chat/completions"
        api_key = os.environ.get("LITELLM_MASTER_KEY")
        if not api_key:
            raise RuntimeError(
                "LITELLM_MASTER_KEY environment variable is required for VisionExtractor."
            )
        self.api_key = api_key
        self.model = os.environ.get("VLLM_MODEL", "rag-core")
        logger.info(f"VisionExtractor (Hybrid-Proxy) initialized via Gateway: {self.gateway_url}")

    @staticmethod
    def _extract_content_for_summary(full_text: str, max_chars: int = 12000) -> str:
        """[Fix #3] Smart content selection: skip cover/TOC, start from substantive content.

        Improved: verifies that a found marker is actual content (not a TOC line)
        by checking the text immediately after the marker. TOC markers are immediately
        followed by '1.1.' sub-TOC items; real content has paragraph text.
        """
        content_markers = [
            r'(?m)^1\.\s+QUY ĐỊNH CHUNG',
            r'(?m)^Điều\s+1\.',
            r'(?m)^I\.\s+QUY ĐỊNH',
            r'(?m)^Lời nói đầu',
        ]
        start_pos = 0
        matched = False

        for marker in content_markers:
            search_from = 0
            while True:
                m = re.search(marker, full_text[search_from:], re.IGNORECASE)
                if not m:
                    break
                abs_pos = search_from + m.start()
                # Must be within 60% of document (skip if too deep)
                if abs_pos > len(full_text) * 0.6:
                    break
                # Must not be at very beginning (cover page echo)
                if abs_pos < 50:
                    search_from = abs_pos + len(m.group())
                    continue
                # Verify it's real content, not TOC:
                # TOC: marker line immediately followed by '1.1.' sub-items
                after = full_text[abs_pos + len(m.group()):abs_pos + len(m.group()) + 200]
                is_toc = bool(re.match(r'\s*\n\s*1\.1\.', after))
                if is_toc:
                    # This is a TOC line, find next occurrence
                    search_from = abs_pos + len(m.group())
                    continue
                # Real content found
                start_pos = abs_pos
                matched = True
                break
            if matched:
                break

        # Fallback: no marker matched → skip first ~3000 chars (cover + TOC estimate)
        if not matched and len(full_text) > 4000:
            start_pos = min(3000, len(full_text) // 5)

        return full_text[start_pos:start_pos + max_chars]

    def generate_summary(self, full_text: str) -> str:
        """Generate summary using the 9B model via LiteLLM/vLLM."""
        if not full_text.strip():
            return ""

        # [Fix #3] Use smart content selection instead of raw first 15k chars
        content_for_summary = self._extract_content_for_summary(full_text)

        _SUMMARY_SYSTEM = """Bạn là chuyên gia tóm tắt văn bản kỹ thuật pháp lý Việt Nam.
CHỈ viết bằng tiếng Việt. KHÔNG BAO GIỜ viết tiếng Anh.

QUY TẮC BẮT BUỘC:
- Tối đa 1500 ký tự
- Mô tả NỘI DUNG KỸ THUẬT VÀ PHÁP LÝ thực sự của tài liệu:
  + Phạm vi và đối tượng áp dụng
  + Các yêu cầu kỹ thuật hoặc quy định pháp lý quan trọng nhất
  + Cơ quan ban hành và hiệu lực
- KHÔNG liệt kê mục lục, chương, điều theo kiểu TOC
- KHÔNG giải thích quá trình suy nghĩ
- KHÔNG viết "Internal Monologue", "Drafting", "Strategy"
- KHÔNG đánh số bước phân tích (1. **, 2. **)
- KHÔNG dùng markdown đặc biệt (**, ##, *)
- Chỉ xuất nội dung tóm tắt thuần túy dạng đoạn văn"""

        from core.ai_gateway_client import get_ai_gateway_client
        client = get_ai_gateway_client()
        messages = [
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {"role": "user", "content": f"Tóm tắt nội dung kỹ thuật và pháp lý của văn bản sau bằng tiếng Việt:\n\n{content_for_summary}"}
        ]
        try:
            content = client.complete_sync(
                messages,
                model=self.model,
                max_tokens=400,
                temperature=0.1,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            return clean_llm_text(content, is_summary=True)
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return ""

    def extract_from_pdf_pages(self, file_path: str, pages=None):
        logger.warning("extract_from_pdf_pages proxy used. Use new hybrid pipeline methods directly.")
        return [], []
