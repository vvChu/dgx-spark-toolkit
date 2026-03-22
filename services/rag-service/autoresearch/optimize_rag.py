#!/usr/bin/env python3
"""Autoresearch — Mutable RAG Pipeline.

████████████████████████████████████████████████████████████████████████
██  THIS IS THE FILE THE AI AGENT MODIFIES.                          ██
██  Everything is fair game: extraction, cleaning, chunking, export. ██
████████████████████████████████████████████████████████████████████████

Usage:
    python3 optimize_rag.py                    # Process all sample PDFs
    python3 optimize_rag.py /path/to/file.pdf  # Process single PDF
"""

import os
import re
import sys
import json
import hashlib
import logging
from pathlib import Path

# Add rag-service to path for imports
RAG_SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAG_SERVICE_DIR)

from ingestion.chunking import DocumentChunker
from ingestion.text_normalizer import normalize_chunk_text
from ingestion.cleaning_utils import strip_illegal_chars

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────
EXPORT_DIR = "/home/vvc/Public/exports"
EXPORT_JSON_DIR = os.path.join(EXPORT_DIR, "json")
EXPORT_MD_DIR = os.path.join(EXPORT_DIR, "markdown")

# Source directories
PDF_SOURCE_DIRS = [
    "/home/vvc/Public/QCVN",
    "/home/vvc/Public/VB phap quy",
]

# Ensure dirs exist
os.makedirs(EXPORT_JSON_DIR, exist_ok=True)
os.makedirs(EXPORT_MD_DIR, exist_ok=True)


# ═════════════════════════════════════════════════════════════════════════
# STAGE 1: TEXT EXTRACTION
# ═════════════════════════════════════════════════════════════════════════

def extract_text(pdf_path: str) -> list[dict]:
    """Extract text from PDF, returning list of page dicts.
    
    Each page dict: {"page": int, "text": str, "layout": list}
    
    Currently uses pdfplumber for digital PDFs.
    AI Agent: feel free to switch to Cloud Vision, Surya, Docling, etc.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed. Run: pip install pdfplumber")
        return []
    
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                
                # Extract tables as markdown
                tables = page.extract_tables()
                table_md = ""
                for table in tables:
                    if table and len(table) > 1:
                        # Convert table to markdown
                        headers = table[0]
                        header_row = "| " + " | ".join(str(h or "") for h in headers) + " |"
                        sep_row = "| " + " | ".join("---" for _ in headers) + " |"
                        data_rows = []
                        for row in table[1:]:
                            data_rows.append("| " + " | ".join(str(c or "") for c in row) + " |")
                        table_md += "\n" + header_row + "\n" + sep_row + "\n" + "\n".join(data_rows) + "\n"
                
                if table_md:
                    text = text + "\n\n" + table_md
                
                pages.append({
                    "page": i + 1,
                    "text": text,
                    "layout": [],  # No layout info from pdfplumber basic mode
                })
    except Exception as e:
        logger.error(f"Failed to extract {pdf_path}: {e}")
    
    return pages


# ═════════════════════════════════════════════════════════════════════════
# STAGE 2: TEXT CLEANING
# ═════════════════════════════════════════════════════════════════════════

# Vietnamese boilerplate patterns
_BOILERPLATE_PATTERNS = [
    re.compile(r"CỘNG\s+HÒA\s+XÃ\s+HỘI\s+CHỦ\s+NGHĨA\s+VIỆT\s+NAM", re.IGNORECASE),
    re.compile(r"Độc\s+lập\s*[-–—]\s*Tự\s+do\s*[-–—]\s*Hạnh\s+phúc", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*Nơi\s+nhận\s*:.*?(?=\n\s*(?:[A-ZĐ]|\d)|\Z)", re.DOTALL),
    re.compile(r"(?:^|\n).*CỔNG\s+THÔNG\s+TIN\s+ĐIỆN\s+TỬ.*(?:\n|$)", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*-?\s*Lưu\s*:\s*VT[,;]?\s*[A-Z]*\.?\s*(?:\n|$)", re.IGNORECASE),
]

# AI monologue patterns
_AI_PATTERNS = [
    re.compile(r"(?i)(?:^|\n)\s*Dưới đây là[^.]*[.:]?\s*\n"),
    re.compile(r"(?i)(?:^|\n)\s*Tôi xin[^.]*[.:]?\s*\n"),
    re.compile(r"(?i)(?:^|\n)\s*Xin lỗi[^.]*[.!]?\s*\n"),
    re.compile(r"(?i)(?:^|\n)\s*Certainly[,!]?\s+(?:here|I|let)[^\n]*\n"),
    re.compile(r"(?i)(?:^|\n)\s*Here is[^\n]*:\s*\n"),
    re.compile(r"(?i)(?:^|\n)\s*As an AI[^\n]*\n"),
]


def clean_text(text: str) -> str:
    """Clean extracted text: strip boilerplate, noise, AI monologue.
    
    AI Agent: tune these patterns to maximize score.
    """
    if not text:
        return text
    
    original_len = len(text)
    
    # Strip AI monologue
    for pat in _AI_PATTERNS:
        text = pat.sub("\n", text)
    
    # Safety: never strip more than 30% of content
    if len(text) < original_len * 0.7:
        return text.strip()
    
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    return text.strip()


def strip_boilerplate_from_content(text: str) -> str:
    """Strip government header boilerplate from content section only."""
    for pat in _BOILERPLATE_PATTERNS:
        text = pat.sub("\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ═════════════════════════════════════════════════════════════════════════
# STAGE 3: METADATA EXTRACTION
# ═════════════════════════════════════════════════════════════════════════

# Standard doc number patterns
_QCVN_RE = re.compile(r"QCVN[_\s-]?(\d+)[_\s-](\d{4})[_\s-]([A-Z]+)")
_DOC_NUM_RE = re.compile(r"Số\s*:\s*([\d/]+\s*[A-ZĐ]{2,}[-/][A-ZĐ]+)", re.IGNORECASE)


def extract_metadata(text: str, pdf_path: str) -> dict:
    """Extract document metadata from text and filename.
    
    AI Agent: improve pattern matching to fill more fields.
    """
    meta = {
        "date": "",
        "type": "",
        "authority": "",
        "doc_number": "",
        "validity_status": "current",
        "legal_level": "",
        "source_category": "",
    }
    
    basename = os.path.basename(pdf_path).replace(".pdf", "").replace(".PDF", "")
    
    # Try QCVN pattern from filename
    m = _QCVN_RE.search(basename)
    if m:
        meta["doc_number"] = f"QCVN {m.group(1)}:{m.group(2)}/{m.group(3)}"
        meta["type"] = "QCVN"
        meta["source_category"] = "QCVN"
    
    # Try doc number from text
    if not meta["doc_number"]:
        m = _DOC_NUM_RE.search(text[:2000])
        if m:
            meta["doc_number"] = m.group(1).strip()
    
    # Date extraction
    date_m = re.search(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", text[:3000])
    if date_m:
        meta["date"] = f"{date_m.group(3)}-{date_m.group(2).zfill(2)}-{date_m.group(1).zfill(2)}"
    
    # Authority from path
    if "/QCVN/" in pdf_path:
        meta["source_category"] = "QCVN"
    elif "/VB phap quy/" in pdf_path:
        meta["source_category"] = "VB_PHAP_QUY"
    
    return meta


def generate_doc_id(pdf_path: str, meta: dict) -> str:
    """Generate a unique doc_id from metadata and path."""
    doc_num = meta.get("doc_number", "")
    if doc_num:
        # Normalize: QCVN 01:2021/BXD → QCVN/01_2021_BXD
        safe_id = doc_num.replace(":", "_").replace("/", "_").replace(" ", "_")
        cat = meta.get("source_category", "LEGAL")
        return f"{cat}/{safe_id}"
    
    # Fallback to filename hash
    basename = Path(pdf_path).stem
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", basename)
    return f"UNKNOWN/{safe_name}"


# ═════════════════════════════════════════════════════════════════════════
# STAGE 4: DOCUMENT CHUNKING
# ═════════════════════════════════════════════════════════════════════════

def chunk_document(pages: list[dict], doc_id: str, source: str) -> list[dict]:
    """Chunk extracted pages into parent/child chunks.
    
    [EXP-1] Merge all pages into single document text before chunking.
    This allows VietLawArticleChunker to detect cross-page Điều patterns.
    Then force child generation for parent chunks > 300 chars.
    """
    from ingestion.chunking import (
        VietLawArticleChunker, VietLawSectionChunker,
        GenericFallbackChunker, _split_into_children, _is_noise_chunk
    )
    
    # Merge all page texts into one document
    full_text = "\n\n".join(
        p["text"].strip() for p in pages if p.get("text", "").strip()
    )
    
    if not full_text or len(full_text.strip()) < 30:
        return []
    
    # Try chunking strategies in order on the FULL document text
    all_chunks = []
    
    # Strategy 1: Try VietLawArticleChunker on full text
    law_chunker = VietLawArticleChunker()
    chunks = law_chunker.chunk(full_text, source, 1, doc_id)
    
    if not chunks:
        # Strategy 2: Try VietLawSectionChunker
        sec_chunker = VietLawSectionChunker()
        chunks = sec_chunker.chunk(full_text, source, 1, doc_id)
    
    if not chunks:
        # Strategy 3: Generic fallback
        fb_chunker = GenericFallbackChunker()
        chunks = fb_chunker.chunk(full_text, source, 1, doc_id)
    
    # Filter noise
    chunks = [c for c in chunks if not _is_noise_chunk(c.get("text", ""))]
    
    # Force child generation for parent chunks without children
    parent_ids_with_children = set()
    for c in chunks:
        if c.get("chunk_type") == "child":
            parent_ids_with_children.add(c.get("parent_id"))
    
    extra_children = []
    for c in chunks:
        if (c.get("chunk_type") == "parent"
            and c.get("parent_id") not in parent_ids_with_children
            and len(c.get("text", "")) > 300):
            children = _split_into_children(
                c["text"], doc_id, source, c.get("page", 1),
                c["parent_id"], c.get("hierarchy_path", ""),
                c.get("bbox", [0, 0, 1000, 1000]),
                min_child_length=200,
            )
            extra_children.extend(children)
    
    chunks.extend(extra_children)
    
    return chunks if chunks else []


# ═════════════════════════════════════════════════════════════════════════
# STAGE 5: SUMMARY GENERATION
# ═════════════════════════════════════════════════════════════════════════

def generate_summary(pages: list[dict], meta: dict) -> str:
    """Generate a document summary from first pages.
    
    AI Agent: can call LLM here, or use extractive methods.
    """
    # Simple extractive summary from first 2 pages
    all_text = " ".join(p["text"] for p in pages[:2] if p["text"])
    
    # Find the first substantive sentence
    sentences = re.split(r'[.!?]\s+', all_text[:2000])
    summary_parts = []
    for s in sentences:
        s = s.strip()
        if len(s) > 50 and not any(bp.search(s) for bp in _BOILERPLATE_PATTERNS):
            summary_parts.append(s)
            if len(" ".join(summary_parts)) > 200:
                break
    
    summary = ". ".join(summary_parts)
    if not summary or len(summary) < 50:
        summary = f"Tài liệu {meta.get('doc_number', 'pháp luật Việt Nam')}. " + all_text[:200].strip()
    
    return summary[:500]


# ═════════════════════════════════════════════════════════════════════════
# STAGE 6: EXPORT (JSON + Markdown)
# ═════════════════════════════════════════════════════════════════════════

def export_document(doc_id: str, rel_path: str, meta: dict,
                    summary: str, chunks: list[dict]):
    """Export processed document as JSON and Markdown.
    
    Both files go to /home/vvc/Public/exports/{json,markdown}/
    """
    safe_filename = doc_id.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
    
    # Enrich chunks with doc-level fields
    for i, chunk in enumerate(chunks):
        chunk["doc_id"] = doc_id
        chunk["doc_number"] = meta.get("doc_number", "")
        chunk["chunk_id"] = f"{doc_id}:chunk_{i}"
    
    # ── JSON Export ──
    json_path = os.path.join(EXPORT_JSON_DIR, f"{safe_filename}.json")
    json_data = {
        "doc_id": doc_id,
        "original_path": rel_path,
        "metadata": meta,
        "summary": summary,
        "chunks": chunks,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    # ── Markdown Export ──
    md_path = os.path.join(EXPORT_MD_DIR, f"{safe_filename}.md")
    md_content = _generate_markdown(doc_id, rel_path, meta, summary, chunks)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    logger.info(f"  Exported {doc_id} → {safe_filename}.json + .md")


def _generate_markdown(doc_id: str, rel_path: str, meta: dict,
                       summary: str, chunks: list[dict]) -> str:
    """Generate formatted markdown from document data.
    
    AI Agent: customize the markdown structure, heading logic, etc.
    """
    lines = [f"# Document: {doc_id}\n"]
    
    # Metadata
    lines.append("## Metadata")
    meta_display = [
        ("date", "Date"), ("type", "Type"), ("authority", "Authority"),
        ("doc_number", "Doc Number"), ("validity_status", "Validity Status"),
        ("legal_level", "Legal Level"),
    ]
    for key, label in meta_display:
        val = meta.get(key, "")
        if val and val not in ("unknown", "UNKNOWN", ""):
            lines.append(f"- **{label}:** {val}")
    lines.append(f"- **Original Path:** {rel_path}\n")
    
    # Summary
    lines.append("## Summary")
    lines.append(f"{summary}\n")
    
    # Content from parent chunks
    lines.append("## Content")
    parent_chunks = sorted(
        [c for c in chunks if c.get("chunk_type") == "parent"],
        key=lambda x: (x.get("page", 0), 0),
    )
    if not parent_chunks:
        parent_chunks = chunks
    
    # Dedup
    seen = set()
    for chunk in parent_chunks:
        text = chunk.get("text", "")
        fp = hash(text.strip())
        if fp in seen:
            continue
        seen.add(fp)
        
        # Strip [doc_id] prefix from display
        display_text = re.sub(r"^\[.*?\]\s*", "", text)
        # Strip context prefix
        display_text = re.sub(r"^\[.*?\]\s*:::\s*", "", display_text)
        # Strip boilerplate from content
        display_text = strip_boilerplate_from_content(display_text)
        
        if not display_text.strip():
            continue
        
        # Extract heading from hierarchy_path
        h_path = chunk.get("hierarchy_path", "")
        heading = _extract_heading(h_path, doc_id)
        if heading:
            lines.append(f"\n### {heading}")
        
        lines.append(display_text)
        lines.append("")
    
    return "\n".join(lines)


def _extract_heading(hierarchy_path: str, doc_id: str) -> str | None:
    """Extract a heading from hierarchy_path."""
    if not hierarchy_path:
        return None
    parts = re.split(r"\s*(?:->|>)\s*", hierarchy_path)
    if not parts:
        return None
    last = parts[-1].strip().strip("[]")
    if not last or last == doc_id or last.lower() == "header":
        return None
    legal_match = re.match(
        r"((?:[ĐÐ]iều\s+\d+\.?\s*[^\n]{0,60})"
        r"|(?:(?:Chương|CHƯƠNG)\s+[IVX\d]+[^.]*)"
        r"|(?:(?:Mục|MỤC)\s+[IVX\d]+[^.]*))",
        last
    )
    if legal_match:
        heading = legal_match.group(1).strip()
        return heading[:80] if len(heading) > 80 else heading
    return None


# ═════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═════════════════════════════════════════════════════════════════════════

def run_pipeline(pdf_path: str) -> bool:
    """Run the full pipeline on a single PDF file.
    
    Returns True on success, False on failure.
    """
    logger.info(f"Processing: {pdf_path}")
    
    # 1. Extract
    pages = extract_text(pdf_path)
    if not pages:
        logger.warning(f"  No text extracted from {pdf_path}")
        return False
    
    # 2. Clean
    for page in pages:
        page["text"] = clean_text(page["text"])
    
    # 3. Metadata
    all_text = "\n".join(p["text"] for p in pages if p["text"])
    meta = extract_metadata(all_text, pdf_path)
    doc_id = generate_doc_id(pdf_path, meta)
    
    # 4. Chunk
    rel_path = pdf_path
    for src_dir in PDF_SOURCE_DIRS:
        if pdf_path.startswith(src_dir):
            rel_path = os.path.relpath(pdf_path, os.path.dirname(src_dir))
            break
    
    chunks = chunk_document(pages, doc_id, rel_path)
    if not chunks:
        logger.warning(f"  No chunks generated for {doc_id}")
        return False
    
    # 5. Summary
    summary = generate_summary(pages, meta)
    
    # 6. Export
    export_document(doc_id, rel_path, meta, summary, chunks)
    
    logger.info(f"  ✅ {doc_id}: {len(chunks)} chunks, {len(pages)} pages")
    return True


def find_all_pdfs() -> list[str]:
    """Find all source PDFs."""
    pdfs = []
    for src_dir in PDF_SOURCE_DIRS:
        if not os.path.isdir(src_dir):
            continue
        for root, _, files in os.walk(src_dir):
            for f in files:
                if f.lower().endswith(".pdf"):
                    pdfs.append(os.path.join(root, f))
    return sorted(pdfs)


def main():
    """Entry point: process PDFs and export results."""
    if len(sys.argv) >= 2:
        # Process single file
        pdf_path = sys.argv[1]
        if not os.path.exists(pdf_path):
            print(f"File not found: {pdf_path}")
            sys.exit(1)
        run_pipeline(pdf_path)
    else:
        # Process all PDFs
        pdfs = find_all_pdfs()
        if not pdfs:
            print("No PDFs found in source directories!")
            sys.exit(1)
        
        print(f"\n  Processing {len(pdfs)} PDFs...\n")
        
        success = 0
        failed = 0
        for i, pdf_path in enumerate(pdfs, 1):
            try:
                ok = run_pipeline(pdf_path)
                if ok:
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"  ❌ Failed: {pdf_path}: {e}")
                failed += 1
            
            if i % 10 == 0:
                print(f"  Progress: {i}/{len(pdfs)} ({success} ok, {failed} failed)")
        
        print(f"\n  {'=' * 40}")
        print(f"  Done: {success}/{len(pdfs)} succeeded, {failed} failed")
        print(f"  Exports: {EXPORT_DIR}")
        print(f"  {'=' * 40}\n")


if __name__ == "__main__":
    main()
