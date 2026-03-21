import logging
import fitz
import os
from ocr_utils import perform_ocr, extract_metadata_and_relations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_small():
    pdf_path = "data/legal_test/Luat_50-2014-QH13_Luat Xay dung_18-6-2014.pdf"
    img_path = "test_page_1.png"
    
    # 1. Render only page 1
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap()
    pix.save(img_path)
    doc.close()
    
    logger.info(f"Page 1 rendered to {img_path}")
    
    # 2. Test hybrid flow on this image
    logger.info("Running perform_ocr...")
    ocr_res = perform_ocr(img_path)
    logger.info(f"OCR Text: {ocr_res['text'][:200]}...")
    
    logger.info("Running extract_metadata_and_relations...")
    semantic_res = extract_metadata_and_relations(ocr_res)
    print("\n--- Semantic Result ---")
    print(semantic_res)
    
if __name__ == "__main__":
    test_small()
