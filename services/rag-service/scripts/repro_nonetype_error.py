import os
import sys
import logging

logging.basicConfig(level=logging.INFO)

sys.path.append('/app')
from ingestion.pipeline import ProductionIngestor

def test_failed_file():
    target_file = "/app/data/legal_docs_source/Linh vuc_BQP/Thong tu BQP ban hanh_2017-2022/TT104-2022-BQP_Sua doi-bs TT08-2017, TT137-2021_KDKTAT trong BQP.pdf"
    print(f"Testing file: {target_file}")
    
    ingestor = ProductionIngestor()
    # We will invoke extract_pdf directly to see if it fails inside hybrid_extract_page
    try:
        chunks, failed = ingestor.extract_pdf(target_file)
        print(f"Extracted {len(chunks)} chunks, {len(failed)} failed pages.")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_failed_file()
