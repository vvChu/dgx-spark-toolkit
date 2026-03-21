#!/usr/bin/env python3
"""
Recover garbled table pages from JSON exports.

The exporter marks pages as garbled (⚠️) when their underlying text
has high repetition. This script reads the JSON exports, de-duplicates
the text, and patches the markdown files to replace ⚠️ placeholders
with recovered content.

Usage:
    python3 scripts/recover_table_pages.py               # Process all
    python3 scripts/recover_table_pages.py --dry-run      # Preview only
    python3 scripts/recover_table_pages.py --file FILE    # Single JSON file
"""
import os
import re
import sys
import json
import hashlib
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_EXPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "exports"
)


def dedup_chunk_text(text: str) -> str:
    """De-duplicate repeated blocks within a single chunk's text.
    
    Strategy: Split into paragraphs (double newline), hash each,
    keep only first occurrence. Then reassemble.
    """
    if not text or len(text) < 200:
        return text
    
    paragraphs = re.split(r'\n\n+', text)
    seen = set()
    unique = []
    
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            continue
        
        # Use hash of normalized text for comparison
        fp = hashlib.md5(stripped.encode('utf-8')).hexdigest()
        if fp in seen:
            continue
        seen.add(fp)
        unique.append(para)
    
    return '\n\n'.join(unique)


def clean_table_text(text: str) -> str:
    """Clean up a table chunk's text for markdown display.
    
    Removes OCR noise while preserving actual content.
    """
    # De-duplicate first
    text = dedup_chunk_text(text)
    
    # Remove standalone page numbers
    text = re.sub(r'^\s*\d{1,3}\s*$', '', text, flags=re.MULTILINE)
    
    # Remove isolated "QCVN XX:YYYY/XXX" headers if they appear as noise
    # (Keep them if they're part of a longer line)
    
    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def is_recoverable(text: str) -> bool:
    """Check if the de-duplicated text is actually usable content
    (not just garbled characters or noise).
    """
    cleaned = dedup_chunk_text(text)
    if not cleaned or len(cleaned) < 50:
        return False
    
    # Check if it has reasonable Vietnamese text
    # Count Vietnamese characters vs total
    lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
    if len(lines) < 2:
        return False
    
    # Check for garbage characters
    garbage_chars = set('ŧĖΧŲġşŷįďŕŝΈΊϐ')
    garbage_count = sum(1 for c in cleaned if c in garbage_chars)
    if garbage_count > 5:
        return False
    
    return True


def process_file(json_path: str, md_dir: str, dry_run: bool = False) -> dict:
    """Process a single JSON export file, recovering garbled pages in its markdown."""
    basename = os.path.splitext(os.path.basename(json_path))[0]
    md_path = os.path.join(md_dir, f"{basename}.md")
    
    if not os.path.exists(md_path):
        return {"file": basename, "recovered": 0, "skipped": 0}
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    with open(md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    
    # Find all ⚠️ placeholder pages
    placeholder_pattern = re.compile(
        r'> ⚠️ \*Trang (\d+): Bảng biểu gốc — dữ liệu OCR không thể chuyển đổi sang văn bản\*'
    )
    placeholder_pages = set(int(m.group(1)) for m in placeholder_pattern.finditer(md_content))
    
    if not placeholder_pages:
        return {"file": basename, "recovered": 0, "skipped": 0}
    
    # Build a map of page -> chunks from JSON
    page_chunks = {}
    for chunk in data.get('chunks', []):
        page = chunk.get('page', 0)
        if page in placeholder_pages and chunk.get('chunk_type') == 'parent':
            if page not in page_chunks:
                page_chunks[page] = []
            page_chunks[page].append(chunk)
    
    recovered = 0
    skipped = 0
    
    for page in sorted(placeholder_pages):
        chunks = page_chunks.get(page, [])
        if not chunks:
            skipped += 1
            continue
        
        # Combine all chunks for this page
        combined_text = '\n\n'.join(c.get('text', '') for c in chunks)
        
        if not is_recoverable(combined_text):
            skipped += 1
            continue
        
        # Clean and de-duplicate
        cleaned = clean_table_text(combined_text)
        
        if len(cleaned) < 30:
            skipped += 1
            continue
        
        # Replace the placeholder in markdown
        placeholder = f'> ⚠️ *Trang {page}: Bảng biểu gốc — dữ liệu OCR không thể chuyển đổi sang văn bản*'
        replacement = f'<!-- Trang {page} -->\n{cleaned}'
        
        if placeholder in md_content:
            md_content = md_content.replace(placeholder, replacement)
            recovered += 1
    
    if recovered > 0 and not dry_run:
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
    
    return {"file": basename, "recovered": recovered, "skipped": skipped, "total_placeholders": len(placeholder_pages)}


def main():
    parser = argparse.ArgumentParser(description="Recover garbled table pages from JSON exports")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--file", type=str, help="Process a single JSON file")
    parser.add_argument("--dir", type=str, default=DEFAULT_EXPORT_DIR, help="Export directory")
    args = parser.parse_args()
    
    json_dir = os.path.join(args.dir, "json")
    md_dir = os.path.join(args.dir, "markdown")
    
    if args.file:
        files = [args.file]
    else:
        if not os.path.isdir(json_dir):
            print(f"❌ JSON directory not found: {json_dir}")
            sys.exit(1)
        files = sorted([
            os.path.join(json_dir, f)
            for f in os.listdir(json_dir)
            if f.endswith('.json')
        ])
    
    mode = "DRY RUN" if args.dry_run else "RECOVERY"
    print(f"{'='*60}")
    print(f"  Table Page Recovery — {mode}")
    print(f"  JSON files: {len(files)}")
    print(f"{'='*60}\n")
    
    total_recovered = 0
    total_skipped = 0
    files_modified = 0
    
    for filepath in files:
        stats = process_file(filepath, md_dir, dry_run=args.dry_run)
        
        if stats.get("recovered", 0) > 0 or stats.get("skipped", 0) > 0:
            indicator = "🟢" if stats["recovered"] > 0 else "⚪"
            print(f"  {indicator} {stats['file']}: recovered={stats['recovered']}, skipped={stats['skipped']}, total_placeholders={stats.get('total_placeholders', 0)}")
            
            if stats["recovered"] > 0:
                files_modified += 1
            total_recovered += stats["recovered"]
            total_skipped += stats["skipped"]
    
    print(f"\n{'='*60}")
    print(f"  Summary")
    print(f"  Files scanned:     {len(files)}")
    print(f"  Files modified:    {files_modified}")
    print(f"  Pages recovered:   {total_recovered}")
    print(f"  Pages skipped:     {total_skipped} (truly garbled)")
    if args.dry_run:
        print(f"\n  ⚠️  DRY RUN — no files were modified.")
    else:
        print(f"\n  ✅ Recovery complete.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
