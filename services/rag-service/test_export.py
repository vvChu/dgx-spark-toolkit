import json
import os
import sys

# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ingestion.exporter import DataExporter

def main():
    exporter = DataExporter("/app/exports")
    
    json_path = "/app/exports/json/UBND_DaNang-QNam_310_2025_QD-BXD.json"
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return
        
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    doc_id = data['doc_id']
    rel_path = data['original_path']
    meta = data['metadata']
    summary = data['summary']
    chunks = data['chunks']
    
    exporter.export(rel_path, doc_id, meta, summary, chunks)
    
if __name__ == "__main__":
    main()
