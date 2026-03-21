#!/usr/bin/env python3
"""
Re-generate Vietnamese summaries for files that have English summaries.

Reads JSON exports, identifies files with English summaries, calls the
local LLM to generate proper Vietnamese summaries, and updates both
JSON and Markdown exports.

Usage:
    python3 scripts/regen_summaries.py               # Process all
    python3 scripts/regen_summaries.py --dry-run      # List files only
    python3 scripts/regen_summaries.py --limit 5      # Process first 5
"""
import os
import re
import sys
import json
import time
import argparse
import httpx

DEFAULT_EXPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "exports"
)

# LLM API config — accessible from host via ai-gateway exposed port
API_URL = os.environ.get("VLLM_API_BASE", "http://localhost:8090/v1") + "/chat/completions"
API_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
MODEL = os.environ.get("VLLM_MODEL", "rag-core")

_SUMMARY_SYSTEM = """Bạn là chuyên gia tóm tắt văn bản pháp luật Việt Nam.
CHỈ viết bằng tiếng Việt. KHÔNG BAO GIỜ viết tiếng Anh.
Hãy tạo bản tóm tắt ngắn gọn, rõ ràng, giữ nguyên ý chính của văn bản.

QUY TẮC BẮT BUỘC:
- Tối đa 1500 ký tự
- KHÔNG giải thích quá trình suy nghĩ
- KHÔNG viết "Internal Monologue", "Drafting", "Strategy"
- KHÔNG đánh số bước phân tích
- KHÔNG dùng markdown
- Chỉ xuất nội dung tóm tắt thuần túy"""


def is_english_summary(summary: str) -> bool:
    """Check if summary is predominantly in English."""
    eng_words = len(re.findall(
        r'\b(?:the|this|that|is|are|was|which|appears|based|document|article|'
        r'regarding|content|text|following|decision|regulation|law|chapter|'
        r'section|point|however|therefore|according|pertaining|related|'
        r'address|establish|implement|provide|specify|include|require)\b',
        summary, re.IGNORECASE
    ))
    return eng_words > 5


def generate_summary(text: str, client: httpx.Client) -> str:
    """Call LLM to generate Vietnamese summary."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {"role": "user", "content": f"Tóm tắt văn bản pháp luật sau bằng tiếng Việt:\n\n{text[:15000]}"}
        ],
        "max_tokens": 400,
        "temperature": 0.1,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": False}
        }
    }
    
    resp = client.post(
        API_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=payload,
        timeout=120
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    
    # Strip any <think> blocks that might still leak through
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    content = re.sub(r'</think>', '', content)
    # Strip markdown formatting
    content = re.sub(r'\*\*(.*?)\*\*', r'\1', content)
    
    return content.strip()


def process_file(json_path: str, md_dir: str, client: httpx.Client, dry_run: bool = False) -> dict:
    """Process a single file: check if English, regenerate if needed."""
    basename = os.path.splitext(os.path.basename(json_path))[0]
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    summary = data.get("summary", "")
    
    if not is_english_summary(summary):
        return {"file": basename, "action": "skip", "reason": "already_vietnamese"}
    
    if dry_run:
        return {"file": basename, "action": "would_regen", "summary_preview": summary[:100]}
    
    # Build text from first 5 chunks
    chunks_text = "\n".join(c.get("text", "") for c in data.get("chunks", [])[:5])
    if not chunks_text.strip():
        return {"file": basename, "action": "skip", "reason": "no_chunks"}
    
    try:
        new_summary = generate_summary(chunks_text, client)
        
        if not new_summary or len(new_summary) < 30:
            return {"file": basename, "action": "failed", "reason": "empty_result"}
        
        if is_english_summary(new_summary):
            return {"file": basename, "action": "failed", "reason": "still_english"}
        
        # Update JSON export
        data["summary"] = new_summary
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Update Markdown export
        md_path = os.path.join(md_dir, f"{basename}.md")
        if os.path.exists(md_path):
            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            # Replace summary section
            md_content = re.sub(
                r'(## Summary\n).*?(\n## Content)',
                rf'\1{new_summary}\n\2',
                md_content,
                flags=re.DOTALL
            )
            
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
        
        return {"file": basename, "action": "regenerated", "new_summary": new_summary[:100]}
    
    except Exception as e:
        return {"file": basename, "action": "error", "reason": str(e)[:100]}


def main():
    parser = argparse.ArgumentParser(description="Re-generate English summaries in Vietnamese")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max files to process (0=all)")
    parser.add_argument("--dir", type=str, default=DEFAULT_EXPORT_DIR)
    args = parser.parse_args()
    
    json_dir = os.path.join(args.dir, "json")
    md_dir = os.path.join(args.dir, "markdown")
    
    files = sorted([
        os.path.join(json_dir, f)
        for f in os.listdir(json_dir)
        if f.endswith('.json')
    ])
    
    mode = "DRY RUN" if args.dry_run else "REGENERATION"
    print(f"{'='*60}")
    print(f"  Summary Re-generation — {mode}")
    print(f"  Files: {len(files)}")
    print(f"{'='*60}\n")
    
    client = httpx.Client(timeout=120) if not args.dry_run else None
    regenerated = 0
    skipped = 0
    failed = 0
    processed = 0
    
    for filepath in files:
        stats = process_file(filepath, md_dir, client, dry_run=args.dry_run)
        
        if stats["action"] == "skip":
            skipped += 1
            continue
        
        if stats["action"] == "would_regen":
            regenerated += 1
            print(f"  🔵 {stats['file']}: {stats['summary_preview']}...")
            continue
        
        if stats["action"] == "regenerated":
            regenerated += 1
            processed += 1
            print(f"  🟢 {stats['file']}: {stats['new_summary']}...")
            time.sleep(0.5)  # Rate limiting
        elif stats["action"] in ("failed", "error"):
            failed += 1
            print(f"  🔴 {stats['file']}: {stats.get('reason', 'unknown')}")
        
        if args.limit and processed >= args.limit:
            print(f"\n  ⏸️  Limit reached ({args.limit})")
            break
    
    if client:
        client.close()
    
    print(f"\n{'='*60}")
    print(f"  Summary")
    print(f"  Regenerated:  {regenerated}")
    print(f"  Skipped:      {skipped} (already Vietnamese)")
    print(f"  Failed:       {failed}")
    if args.dry_run:
        print(f"\n  ⚠️  DRY RUN — no changes made.")
    else:
        print(f"\n  ✅ Done.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
