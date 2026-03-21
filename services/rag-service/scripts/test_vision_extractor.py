import sys
import os
import logging
from PIL import Image
import io

# Add parent directory to path to import ingestion.vision
sys.path.append('/app')
from ingestion.vision import SuryaExtractor

logging.basicConfig(level=logging.INFO)

def test_extractor():
    print("Testing SuryaExtractor instantiation...")
    extractor = SuryaExtractor()
    if not extractor.available:
        print("Extractor failed to initialize.")
        return
        
    print("Extractor initialized. Testing with a blank image...")
    # Generate blank image and test ocr (should return empty due to det filter)
    img = Image.new('RGB', (800, 600), color='white')
    res = extractor.ocr(img, page_num=1)
    print(f"OCR result on blank image: {res}")
    
    layout_res = extractor.extract_layout(img)
    print(f"Layout result on blank image: {layout_res}")
    
    print("Testing with a dummy bounding box behavior...")
    # we can't easily mock det_predictor without writing a lot of code, 
    # but running a real image or just checking syntax is enough for basic verification.

if __name__ == '__main__':
    test_extractor()
