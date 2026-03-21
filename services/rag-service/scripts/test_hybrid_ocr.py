import logging
import sys
import os
import json
from ocr_utils import perform_ocr, extract_metadata_and_relations

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_hybrid_flow(file_path):
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return

    logger.info(f"--- Step 1: PaddleOCR Extraction for {os.path.basename(file_path)} ---")
    ocr_result = perform_ocr(file_path)
    
    if not ocr_result["text"]:
        logger.error("OCR extraction failed (empty text)")
        return

    logger.info(f"Extracted {len(ocr_result['text'])} characters.")
    logger.info(f"Sample text snippet: {ocr_result['text'][:500]}...")

    logger.info("--- Step 2: Qwen3.5 Metadata & Relation Extraction ---")
    try:
        json_result = extract_metadata_and_relations(ocr_result)
        logger.info("Semantic extraction successful!")
        print("\n--- EXTRACTED METADATA & RELATIONS ---")
        print(json_result)
        print("---------------------------------------\n")
    except Exception as e:
        logger.error(f"Semantic extraction failed: {e}")

if __name__ == "__main__":
    # Use the sample file provided in the toolkit
    sample_file = "data/legal_test/Luat_50-2014-QH13_Luat Xay dung_18-6-2014.pdf"
    
    if len(sys.argv) > 1:
        sample_file = sys.argv[1]
        
    test_hybrid_flow(sample_file)
