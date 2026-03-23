"""Non-PDF document conversion for the RAG ingestion pipeline.

Converts DOC, DOCX, JPG/PNG, and XLS/XLSX files into the same chunk format
used by the PDF extraction path, so they flow through the same chunking,
enrichment, and indexing stages.

Usage:
    from ingestion.doc_converter import extract_docx, extract_image, extract_spreadsheet

    chunks, failed = extract_docx("/path/to/doc.docx")
"""

import logging
import os
import re
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


def extract_docx(file_path: str) -> tuple[list, list]:
    """Extract text and tables from DOCX files using python-docx.

    Returns:
        Tuple of (chunks_list, failed_pages_list).
    """
    try:
        from docx import Document
    except ImportError:
        logger.warning("[DOC] python-docx not installed — cannot process DOCX files")
        return [], [0]

    try:
        doc = Document(file_path)
        chunks = []
        page_num = 1  # DOCX doesn't have real pages — treat as sequential blocks

        # Extract paragraphs
        text_buffer = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                if text_buffer:
                    combined = "\n".join(text_buffer)
                    if len(combined) > 30:
                        chunks.append({
                            "text": combined,
                            "page": page_num,
                            "is_table": False,
                            "layout": [],
                            "source": "docx",
                        })
                    text_buffer = []
                    page_num += 1
                continue
            text_buffer.append(text)

        # Flush remaining text
        if text_buffer:
            combined = "\n".join(text_buffer)
            if len(combined) > 30:
                chunks.append({
                    "text": combined,
                    "page": page_num,
                    "is_table": False,
                    "layout": [],
                    "source": "docx",
                })
                page_num += 1

        # Extract tables
        for table in doc.tables:
            md_rows = []
            for row_idx, row in enumerate(table.rows):
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                md_rows.append("| " + " | ".join(cells) + " |")
                if row_idx == 0:
                    md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")

            if len(md_rows) >= 3:  # header + separator + 1 data row minimum
                table_text = "\n".join(md_rows)
                chunks.append({
                    "text": table_text,
                    "page": page_num,
                    "is_table": True,
                    "layout": [],
                    "source": "docx",
                })
                page_num += 1

        logger.info(f"[DOC] Extracted {len(chunks)} chunks from DOCX: {os.path.basename(file_path)}")
        return chunks, []

    except Exception as e:
        logger.error(f"[DOC] DOCX extraction failed for {file_path}: {e}")
        return [], [0]


def convert_doc_to_docx(file_path: str) -> Optional[str]:
    """Convert DOC to DOCX using LibreOffice (headless).

    Returns:
        Path to the converted DOCX file, or None on failure.
    """
    try:
        tmpdir = tempfile.mkdtemp(prefix="rag_doc_")
        result = subprocess.run(
            [
                "libreoffice", "--headless", "--convert-to", "docx",
                "--outdir", tmpdir, file_path,
            ],
            capture_output=True, text=True, timeout=120,
        )

        if result.returncode != 0:
            logger.warning(f"[DOC] LibreOffice conversion failed: {result.stderr[:200]}")
            return None

        # Find the output file
        basename = os.path.splitext(os.path.basename(file_path))[0]
        docx_path = os.path.join(tmpdir, f"{basename}.docx")

        if os.path.exists(docx_path):
            logger.info(f"[DOC] Converted {os.path.basename(file_path)} → DOCX")
            return docx_path

        # LibreOffice might use different naming
        for f in os.listdir(tmpdir):
            if f.endswith(".docx"):
                return os.path.join(tmpdir, f)

        logger.warning(f"[DOC] No DOCX output found after conversion")
        return None

    except FileNotFoundError:
        logger.warning("[DOC] LibreOffice not found — cannot convert DOC files")
        return None
    except subprocess.TimeoutExpired:
        logger.warning(f"[DOC] LibreOffice conversion timed out for {file_path}")
        return None
    except Exception as e:
        logger.warning(f"[DOC] DOC→DOCX conversion failed: {e}")
        return None


def extract_doc(file_path: str) -> tuple[list, list]:
    """Extract text from DOC files by converting to DOCX first.

    Returns:
        Tuple of (chunks_list, failed_pages_list).
    """
    docx_path = convert_doc_to_docx(file_path)
    if docx_path is None:
        return [], [0]

    try:
        return extract_docx(docx_path)
    finally:
        # Cleanup temp file
        try:
            if docx_path and os.path.exists(docx_path):
                os.unlink(docx_path)
                tmpdir = os.path.dirname(docx_path)
                if tmpdir and os.path.isdir(tmpdir):
                    os.rmdir(tmpdir)
        except OSError:
            pass


def extract_image(file_path: str) -> tuple[list, list]:
    """Extract text from image files (JPG/PNG) via LLM Vision OCR.

    Returns:
        Tuple of (chunks_list, failed_pages_list).
    """
    try:
        from ingestion.cloud_vision import llm_extract_page
        from ingestion.image_preprocessor import preprocess_page_image

        with open(file_path, "rb") as f:
            img_bytes = f.read()

        # Preprocess before OCR
        enhanced = preprocess_page_image(img_bytes, dpi=200)

        result = llm_extract_page(enhanced, page_num=1)
        if result.get("text", ""):
            chunks = [{
                "text": result["text"],
                "page": 1,
                "is_table": result.get("is_table", False),
                "layout": result.get("layout", []),
                "source": "image_ocr",
            }]
            logger.info(f"[DOC] Extracted {len(result['text'])} chars from image: {os.path.basename(file_path)}")
            return chunks, []

        return [], [1]

    except Exception as e:
        logger.error(f"[DOC] Image extraction failed for {file_path}: {e}")
        return [], [0]


def extract_spreadsheet(file_path: str) -> tuple[list, list]:
    """Extract tables from Excel files (XLS/XLSX) as markdown.

    Returns:
        Tuple of (chunks_list, failed_pages_list).
    """
    try:
        import openpyxl
    except ImportError:
        logger.warning("[DOC] openpyxl not installed — cannot process Excel files")
        return [], [0]

    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        chunks = []
        page_num = 1

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                continue

            # Convert to markdown table
            md_lines = []
            max_cols = max(len(row) for row in rows)

            for row_idx, row in enumerate(rows):
                cells = [str(cell) if cell is not None else "" for cell in row]
                # Pad to max_cols
                cells += [""] * (max_cols - len(cells))
                md_lines.append("| " + " | ".join(cells) + " |")
                if row_idx == 0:
                    md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")

            if len(md_lines) >= 3:
                table_text = f"**Sheet: {sheet_name}**\n\n" + "\n".join(md_lines)
                chunks.append({
                    "text": table_text,
                    "page": page_num,
                    "is_table": True,
                    "layout": [],
                    "source": "xlsx",
                })
                page_num += 1

        wb.close()
        logger.info(f"[DOC] Extracted {len(chunks)} sheets from Excel: {os.path.basename(file_path)}")
        return chunks, []

    except Exception as e:
        logger.error(f"[DOC] Spreadsheet extraction failed for {file_path}: {e}")
        return [], [0]
