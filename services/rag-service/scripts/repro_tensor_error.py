import torch
import fitz
from PIL import Image
import io
import logging
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.layout import LayoutPredictor
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
    # Test first 5 pages
    for i in range(min(5, len(doc))):
        logger.info(f"Processing page {i+1}...")
        page = doc[i]
        pix = page.get_pixmap(dpi=150)
        img_pil = Image.open(io.BytesIO(pix.tobytes("jpeg")))
        
        logger.info("  Testing OCR with math_mode=True (default)...")
        try:
            res = rec_predictor([img_pil], det_predictor=det_predictor, math_mode=True)
            logger.info(f"  Page {i+1} OCR Success (math=True)")
        except Exception as e:
            logger.error(f"  Page {i+1} OCR FAILED (math=True): {e}", exc_info=True)
            
        logger.info("  Testing OCR with math_mode=False...")
        try:
            res = rec_predictor([img_pil], det_predictor=det_predictor, math_mode=False)
            logger.info(f"  Page {i+1} OCR Success (math=False)")
        except Exception as e:
            logger.error(f"  Page {i+1} OCR FAILED (math=False): {e}", exc_info=True)

if __name__ == "__main__":
    repro()
