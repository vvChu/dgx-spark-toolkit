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
    # Test problematic page
    for i in [1]: 
        logger.info(f"Processing page {i+1}...")
        page = doc[i]
        pix = page.get_pixmap(dpi=150)
        img_pil = Image.open(io.BytesIO(pix.tobytes("jpeg")))
        
        logger.info("  Detection...")
        det_results = det_predictor([img_pil])
        polygons = [[p.polygon for p in det_results[0].bboxes]]
        logger.info(f"  Detected {len(polygons[0])} lines.")
        
        logger.info("  Recognition (recognition_batch_size=1)...")
        try:
            # Crucial: pass recognition_batch_size=1
            res = rec_predictor([img_pil], polygons=polygons, recognition_batch_size=1)
            logger.info("    Success with batch_size=1")
        except Exception as e:
            logger.error(f"    FAILED even with batch_size=1: {e}", exc_info=True)

if __name__ == "__main__":
    repro()
