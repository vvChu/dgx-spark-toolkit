import logging
import os
import sys
import types
import time
import io
import numpy as np
import cv2
import re

# --- LangChain Legacy Shims (Fix for PaddleOCR/PaddleX) ---
try:
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    
    # docstore shim
    ms_docstore = types.ModuleType('langchain.docstore')
    sys.modules['langchain.docstore'] = ms_docstore
    ms_document = types.ModuleType('langchain.docstore.document')
    sys.modules['langchain.docstore.document'] = ms_document
    ms_document.Document = Document
    
    # text_splitter shim
    ms_splitter = types.ModuleType('langchain.text_splitter')
    sys.modules['langchain.text_splitter'] = ms_splitter
    ms_splitter.RecursiveCharacterTextSplitter = RecursiveCharacterTextSplitter
    
    logging.info("LangChain legacy shims applied successfully.")
except ImportError as e:
    logging.warning(f"Failed to apply LangChain shims: {e}")

try:
    from surya.detection import DetectionPredictor
    from surya.recognition import RecognitionPredictor
    from surya.foundation import FoundationPredictor
    from surya.layout import LayoutPredictor
    SURYA_AVAILABLE = True
except ImportError:
    SURYA_AVAILABLE = False

from ingestion.rag_router import RAGRouter
import httpx
from PIL import Image
import torch
from ingestion.cleaning_utils import clean_llm_text

logger = logging.getLogger(__name__)

class SuryaExtractor:
    """Surya OCR & Layout Engine - Optimized for ARM64 + Blackwell GPU (v0.17+ API)."""
    def __init__(self):
        if not SURYA_AVAILABLE:
            self.available = False
            return
        
        # Force CPU for Surya to avoid CUDA device-side assert errors on Blackwell
        self.device = "cpu"
        logger.info(f"Initializing Surya Predictors on {self.device} (Forced stability mode)...")
        
        try:
            self.foundation_predictor = FoundationPredictor(device=self.device)
            self.det_predictor = DetectionPredictor(device=self.device)
            self.rec_predictor = RecognitionPredictor(self.foundation_predictor)
            self.layout_predictor = LayoutPredictor(self.foundation_predictor)
            self.available = True
            logger.info("Surya OCR & Layout Predictors ready.")
        except Exception as e:
            logger.error(f"Failed to load Surya models: {e}")
            self.available = False

    def ocr(self, img_pil, langs=['vi'], page_num=0):
        if not self.available:
            return []
            
        # 1. Granular Detection & Filtering
        try:
            det_results = self.det_predictor([img_pil])
        except Exception as e:
            logger.error(f"Surya detection failed: {e}")
            return []
            
        if not det_results or not getattr(det_results[0], 'bboxes', None):
            return []
            
        valid_bboxes = []
        for bbox_obj in det_results[0].bboxes:
            polygon = getattr(bbox_obj, 'polygon', None)
            if not polygon or len(polygon) != 4:
                continue
                
            # Validate area and shape to filter degenerate boxes
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            
            if width * height < 50 or width <= 0 or height <= 0:
                continue
                
            # Filter anomalous aspect ratios that cause transformer sequence glitches
            if width / height > 100 or height / width > 100:
                continue
                
            valid_bboxes.append(polygon)

        if not valid_bboxes:
            return []

        results = []
        
        # 2. Try chunked mini-batched OCR to avoid PyTorch IndexError on large dimension 0 sizes
        import time
        from io import BytesIO
        
        failed_boxes_count = 0
        math_false_count = 0
        chunk_size = 8  # Reduced from 16 to mitigate Tensor indexing errors on high system load
        
        for i in range(0, len(valid_bboxes), chunk_size):
            chunk_bboxes = valid_bboxes[i:i+chunk_size]
            try:
                # Attempt to process a chunk of 16 boxes
                predictions = self.rec_predictor(
                    [img_pil], 
                    polygons=[chunk_bboxes], 
                    math_mode=True
                )
                if predictions and getattr(predictions[0], 'text_lines', None):
                    for line in predictions[0].text_lines:
                        p = getattr(line, 'polygon', None)
                        if p:
                            results.append([p, (line.text, line.confidence)])
            except Exception as e:
                logger.warning(f"Surya OCR mini-batch ({i} to {i+len(chunk_bboxes)}) failed ({type(e).__name__}): {e}. Granular fallback for this chunk...")
                
                # 3. Granular Tiered Fallback for only the failed chunk
                for idx, poly in enumerate(chunk_bboxes):
                    try:
                        # Retry math_mode=True for the individual box
                        res = self.rec_predictor([img_pil], polygons=[[poly]], math_mode=True)
                        if res and getattr(res[0], 'text_lines', None) and res[0].text_lines:
                            line = res[0].text_lines[0]
                            results.append([line.polygon, (line.text, line.confidence)])
                    except Exception as e1:
                        # Re-try with math_mode=False
                        try:
                            res = self.rec_predictor([img_pil], polygons=[[poly]], math_mode=False)
                            if res and getattr(res[0], 'text_lines', None) and res[0].text_lines:
                                line = res[0].text_lines[0]
                                results.append([line.polygon, (line.text, line.confidence)])
                                math_false_count += 1
                        except Exception as e2:
                            failed_boxes_count += 1
                            logger.warning(f"Granular box {i+idx} complete OCR failure: {e2}. Triggering Vision LLM fallback for this box...")
                            try:
                                xs = [p[0] for p in poly]
                                ys = [p[1] for p in poly]
                                bbox = (min(xs), min(ys), max(xs), max(ys))
                                cropped = img_pil.crop(bbox)
                                bio = BytesIO()
                                cropped.save(bio, format="JPEG")
                                img_bytes = bio.getvalue()
                                
                                text_llm = call_vision_fallback(img_bytes, ocr_text="", page_num=page_num)
                                if text_llm:
                                    results.append([poly, (text_llm, 0.85)])
                            except Exception as e3:
                                logger.error(f"Vision LLM fallback for granular box {i+idx} failed: {e3}")
        
        if failed_boxes_count > 0 or math_false_count > 0:
            logger.info(f"Mini-batch OCR complete: {len(valid_bboxes)} boxes processed. {math_false_count} math_mode=False retries. {failed_boxes_count} Vision LLM fallbacks.")
            
        return results

    def extract_layout(self, img_pil):
        """Extract layout segments (Table, Header, Text, etc.)"""
        if not self.available:
            return []
        
        try:
            # Use a short timeout or check if layout_predictor is still healthy
            layout_predictions = self.layout_predictor([img_pil])
            if layout_predictions and getattr(layout_predictions[0], 'bboxes', None):
                valid_layout = []
                for b in layout_predictions[0].bboxes:
                    # Validate polygon existence and shape defensively
                    poly = getattr(b, 'polygon', None)
                    if poly and len(poly) == 4:
                        valid_layout.append(b)
                return valid_layout
            return []
        except (AttributeError, IndexError, TypeError, RuntimeError) as e:
            # Catch RuntimeError for specific tensor shape mismatches (common in Surya v0.17+ on varying hardware)
            if "tensor" in str(e).lower() or "size" in str(e).lower():
                logger.warning(f"Surya Layout tensor shape mismatch: {e}. Falling back to empty layout.")
            else:
                logger.warning(f"Surya Layout internal error: {e}. Skipping structural layout.")
            return []
        except Exception as e:
            logger.error(f"Surya Layout unexpected failure: {e}")
            return []

# Global components — initialized lazily on first use to avoid loading heavy ML
# models at import time (e.g. when vision.py is imported in test or API contexts).
import threading as _threading

_router: "RAGRouter | None" = None
_ocr_engine: "SuryaExtractor | None" = None
_components_lock = _threading.Lock()


def _get_router() -> "RAGRouter":
    global _router
    if _router is None:
        with _components_lock:
            if _router is None:
                _router = RAGRouter()
    return _router


def _get_ocr_engine() -> "SuryaExtractor":
    global _ocr_engine
    if _ocr_engine is None:
        with _components_lock:
            if _ocr_engine is None:
                _ocr_engine = SuryaExtractor()
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
                _vision_http_client = httpx.Client(timeout=600)
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
        keyword_bonus += 15 # Metadata page
    elif page_num == total_pages:
        keyword_bonus += 10 # Signatures page
        
    # Legal Keywords indicating important structural zones
    for kw in ["cộng hòa", "độc lập", "nơi nhận", "ký thay", "mục lục", "phụ lục"]:
        if kw in full_text.lower():
            keyword_bonus += 5
            
    final_score = max(0, min(100, score + keyword_bonus))
    return final_score, avg_conf

def call_vision_fallback(img_bytes, ocr_text, page_num):
    """Call rag-core (Qwen3.5 35B Multimodal) for fallback extraction via LiteLLM"""
    import base64
    base64_image = base64.b64encode(img_bytes).decode('utf-8')
    prompt = (
        "Bạn là AI đọc tài liệu pháp lý chuyên nghiệp. Dưới đây là bản nháp OCR của trang:\n---\n"
        f"{ocr_text}\n---\n"
        "Hãy sửa các lỗi do OCR đọc sai (đặc biệt là bảng biểu, số hiệu, con dấu, chữ ký). "
        "YÊU CẦU QUAN TRỌNG:\n"
        "1. Phải giữ nguyên các nhãn cấu trúc như 'Điều', 'Chương', 'Mục', 'Phần' và định dạng của chúng để không làm hỏng logic chia chunk.\n"
        "2. NẾU TRANG CÓ BẢNG BIỂU, BẮT BUỘC phải chuyển đổi thành định dạng MARKDOWN TABLE (giữ nguyên hàng cột, không bỏ sót dữ liệu).\n"
        "Trả về CHỈ nội dung đã sửa hoàn chỉnh, giữ đúng định dạng. Không giải thích."
    )

    gateway_url = os.environ.get("VLLM_API_BASE", "http://ai-gateway:4000/v1")
    api_key = os.environ.get("LITELLM_MASTER_KEY")
    if not api_key:
        logger.error("LITELLM_MASTER_KEY is not set; cannot call vision fallback.")
        return ""

    payload = {
        "model": "rag-core",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.1
    }
    max_retries = 5
    retry_delay = 2
    client = _get_vision_http_client()
    for attempt in range(max_retries):
        try:
            resp = client.post(
                f"{gateway_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )

            if resp.status_code == 429:
                wait_time = retry_delay * (2 ** attempt)
                logger.warning(f"Rate limited (429) on page {page_num}. Retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(wait_time)
                continue

            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or "choices" not in data or not data["choices"]:
                logger.warning(f"Invalid API response in vision fallback: {data}")
                return ""
            msg = data['choices'][0].get('message', {})
            content = msg.get('content', "")
            return clean_llm_text(content)
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Vision fallback failed for page {page_num} after {max_retries} attempts: {e}")
                return ""
            wait_time = retry_delay * (2 ** attempt)
            logger.warning(f"Vision fallback attempt {attempt+1}/{max_retries} failed for page {page_num}: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
    return ""

def call_table_vision_llm(img_data, ocr_text, page_num, is_pil=False):
    """Specialized call to rag-core to convert a table image into a clean Markdown table."""
    import base64
    from io import BytesIO
    
    if is_pil:
        bio = BytesIO()
        img_data.save(bio, format="JPEG")
        img_bytes = bio.getvalue()
    else:
        img_bytes = img_data

    base64_image = base64.b64encode(img_bytes).decode('utf-8')
    prompt = (
        "Bạn là chuyên gia chuyển đổi bảng biểu từ ảnh sang Markdown. "
        "Dưới đây là một số đoạn văn bản thô trích xuất từ vùng chứa bảng (có thể bị sai định dạng):\n---\n"
        f"{ocr_text}\n---\n"
        "Hãy dựa vào ảnh và văn bản thô để kiến tạo lại bảng này dưới dạng MARKDOWN TABLE chính xác nhất. "
        "YÊU CẦU: \n"
        "1. Phải giữ nguyên cấu trúc hàng và cột.\n"
        "2. Không được bỏ sót dữ liệu số hoặc văn bản trong các ô.\n"
        "3. Tuyệt đối không thêm văn bản giải thích, chỉ trả về bảng Markdown.\n"
        "4. Nếu có các ô bị gộp (merged cells), hãy xử lý sao cho hợp lý nhất trong Markdown.\n"
    )

    gateway_url = os.environ.get("VLLM_API_BASE", "http://ai-gateway:4000/v1")
    api_key = os.environ.get("LITELLM_MASTER_KEY")
    client = _get_vision_http_client()
    
    payload = {
        "model": "rag-core",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.0
    }

    try:
        resp = client.post(
            f"{gateway_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data['choices'][0]['message'].get('content', "")
        return clean_llm_text(content)
    except Exception as e:
        logger.error(f"Table-to-Markdown LLM call failed for page {page_num}: {e}")
        return ocr_text


def hybrid_extract_page(img_bytes, page_num, total_pages):
    """
    Multi-Signal Vision Fallback Router using Surya OCR + Blackwell GPU.
    Enhanced with per-segment Table-to-Markdown reconstruction.
    """
    if OCR_PROCESSED_COUNT:
        OCR_PROCESSED_COUNT.inc()
        
    # Convert bytes to PIL for Surya
    img_pil = Image.open(io.BytesIO(img_bytes))
    
    # 1. Primary OCR Pass (Surya)
    ocr_raw = []
    layout = []
    ocr_engine = _get_ocr_engine()
    if ocr_engine and ocr_engine.available:
        ocr_raw = ocr_engine.ocr(img_pil, page_num=page_num)
        layout = ocr_engine.extract_layout(img_pil)
    
    bbox_list = [line[0] for line in ocr_raw] if ocr_raw else []
    
    # 2. Layout-Aware Segment Processing
    layout_segments = []
    has_table = False
    
    if ocr_raw and layout:
        # Sort layout elements top-to-bottom
        sorted_layout = sorted(layout, key=lambda x: (getattr(x, 'bbox', [0,0,0,0])[1]))
        
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
                if not line_data: continue
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
    # Threshold for full page fallback (lower if we already handled tables well)
    # [I1] Lowered thresholds: 70 (was 80) for text, 55 (was 65) for table pages
    threshold = 55 if has_table else 70
    
    # Force vision fallback on Annex pages that likely contain tables missed by the layout analyzer
    import re
    looks_like_annex_table = not has_table and bool(re.search(r'(?i)(phụ lục\s+\d+|đơn vị\s*:|tổng cộng|số tt|ghi chú)', full_text))
    if looks_like_annex_table:
        threshold = 80  # Higher threshold to strongly incentivize fallback for likely tables
    
    if score < threshold or looks_like_annex_table:
        logger.info(f"Page {page_num} score {score:.1f} < {threshold} (or seems like annex table). Triggering Full Vision Fallback (rag-core).")
        if VISION_FALLBACK_COUNT:
            VISION_FALLBACK_COUNT.inc()
        vision_text = call_vision_fallback(img_bytes, ocr_text=full_text, page_num=page_num)
        
    if vision_text:
        final_text = vision_text
        layout_segments = []  # Clear bad layout so we don't ignore the vision text in chunking
    else:
        final_text = full_text
    
    return {
        "text": final_text,
        "bbox": bbox_list,
        "score": score,
        "is_table": has_table,
        "layout": layout_segments, 
        "source": "vision" if vision_text else "surya"
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

    def generate_summary(self, full_text: str) -> str:
        """Generate summary using the 9B model via LiteLLM/vLLM."""
        if not full_text.strip():
            return ""

        _SUMMARY_SYSTEM = """Bạn là chuyên gia tóm tắt văn bản pháp luật Việt Nam.
CHỈ viết bằng tiếng Việt. KHÔNG BAO GIỜ viết tiếng Anh.
Hãy tạo bản tóm tắt ngắn gọn, rõ ràng, giữ nguyên ý chính của văn bản.

QUY TẮC BẮT BUỘC:
- Tối đa 1500 ký tự
- KHÔNG giải thích quá trình suy nghĩ
- KHÔNG viết "Internal Monologue", "Drafting", "Strategy", "Task Interpretation"
- KHÔNG đánh số bước phân tích (1. **, 2. **)
- KHÔNG dùng markdown (**, ##, *)
- Chỉ xuất nội dung tóm tắt thuần túy"""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SUMMARY_SYSTEM},
                {"role": "user", "content": f"Tóm tắt văn bản pháp luật sau bằng tiếng Việt:\n\n{full_text[:15000]}"}
            ],
            "max_tokens": 400,
            "temperature": 0.1,
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": False}
            }
        }

        try:
            client = _get_vision_http_client()
            resp = client.post(self.api_url, headers={"Authorization": f"Bearer {self.api_key}"}, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return clean_llm_text(content, is_summary=True)
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return ""

    def extract_from_pdf_pages(self, file_path: str, pages=None):
        logger.warning("extract_from_pdf_pages proxy used. Use new hybrid pipeline methods directly.")
        return [], []

