"""Re-export script: reads existing JSON exports and regenerates Markdown
using the updated exporter with text_normalizer integration.

Usage:
    python3 scripts/reexport_markdown.py [--all | --file <json_filename>]
"""
import json
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.exporter import DataExporter


def reexport_file(exporter: DataExporter, json_path: str):
    """Re-export a single file from its JSON dump."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    doc_id = data['doc_id']
    rel_path = data['original_path']
    meta = data['metadata']
    summary = data['summary']
    chunks = data['chunks']

    exporter.export(rel_path, doc_id, meta, summary, chunks)
    print(f"  ✅ Re-exported: {doc_id}")


def main():
    export_dir = os.environ.get("EXPORT_DIR", "/app/exports")
    exporter = DataExporter(export_dir)

    json_dir = os.path.join(export_dir, "json")

    if len(sys.argv) > 1 and sys.argv[1] == "--file":
        # Re-export a single file
        filename = sys.argv[2]
        json_path = os.path.join(json_dir, filename)
        if not os.path.exists(json_path):
            print(f"File not found: {json_path}")
            sys.exit(1)
        reexport_file(exporter, json_path)
    else:
        # Re-export all
        json_files = sorted(glob.glob(os.path.join(json_dir, "*.json")))
        print(f"Found {len(json_files)} JSON files to re-export")
        for jf in json_files:
            try:
                reexport_file(exporter, jf)
            except Exception as e:
                print(f"  ❌ Failed: {os.path.basename(jf)}: {e}")

    print("\nDone!")


if __name__ == "__main__":
    main()
