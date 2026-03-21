import os
import sys
import logging
from PIL import Image
import fitz

logging.basicConfig(level=logging.INFO)
sys.path.append('/app')
from ingestion.vision import SuryaExtractor

def test_layout_only():
    target_file = "/app/data/legal_docs_source/Linh vuc_BQP/Thong tu BQP ban hanh_2017-2022/TT104-2022-BQP_Sua doi-bs TT08-2017, TT137-2021_KDKTAT trong BQP.pdf"
    
    doc = fitz.open(target_file)
    page = doc[0]
    pix = page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("jpeg")
    
    import io
    img_pil = Image.open(io.BytesIO(img_bytes))
    
    extractor = SuryaExtractor()
    print("Testing extract_layout...")
    try:
        layout = extractor.extract_layout(img_pil)
        print(f"Extracted layout elements: {len(layout)}")
        for i, seg in enumerate(layout):
            print(f"[{i}] {getattr(seg, 'label', 'N/A')}: bbox={getattr(seg, 'bbox', 'MISSING_BBOX')}")
            
            # This is the line that might throw NoneType object is not subscriptable in vision.py
            seg_bbox = seg.bbox
            if seg_bbox is None:
                print(f"  -> BBOX IS NONE for element {i}!")
                # trigger the exact error
                print(seg_bbox[0])
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_layout_only()
