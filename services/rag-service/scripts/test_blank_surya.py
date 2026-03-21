import torch
from PIL import Image
import logging
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.layout import LayoutPredictor
from surya.foundation import FoundationPredictor

logging.basicConfig(level=logging.INFO)

img_pil = Image.new('RGB', (800, 600), color = 'white')

foundation = FoundationPredictor(device="cpu")
det_predictor = DetectionPredictor(device="cpu")
rec_predictor = RecognitionPredictor(foundation)
layout_predictor = LayoutPredictor(foundation)

print("Starting Layout Predictor on blank image...")
try:
    layout_predictions = layout_predictor([img_pil])
    print("Layout success:", layout_predictions)
except Exception as e:
    print("Layout failed:", type(e).__name__, e)

print("Starting Recognition Predictor on blank image...")
try:
    predictions = rec_predictor([img_pil], det_predictor=det_predictor, math_mode=True)
    print("Rec success:", predictions)
except Exception as e:
    print("Rec failed:", type(e).__name__, e)
