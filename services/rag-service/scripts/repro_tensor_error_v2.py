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
    # Test page 2 (usually where errors start appearing in these logs)
    for i in [1]: 
        logger.info(f"Processing page {i+1}...")
        page = doc[i]
        pix = page.get_pixmap(dpi=150)
        img_pil = Image.open(io.BytesIO(pix.tobytes("jpeg")))
        
        logger.info("  Step 1: Detection...")
        det_results = det_predictor([img_pil])
        bboxes = [res.bboxes for res in det_results]
        logger.info(f"  Detected {len(bboxes[0])} lines.")
        
        logger.info("  Step 2: Recognition (Whole page at once)...")
        try:
            res = rec_predictor([img_pil], bboxes=bboxes)
            logger.info("    Success (Whole page)")
        except Exception as e:
            logger.error(f"    FAILED (Whole page): {e}")

        logger.info("  Step 3: Recognition (Granular - batch size 1)...")
        success_count = 0
        fail_count = 0
        for idx, bbox in enumerate(bboxes[0]):
            try:
                # rec_predictor expects List[List[List[int]]] for bboxes
                single_bbox = [[bbox]] 
                res = rec_predictor([img_pil], bboxes=[[bbox]])
                success_count += 1
            except Exception as e:
                logger.error(f"    Line {idx} FAILED: {e}")
                fail_count += 1
        
        logger.info(f"  Granular Results: {success_count} success, {fail_count} failure.")

if __name__ == "__main__":
    repro()
