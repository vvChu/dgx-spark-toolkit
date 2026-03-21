#!/usr/bin/env python3
"""
Cleanup script for existing markdown exports.
Strips AI monologue leakage, <think> blocks, and reduces content duplication.

Usage:
    python scripts/cleanup_exports.py               # Process all exports
    python scripts/cleanup_exports.py --dry-run       # Preview changes only
    python scripts/cleanup_exports.py --file FILE     # Process single file
"""
import os
import re
import sys
import argparse
import hashlib

# Default export directory (Docker path)
DEFAULT_EXPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "exports", "markdown"
)


def strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> and <thought>...</thought> blocks."""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
    text = re.sub(r'</think>', '', text)
    text = re.sub(r'</thought>', '', text)
    return text


def strip_random_emojis(text: str) -> str:
    """Remove random emojis injected by Vision LLM.
    
    These emojis appear mid-sentence as OCR artifacts. We only strip
    emojis that are NOT used as intentional markers (⚠️ is kept).
    """
    # Common Vision LLM injected emojis (from audit)
    injected_emojis = [
        '\U0001f30b',  # 🌋
        '\U0001f525',  # 🔥
        '\U0001f4a5',  # 💥
        '\u26a1',      # ⚡
        '\U0001f30a',  # 🌊
        '\U0001f3af',  # 🎯
        '\U0001f680',  # 🚀
        '\U0001f389',  # 🎉
        '\U0001f3c6',  # 🏆
        '\U0001f31f',  # 🌟
        '\U0001f48e',  # 💎
        '\U0001f3ae',  # 🎮
        '\u2b50',      # ⭐
    ]
    for emoji in injected_emojis:
        text = text.replace(emoji, '')
    return text


def strip_digital_signature_lines(text: str) -> str:
    """Remove digital signature metadata that leaked into content.
    
    Pattern: 'Người ký: ... Email: ... Cơ quan: ... Thời gian ký: ...'
    These appear as single lines at page boundaries.
    """
    patterns = [
        r'^.*Người ký:.*Email:.*Cơ quan:.*Thời gian ký:.*$',
        r'^.*Người ký:\s*[A-ZĐÀ-Ỹ\s]+Email:.*$',
    ]
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        if any(re.match(p, line, re.IGNORECASE) for p in patterns):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def fix_ocr_typos(text: str) -> str:
    """Fix common Vietnamese OCR typos in legal documents."""
    typo_map = [
        ('Điểu', 'Điều'),   # Most common legal typo
        ('tỳ lệ', 'tỷ lệ'),
        ('Tỳ lệ', 'Tỷ lệ'),
        ('hổ sơ', 'hồ sơ'),
        ('Hổ sơ', 'Hồ sơ'),
        ('bố sung', 'bổ sung'),
        ('Bố sung', 'Bổ sung'),
        ('họp đồng', 'hợp đồng'),
        ('Họp đồng', 'Hợp đồng'),
        ('trưởng họp', 'trường hợp'),
        ('Trưởng họp', 'Trường hợp'),
    ]
    for wrong, correct in typo_map:
        if wrong in text:
            text = text.replace(wrong, correct)
    return text


def strip_ai_monologue_lines(text: str) -> str:
    """Remove lines containing AI reasoning/monologue patterns."""
    patterns = [
        # Vision LLM internal reasoning
        r'^\s*\*?\s*.*?(?:I will|I need to|I should|I have the|Let me|My plan)(?:\s+(?:use|look|replace|reconstruct|ensure|combine|respect|include|read|format|transcribe)).*$',
        r'^\s*.*?(?:The provided OCR text is|The OCR text provided|The prompt text provided).*$',
        r'^\s*.*?(?:The prompt asks to|The prompt says|One detail:).*$',
        r'^\s*.*?(?:Final check on the text|Okay, ready to generate|Ready to generate).*$',
        r'^\s*.*?(?:Let\'s assemble the final text|Let\'s refine the|Let\'s look at).*$',
        r'^\s*.*?(?:I should use the image|I need to look at the).*$',
        r'^\s*.*?(?:Wait, looking at|Wait, looking closely|Actually, looking at|Actually, for the).*$',
        r'^\s*.*?(?:looking closely at the|looking at the image|looking at the very top).*$',
        r'^\s*\*\*Plan:\*\*\s*$',
        r'^\s*\*\*Structure:.*?\*\*\s*$',
        r'^\s*\*\*OCR Text:\*\*.*$',
        r'^\s*\*\*Reconstruct the.*?\*\*.*$',
        # Analysis/thinking headers
        r'^\s*.*?(?:Analyze the Request|Analyze the Input Text|Evaluate the Input Text).*$',
        r'^\s*.*?(?:Thinking Process|Based on the visual content|Based on the visual input).*$',
        r'^\s*.*?(?:I see a document titled|Double-check the characters).*$',
        r'^\s*.*?(?:The user wants me to|Let\'s assume the user wants|As an AI).*$',
        # Broad AI reasoning lines (mid-paragraph monologue)
        r'^.*The OCR draft (?:had|provided|is very).*$',
        r'^.*I need to (?:replace|reconstruct|make sure|include|combine).*$',
        r'^.*I will (?:place|put|combine|include|replace|reconstruct|ensure|respect).*$',
        r'^.*I should (?:include|use|look).*$',
        r'^.*The first table in the image is actually.*$',
        r'^.*This applies to the whole list.*$',
        r'^.*In Markdown, I can\'t merge cells.*$',
        r'^.*Standard practice for Markdown tables.*$',
        # Starred analysis bullets that are AI reasoning, not document content
        r'^\s*\*\s+\*\*(?:Note|Reconstruct|Plan|Structure|OCR Text):?\*\*.*$',
    ]
    
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        should_remove = False
        for pattern in patterns:
            if re.match(pattern, line, re.IGNORECASE):
                should_remove = True
                break
        if not should_remove:
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def dedup_content_blocks(text: str) -> str:
    """Remove duplicate multi-line blocks in the content section.
    
    Strategy: Split by page markers (<!-- Trang N -->) and dedup within
    the Content section by comparing normalized block fingerprints.
    """
    # Only dedup within the ## Content section
    content_marker = "## Content"
    idx = text.find(content_marker)
    if idx == -1:
        return text
    
    header = text[:idx + len(content_marker)]
    body = text[idx + len(content_marker):]
    
    # Split body into blocks by double newlines
    blocks = re.split(r'\n\n+', body)
    
    seen_hashes = set()
    unique_blocks = []
    dedup_count = 0
    
    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue
        
        # Don't dedup page markers, headings, or warning placeholders  
        if (stripped.startswith('<!-- Trang') or 
            stripped.startswith('### ') or 
            stripped.startswith('## ') or
            '⚠️' in stripped):
            unique_blocks.append(block)
            continue
        
        # Hash the normalized content
        block_hash = hashlib.md5(stripped.encode('utf-8')).hexdigest()
        if block_hash in seen_hashes:
            dedup_count += 1
            continue
        
        seen_hashes.add(block_hash)
        unique_blocks.append(block)
    
    result = header + '\n' + '\n\n'.join(unique_blocks)
    
    # Clean up excessive blank lines (>2 consecutive)
    result = re.sub(r'\n{4,}', '\n\n\n', result)
    
    return result


def clean_summary_section(text: str) -> str:
    """Clean AI-structured analysis from the summary section.
    
    Strips markdown formatting (**, ##, bullets) and AI analysis headers
    that shouldn't appear in a plain-text summary.
    """
    # Only process the summary section
    summary_start = text.find('## Summary\n')
    content_start = text.find('\n## Content')
    if summary_start == -1 or content_start == -1:
        return text
    
    header = text[:summary_start + len('## Summary\n')]
    summary = text[summary_start + len('## Summary\n'):content_start]
    rest = text[content_start:]
    
    # Strip AI analysis markers from summary
    summary = re.sub(r'\*\*(?:Header|Content Snippets?|Key Points?|Note|Overview|Structure|Document Type|Issuing Authority|Recipients?|Sender|Date):?\*\*:?\s*', '', summary)
    # Strip markdown bold
    summary = re.sub(r'\*\*(.*?)\*\*', r'\1', summary)
    # Strip bullet markers (* / - / +) at start of lines
    summary = re.sub(r'^\s*[*\-+]\s+', '', summary, flags=re.MULTILINE)
    # Strip indented bullets
    summary = re.sub(r'^\s{2,}[*\-+]\s+', '', summary, flags=re.MULTILINE)
    # Clean up excessive whitespace
    summary = re.sub(r'\n{3,}', '\n\n', summary)
    
    return header + summary + rest


def strip_empty_pages(text: str) -> str:
    """Remove empty page markers (<!-- Trang N --> followed by nothing)."""
    # Remove <!-- Trang N --> that's followed immediately by another page marker or heading
    text = re.sub(r'<!-- Trang \d+ -->\s*\n\s*(?=<!-- Trang|\n###|\n## |\Z)', '', text)
    return text


def cleanup_file(filepath: str, dry_run: bool = False) -> dict:
    """Clean a single markdown file. Returns stats dict."""
    with open(filepath, 'r', encoding='utf-8') as f:
        original = f.read()
    
    original_lines = len(original.split('\n'))
    
    # Step 1: Strip <think> blocks
    cleaned = strip_think_blocks(original)
    
    # Step 2: Strip AI monologue lines
    cleaned = strip_ai_monologue_lines(cleaned)
    
    # Step 3: Dedup content blocks
    cleaned = dedup_content_blocks(cleaned)
    
    # Step 4: OCR artifact cleanup
    cleaned = strip_random_emojis(cleaned)
    cleaned = strip_digital_signature_lines(cleaned)
    cleaned = fix_ocr_typos(cleaned)
    
    # Step 5: Summary section cleanup (strip AI analysis markers)
    cleaned = clean_summary_section(cleaned)
    
    # Step 6: Remove empty page markers
    cleaned = strip_empty_pages(cleaned)
    
    # Step 7: Clean up excessive blank lines
    cleaned = re.sub(r'\n{4,}', '\n\n\n', cleaned)
    cleaned = cleaned.rstrip() + '\n'
    
    cleaned_lines = len(cleaned.split('\n'))
    removed = original_lines - cleaned_lines
    
    stats = {
        "file": os.path.basename(filepath),
        "original_lines": original_lines,
        "cleaned_lines": cleaned_lines,
        "removed_lines": removed,
        "changed": original != cleaned,
        "had_think_tags": '</think>' in original or '<think>' in original,
    }
    
    if not dry_run and stats["changed"]:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(cleaned)
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Cleanup RAG markdown exports")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--file", type=str, help="Process a single file")
    parser.add_argument("--dir", type=str, default=DEFAULT_EXPORT_DIR, help="Export directory")
    args = parser.parse_args()
    
    if args.file:
        files = [args.file]
    else:
        if not os.path.isdir(args.dir):
            print(f"❌ Directory not found: {args.dir}")
            sys.exit(1)
        files = sorted([
            os.path.join(args.dir, f)
            for f in os.listdir(args.dir)
            if f.endswith('.md')
        ])
    
    if not files:
        print("No markdown files found.")
        sys.exit(0)
    
    mode = "DRY RUN" if args.dry_run else "CLEANUP"
    print(f"{'='*60}")
    print(f"  Markdown Export Cleanup — {mode}")
    print(f"  Files: {len(files)}")
    print(f"{'='*60}\n")
    
    total_removed = 0
    files_changed = 0
    files_with_think = 0
    
    for filepath in files:
        stats = cleanup_file(filepath, dry_run=args.dry_run)
        
        if stats["had_think_tags"]:
            files_with_think += 1
        
        if stats["changed"]:
            files_changed += 1
            total_removed += stats["removed_lines"]
            indicator = "🔴" if stats["had_think_tags"] else "🟡"
            print(f"  {indicator} {stats['file']}: {stats['original_lines']} → {stats['cleaned_lines']} lines (-{stats['removed_lines']})")
        
    print(f"\n{'='*60}")
    print(f"  Summary")
    print(f"  Files scanned:     {len(files)}")
    print(f"  Files changed:     {files_changed}")
    print(f"  Files with <think>: {files_with_think}")
    print(f"  Total lines removed: {total_removed}")
    if args.dry_run:
        print(f"\n  ⚠️  DRY RUN — no files were modified. Run without --dry-run to apply.")
    else:
        print(f"\n  ✅ Cleanup complete.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
