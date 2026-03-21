import torch
from PIL import Image
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.layout import LayoutPredictor
from surya.foundation import FoundationPredictor
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_surya():
    device = "cpu"
    logger.info(f"Using device: {device}")
    
    # Create a dummy image
    img = Image.new('RGB', (100, 100), color = (73, 109, 137))
    
    logger.info("Initializing predictors...")
    foundation = FoundationPredictor()
    det_predictor = DetectionPredictor()
    rec_predictor = RecognitionPredictor(foundation)
    layout_predictor = LayoutPredictor(foundation)
    
    logger.info("Testing OCR...")
    try:
        # In 0.17.1, rec_predictor call:
        # predictions = rec_predictor([img], [["vi"]], det_predictor)
        predictions = rec_predictor([img], [["en"]], det_predictor)
        logger.info(f"OCR Success: {len(predictions)} results")
    except Exception as e:
        logger.error(f"OCR Failed: {e}", exc_info=True)
        
    logger.info("Testing Layout...")
    try:
        # In 0.17.1, layout_predictor call:
        # Maybe it needs explicit arguments?
        layout_predictions = layout_predictor([img], det_predictor)
        logger.info(f"Layout Success: {len(layout_predictions)} results")
    except Exception as e:
        logger.error(f"Layout Failed: {e}", exc_info=True)

if __name__ == "__main__":
    test_surya()
