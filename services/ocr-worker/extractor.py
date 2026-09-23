import io
import logging
import os
from typing import Any, Dict, List
from PIL import Image

try:
    from surya.detection import DetectionPredictor
    from surya.foundation import FoundationPredictor
    from surya.layout import LayoutPredictor
    from surya.recognition import RecognitionPredictor
    SURYA_AVAILABLE = True
except ImportError:
    SURYA_AVAILABLE = False

logger = logging.getLogger("ocr-worker.extractor")


class SuryaWorkerExtractor:
    """Surya OCR & Layout Engine running in dedicated worker process on CPU."""

    def __init__(self, device: str = "cpu"):
        self.device = os.environ.get("SURYA_DEVICE", device)
        self.available = False
        if not SURYA_AVAILABLE:
            logger.error("surya-ocr library is not installed in worker environment.")
            return

        logger.info(f"Initializing Surya Predictors on {self.device}...")
        try:
            self.foundation_predictor = FoundationPredictor(device=self.device)
            self.det_predictor = DetectionPredictor(device=self.device)
            self.rec_predictor = RecognitionPredictor(self.foundation_predictor)
            self.layout_predictor = LayoutPredictor(self.foundation_predictor)
            self.available = True
            logger.info(f"Surya OCR & Layout Predictors ready on {self.device}.")
        except Exception as e:
            logger.error(f"Failed to initialize Surya predictors on {self.device}: {e}", exc_info=True)
            self.available = False

    def process(self, img_bytes: bytes) -> Dict[str, Any]:
        """Perform Detection, Recognition, and Layout extraction in a single pass.

        Returns:
            Dict containing:
              - ocr_raw: list of [polygon, [text, confidence]]
              - layout: list of {"bbox": [xmin, ymin, xmax, ymax], "label": str, "polygon": [...]}
        """
        if not self.available:
            logger.warning("SuryaWorkerExtractor called but extractor is not available.")
            return {"ocr_raw": [], "layout": []}

        if not img_bytes:
            return {"ocr_raw": [], "layout": []}

        try:
            img_pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception as e:
            logger.error(f"Failed to parse image bytes: {e}")
            return {"ocr_raw": [], "layout": []}

        # 1. Detection Pass
        try:
            det_results = self.det_predictor([img_pil])
        except Exception as e:
            logger.error(f"Surya detection failed: {e}")
            det_results = None

        valid_bboxes = []
        if det_results and getattr(det_results[0], "bboxes", None):
            for bbox_obj in det_results[0].bboxes:
                polygon = getattr(bbox_obj, "polygon", None)
                if not polygon or len(polygon) != 4:
                    continue

                xs = [p[0] for p in polygon]
                ys = [p[1] for p in polygon]
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)

                if width * height < 50 or width <= 0 or height <= 0:
                    continue

                if width / height > 100 or height / width > 100:
                    continue

                valid_bboxes.append(polygon)

        # 2. Recognition Pass (Chunked mini-batches)
        ocr_raw: List[Any] = []
        chunk_size = 8
        for i in range(0, len(valid_bboxes), chunk_size):
            chunk_bboxes = valid_bboxes[i:i + chunk_size]
            try:
                predictions = self.rec_predictor(
                    [img_pil],
                    polygons=[chunk_bboxes],
                    math_mode=True
                )
                if predictions and getattr(predictions[0], "text_lines", None):
                    for line in predictions[0].text_lines:
                        p = getattr(line, "polygon", None)
                        if p:
                            ocr_raw.append([p, [str(line.text), float(line.confidence)]])
            except Exception as e:
                logger.warning(
                    f"Surya OCR mini-batch ({i} to {i + len(chunk_bboxes)}) failed ({type(e).__name__}): {e}. "
                    "Granular fallback for this chunk..."
                )
                for idx, poly in enumerate(chunk_bboxes):
                    try:
                        res = self.rec_predictor([img_pil], polygons=[[poly]], math_mode=True)
                        if res and getattr(res[0], "text_lines", None) and res[0].text_lines:
                            line = res[0].text_lines[0]
                            ocr_raw.append([line.polygon, [str(line.text), float(line.confidence)]])
                    except Exception:
                        try:
                            res = self.rec_predictor([img_pil], polygons=[[poly]], math_mode=False)
                            if res and getattr(res[0], "text_lines", None) and res[0].text_lines:
                                line = res[0].text_lines[0]
                                ocr_raw.append([line.polygon, [str(line.text), float(line.confidence)]])
                        except Exception as e2:
                            logger.warning(f"Granular box {i + idx} complete failure: {e2}. Returning empty text.")
                            ocr_raw.append([poly, ["", 0.0]])

        # 3. Layout Extraction Pass
        layout_list: List[Dict[str, Any]] = []
        try:
            layout_predictions = self.layout_predictor([img_pil])
            if layout_predictions and getattr(layout_predictions[0], "bboxes", None):
                for b in layout_predictions[0].bboxes:
                    poly = getattr(b, "polygon", None)
                    if not poly or len(poly) != 4:
                        continue
                    bbox = getattr(b, "bbox", None)
                    if not bbox:
                        xs = [p[0] for p in poly]
                        ys = [p[1] for p in poly]
                        bbox = [min(xs), min(ys), max(xs), max(ys)]
                    label = getattr(b, "label", "text")
                    layout_list.append({
                        "bbox": list(bbox),
                        "label": str(label),
                        "polygon": [list(pt) for pt in poly]
                    })
        except Exception as e:
            logger.error(f"Surya layout extraction failed: {e}")

        return {
            "ocr_raw": ocr_raw,
            "layout": layout_list
        }
