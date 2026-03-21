import torch
import fitz
from PIL import Image
import io
import logging
import numpy as np
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.foundation import FoundationPredictor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def repro():
    file_path = "/app/data/legal_docs_source/Linh vuc_BQP/Quy chuan-Tieu chuan BQP ban hanh/TCVN-QS 1822-2021_Trang phuc dan quan tu ve_tiep.pdf"
    device = "cpu"
    
    logger.info(f"Initializing predictors on {device}...")
    foundation = FoundationPredictor(device=device)
    det_predictor = DetectionPredictor(device=device)
    rec_predictor = RecognitionPredictor(foundation)
    
    doc = fitz.open(file_path)
    # Test page 2
    for i in [1]: 
        logger.info(f"Processing page {i+1}...")
        page = doc[i]
        pix = page.get_pixmap(dpi=150)
        img_pil = Image.open(io.BytesIO(pix.tobytes("jpeg")))
        
        logger.info("  Step 1: Detection...")
        det_results = det_predictor([img_pil])
        # Convert PolygonBox objects to List[List[int]] as expected by RecognitionPredictor
        # Polygon is List[List[int]] i.e. [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        polygons = [[p.polygon for p in det_results[0].bboxes]]
        logger.info(f"  Detected {len(polygons[0])} lines.")
        
        logger.info("  Step 2: Recognition (math_mode=True, whole page)...")
        try:
            res = rec_predictor([img_pil], polygons=polygons, math_mode=True)
            logger.info("    Success (math=True)")
        except Exception as e:
            logger.error(f"    FAILED (math=True): {e}")

        logger.info("  Step 3: Recognition (math_mode=False, whole page)...")
        try:
            res = rec_predictor([img_pil], polygons=polygons, math_mode=False)
            logger.info("    Success (math=False)")
        except Exception as e:
            logger.error(f"    FAILED (math=False): {e}")

if __name__ == "__main__":
    repro()
