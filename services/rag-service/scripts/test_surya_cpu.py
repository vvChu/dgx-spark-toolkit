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
    
    # Create a dummy image with some text-like features (black on white)
    img = Image.new('RGB', (200, 50), color = (255, 255, 255))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.text((10,10), "Surya CPU Test", fill=(0,0,0))
    
    logger.info("Initializing predictors...")
    foundation = FoundationPredictor(device=device)
    det_predictor = DetectionPredictor(device=device)
    rec_predictor = RecognitionPredictor(foundation)
    layout_predictor = LayoutPredictor(foundation)
    
    logger.info("Testing OCR...")
    try:
        # Fixed signature for 0.17.1
        predictions = rec_predictor([img], det_predictor=det_predictor)
        logger.info(f"OCR Success: {len(predictions)} results")
        if predictions:
            logger.info(f"First prediction text lines: {len(predictions[0].text_lines)}")
            for line in predictions[0].text_lines:
                logger.info(f"Text detected: {line.text}")
    except Exception as e:
        logger.error(f"OCR Failed: {e}", exc_info=True)
        
    logger.info("Testing Layout...")
    try:
        # Fixed signature for 0.17.1
        layout_predictions = layout_predictor([img])
        logger.info(f"Layout Success: {len(layout_predictions)} results")
    except Exception as e:
        logger.error(f"Layout Failed: {e}", exc_info=True)

if __name__ == "__main__":
    test_surya()
