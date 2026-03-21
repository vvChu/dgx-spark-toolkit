import os
import sys

# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ingestion.pipeline import IngestionPipeline

def main():
    pipe = IngestionPipeline('/app/source_docs')
    sm = pipe.state_manager
    filepath = '/app/source_docs/UBND DaNang-QNam/20250325_QD310-BXD_Phe duyetQHptvungdat-nuoccangbienQNgd21-30-50.pdf'
    rel_path = os.path.relpath(filepath, '/app/source_docs')
    
    # 1. Clear Postgres state
    try:
        with sm.engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(text("DELETE FROM ingestion_state WHERE file_path = :path"), {"path": rel_path})
            print(f"Deleted {rel_path} from state DB.")
    except Exception as e:
        print(f"Error accessing DB: {e}")
        
    # 2. Process File
    print(f"Re-ingesting {rel_path}...")
    pipe.process_file(filepath)
    print("Done re-ingesting.")
    
if __name__ == "__main__":
    main()
