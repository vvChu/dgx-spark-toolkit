"""Re-chunk form-based documents using the updated FormFieldChunker.

This script reads existing JSON exports, groups parent chunks with their
children by page, reconstructs full page text, and re-chunks using the
updated chunking pipeline. It then updates both JSON and Markdown exports.

Usage:
    python3 scripts/rechunk_forms.py [--all | --file <json_filename>]

Only affects documents where FormFieldChunker activates (form-based docs
like NOXH templates). Other documents' chunks remain unchanged.
"""
import json
import os
import sys
import glob
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.chunking import DocumentChunker, FormFieldChunker
from ingestion.exporter import DataExporter


def rechunk_file(chunker: DocumentChunker, exporter: DataExporter, json_path: str):
    """Re-chunk a single file from its JSON dump using updated strategies."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    doc_id = data['doc_id']
    rel_path = data['original_path']
    meta = data['metadata']
    summary = data['summary']
    old_chunks = data['chunks']

    old_parents = sum(1 for c in old_chunks if c.get('chunk_type') == 'parent')
    old_children = sum(1 for c in old_chunks if c.get('chunk_type') == 'child')

    # Group parent chunks by page and reconstruct page text
    pages = {}
    for chunk in old_chunks:
        if chunk.get('chunk_type') != 'parent':
            continue
        page = chunk.get('page', 0)
        text = chunk.get('text', '')
        # Strip [doc_id] prefix for re-chunking
        text = re.sub(r'^\[.*?\]\s*', '', text)
        if page not in pages:
            pages[page] = []
        pages[page].append(text)

    # Re-chunk each page
    new_chunks = []
    form_chunker = FormFieldChunker()
    for page in sorted(pages.keys()):
        full_text = '\n'.join(pages[page])
        source = rel_path

        # Try FormFieldChunker first
        page_chunks = form_chunker.chunk(full_text, source, page, doc_id)

        if not page_chunks:
            # Fall back to full chunking pipeline
            page_chunks = chunker.chunk_document(full_text, source, page, doc_id)

        if not page_chunks:
            # Keep original parent chunk if nothing works
            for chunk in old_chunks:
                if chunk.get('page') == page and chunk.get('chunk_type') == 'parent':
                    new_chunks.append(chunk)
            continue

        # Assign chunk indices and doc metadata
        for idx, chunk in enumerate(page_chunks):
            chunk['doc_id'] = doc_id
            chunk['doc_number'] = meta.get('doc_number', '')
            chunk['chunk_index'] = len(new_chunks) + idx

        new_chunks.extend(page_chunks)

    new_parents = sum(1 for c in new_chunks if c.get('chunk_type') == 'parent')
    new_children = sum(1 for c in new_chunks if c.get('chunk_type') == 'child')
    new_ratio = new_children / max(new_parents, 1)
    old_ratio = old_children / max(old_parents, 1)

    improved = new_children > old_children

    if improved:
        # Update JSON
        data['chunks'] = new_chunks
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Re-export markdown
        exporter.export(rel_path, doc_id, meta, summary, new_chunks)

        print(f"  ✅ {os.path.basename(json_path)}")
        print(f"     P: {old_parents}→{new_parents}  C: {old_children}→{new_children}  ratio: {old_ratio:.2f}→{new_ratio:.2f}")
    else:
        print(f"  ⏭️  {os.path.basename(json_path)} — no improvement (already optimal)")
        print(f"     P: {old_parents}  C: {old_children}  ratio: {old_ratio:.2f}")


def main():
    export_dir = os.environ.get("EXPORT_DIR", "/app/exports")
    exporter = DataExporter(export_dir)
    chunker = DocumentChunker()

    json_dir = os.path.join(export_dir, "json")

    if len(sys.argv) > 1 and sys.argv[1] == "--file":
        filename = sys.argv[2]
        json_path = os.path.join(json_dir, filename)
        if not os.path.exists(json_path):
            print(f"File not found: {json_path}")
            sys.exit(1)
        rechunk_file(chunker, exporter, json_path)
    else:
        json_files = sorted(glob.glob(os.path.join(json_dir, "*.json")))
        print(f"Found {len(json_files)} JSON files to re-chunk")
        for jf in json_files:
            try:
                rechunk_file(chunker, exporter, jf)
            except Exception as e:
                print(f"  ❌ Failed: {os.path.basename(jf)}: {e}")

    # Print summary
    print("\n" + "=" * 60)
    total_p = 0
    total_c = 0
    for jf in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        with open(jf, 'r', encoding='utf-8') as f:
            data = json.load(f)
        p = sum(1 for c in data['chunks'] if c.get('chunk_type') == 'parent')
        c = sum(1 for c in data['chunks'] if c.get('chunk_type') == 'child')
        total_p += p
        total_c += c
    ratio = total_c / max(total_p, 1)
    print(f"  TOTAL: P={total_p} C={total_c} ratio={ratio:.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
