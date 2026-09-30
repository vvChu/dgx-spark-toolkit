#!/usr/bin/env python3
"""Script to inspect and parse blocks in sua_doi_1_2023_qcvn_06_2022_bxd.md."""

import re
from pathlib import Path

SD1_FILE = Path("/home/vvc/ccba/ccba-legal-knowledge/legal_docs/02_qcvn/qcvn_06_2022_bxd/sources/sua_doi_1_2023_qcvn_06_2022_bxd.md")

def parse_sd1():
    text = SD1_FILE.read_text(encoding="utf-8")
    
    # Split by `#### <a id="sd1-`
    pattern = r'(####\s*<a\s+id="(sd1-[^"]+)"[^>]*></a>([^\n]+))'
    splits = list(re.finditer(pattern, text))
    
    print(f"Total sd1 sections found: {len(splits)}")
    
    sections = []
    for i, match in enumerate(splits):
        full_heading = match.group(1)
        anchor_id = match.group(2)
        heading_text = match.group(3).strip()
        
        start_pos = match.end()
        end_pos = splits[i+1].start() if i + 1 < len(splits) else len(text)
        
        body = text[start_pos:end_pos].strip()
        
        sections.append({
            "anchor_id": anchor_id,
            "target_anchor": anchor_id.replace("sd1-", ""),
            "heading": heading_text,
            "body": body
        })
        
    return sections

if __name__ == "__main__":
    sections = parse_sd1()
    print(f"Parsed {len(sections)} sections successfully.")
    for s in sections[:5]:
        print(f"--- Anchor: {s['anchor_id']} -> Target: {s['target_anchor']} ---")
        print(f"Heading: {s['heading']}")
        print(f"Body preview: {s['body'][:150]}...")
