import sys
import logging
import os

from ingestion.pipeline import ProductionIngestor

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_single.py <file_path>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    
    # 1. Reset its status in Postgres so it doesn't get skipped by orchestrator checking cache
    try:
        from ingestion.state_manager import PostgresStateManager
        manager = PostgresStateManager()
        rel_path = os.path.relpath(file_path, "/app/data/legal_docs_source")
        manager._run_query('DELETE FROM ingestion_state WHERE file_path = %s', (rel_path,))
        print(f"Postgres state reset for {rel_path}")
    except Exception as e:
        print(f"Could not reset postgres state: {e}")

    # 2. Process the file
    print(f"Force processing file: {file_path}")
    ingestor = ProductionIngestor()
    
    # Bypass queue, just run it directly
    ingestor.safe_process(file_path)
    print("Done processing!")
