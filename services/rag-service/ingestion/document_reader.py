"""Deep DocumentReader module for unified multi-format document extraction.

Consolidates native PDF parsing, PDF tier classification (native vs scan),
Surya/LLM Vision OCR routing, DOCX/DOC conversion, spreadsheet parsing,
and image OCR behind a single extraction interface.
"""
import asyncio
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    """Standardized representation of a single extracted document page."""
    page: int
    text: str
    route: str = "native"
    is_table: bool = False
    bbox: Any = field(default_factory=lambda: [0, 0, 1000, 1000])
    layout: list = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "text": self.text,
            "route": self.route,
            "is_table": self.is_table,
            "bbox": self.bbox,
            "layout": self.layout,
        }


@dataclass
class ExtractedDocument:
    """Type-safe output of the DocumentReader extraction seam."""
    file_path: str
    format_type: str
    pages: List[PageContent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    def to_pages_dict(self) -> List[Dict[str, Any]]:
        """Convert pages to standard dicts for ProcessedDocument."""
        return [p.to_dict() for p in self.pages]


class DocumentReader:
    """Unified deep module for multi-format document ingestion and OCR routing."""

    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.jpg', '.jpeg', '.png', '.xls', '.xlsx'}

    def __init__(self, vision_extractor: Optional[Any] = None):
        self.vision_extractor = vision_extractor

    def extract(self, file_path: Union[str, Path]) -> ExtractedDocument:
        """Extract pages from any supported legal document format synchronously."""
        path_str = str(file_path)
        ext = os.path.splitext(path_str)[1].lower()

        if not os.path.exists(path_str):
            logger.error(f"[DocumentReader] File not found: {path_str}")
            return ExtractedDocument(
                file_path=path_str,
                format_type=ext.lstrip('.'),
                error=f"File not found: {path_str}",
            )

        try:
            if ext == '.pdf':
                return self._extract_pdf(path_str)
            elif ext in ('.docx', '.doc'):
                return self._extract_docx_or_doc(path_str, ext)
            elif ext in ('.xlsx', '.xls'):
                return self._extract_spreadsheet(path_str)
            elif ext in ('.jpg', '.jpeg', '.png'):
                return self._extract_image(path_str)
            else:
                logger.warning(f"[DocumentReader] Unsupported file extension: {ext} for {path_str}")
                return ExtractedDocument(
                    file_path=path_str,
                    format_type=ext.lstrip('.'),
                    error=f"Unsupported format: {ext}",
                )
        except Exception as e:
            logger.error(f"[DocumentReader] Extraction failed for {path_str}: {e}", exc_info=True)
            return ExtractedDocument(
                file_path=path_str,
                format_type=ext.lstrip('.'),
                error=str(e),
            )

    async def extract_async(self, file_path: Union[str, Path]) -> ExtractedDocument:
        """Async convenience wrapper running extraction in threadpool executor."""
        return await asyncio.to_thread(self.extract, file_path)

    # ── Format Adapters (Internal) ────────────────────────────────────

    def _extract_pdf(self, file_path: str) -> ExtractedDocument:
        """Extract pages from PDF using PyMuPDF (native) or Surya/LLM Vision (scanned)."""
        try:
            import fitz
        except ImportError:
            logger.warning("[DocumentReader] PyMuPDF (fitz) not available; falling back to stub")
            return ExtractedDocument(
                file_path=file_path,
                format_type="pdf",
                pages=[PageContent(page=1, text="PDF extractor requires PyMuPDF", route="error")],
            )

        from ingestion.pdf_classifier import classify_page, PdfType

        pages: List[PageContent] = []
        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)

            for page_idx in range(total_pages):
                page_num = page_idx + 1
                page = doc[page_idx]
                page_type = classify_page(page, page_idx)

                if page_type == PdfType.NATIVE:
                    text = page.get_text().strip()
                    pages.append(PageContent(
                        page=page_num,
                        text=text,
                        route="native",
                        is_table=False,
                        bbox=[0, 0, 1000, 1000],
                        layout=[],
                    ))
                else:
                    # Scanned page — render pixmap and run Vision/Surya OCR
                    img_bytes = None
                    try:
                        pix = page.get_pixmap(dpi=200)
                        img_bytes = pix.tobytes("jpeg")
                    except Exception as pe:
                        logger.warning(f"[DocumentReader] Failed to render pixmap for page {page_num}: {pe}")

                    if img_bytes:
                        try:
                            from ingestion.vision import hybrid_extract_page
                            extracted_res = hybrid_extract_page(img_bytes, page_num, total_pages)
                            if isinstance(extracted_res, dict):
                                text = extracted_res.get("text", "")
                                is_table = extracted_res.get("is_table", False)
                                layout = extracted_res.get("layout", [])
                                bbox = extracted_res.get("bbox", [0, 0, 1000, 1000])
                            else:
                                text = str(extracted_res or "")
                                is_table = False
                                layout = []
                                bbox = [0, 0, 1000, 1000]

                            pages.append(PageContent(
                                page=page_num,
                                text=text,
                                route="surya_ocr",
                                is_table=is_table,
                                bbox=bbox,
                                layout=layout,
                            ))
                        except Exception as ve:
                            logger.warning(f"[DocumentReader] Vision OCR failed on page {page_num}: {ve}")
                            # Cloud Vision fallback
                            try:
                                from ingestion.cloud_vision import llm_extract_page
                                cloud_res = llm_extract_page(img_bytes, page_num=page_num)
                                pages.append(PageContent(
                                    page=page_num,
                                    text=cloud_res.get("text", ""),
                                    route="vision_llm",
                                    is_table=cloud_res.get("is_table", False),
                                ))
                            except Exception as cve:
                                logger.error(f"[DocumentReader] Cloud Vision fallback failed for page {page_num}: {cve}")
                                pages.append(PageContent(page=page_num, text="", route="failed"))
                    else:
                        pages.append(PageContent(page=page_num, text="", route="failed"))

            doc.close()
            return ExtractedDocument(file_path=file_path, format_type="pdf", pages=pages)

        except Exception as e:
            logger.error(f"[DocumentReader] Error opening PDF {file_path}: {e}")
            return ExtractedDocument(file_path=file_path, format_type="pdf", error=str(e))

    def _extract_docx_or_doc(self, file_path: str, ext: str) -> ExtractedDocument:
        """Extract text and tables from Word (.docx / .doc) documents."""
        actual_path = file_path
        cleanup_temp = False

        if ext == '.doc':
            converted = self._convert_doc_to_docx(file_path)
            if converted:
                actual_path = converted
                cleanup_temp = True
            else:
                return ExtractedDocument(
                    file_path=file_path,
                    format_type="doc",
                    error="LibreOffice conversion from .doc to .docx failed",
                )

        try:
            from docx import Document
            doc = Document(actual_path)
            pages: List[PageContent] = []
            page_num = 1

            # Extract paragraphs in structured blocks
            text_buffer = []
            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    if text_buffer:
                        combined = "\n".join(text_buffer)
                        if len(combined) > 30:
                            pages.append(PageContent(page=page_num, text=combined, route="docx", is_table=False))
                            page_num += 1
                        text_buffer = []
                    continue
                text_buffer.append(text)

            if text_buffer:
                combined = "\n".join(text_buffer)
                if len(combined) > 30:
                    pages.append(PageContent(page=page_num, text=combined, route="docx", is_table=False))
                    page_num += 1

            # Extract tables as Markdown
            for table in doc.tables:
                md_rows = []
                for row_idx, row in enumerate(table.rows):
                    cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    md_rows.append("| " + " | ".join(cells) + " |")
                    if row_idx == 0:
                        md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")

                if len(md_rows) >= 3:
                    table_text = "\n".join(md_rows)
                    pages.append(PageContent(page=page_num, text=table_text, route="docx", is_table=True))
                    page_num += 1

            if not pages:
                # Fallback for empty or single small doc
                full_raw = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                pages.append(PageContent(page=1, text=full_raw, route="docx", is_table=False))

            return ExtractedDocument(file_path=file_path, format_type="docx", pages=pages)

        except ImportError:
            logger.warning("[DocumentReader] python-docx not installed")
            return ExtractedDocument(file_path=file_path, format_type="docx", error="python-docx not installed")
        finally:
            if cleanup_temp and actual_path and os.path.exists(actual_path):
                try:
                    os.unlink(actual_path)
                except OSError:
                    pass
                parent_dir = os.path.dirname(actual_path)
                if os.path.basename(parent_dir).startswith("rag_doc_") and os.path.isdir(parent_dir):
                    shutil.rmtree(parent_dir, ignore_errors=True)

    def _convert_doc_to_docx(self, file_path: str) -> Optional[str]:
        """Convert legacy .doc to .docx using headless LibreOffice."""
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
                logger.warning(f"[DocumentReader] LibreOffice conversion failed: {result.stderr[:200]}")
                return None

            basename = os.path.splitext(os.path.basename(file_path))[0]
            docx_path = os.path.join(tmpdir, f"{basename}.docx")
            if os.path.exists(docx_path):
                return docx_path

            for f in os.listdir(tmpdir):
                if f.endswith(".docx"):
                    return os.path.join(tmpdir, f)
            return None
        except Exception as e:
            logger.warning(f"[DocumentReader] LibreOffice doc conversion error: {e}")
            return None

    def _extract_spreadsheet(self, file_path: str) -> ExtractedDocument:
        """Extract Excel sheets (.xlsx / .xls) as Markdown tables."""
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            pages: List[PageContent] = []
            page_num = 1

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = list(ws.iter_rows(values_only=True))
                if len(rows) < 2:
                    continue

                md_lines = []
                max_cols = max((len(row) for row in rows), default=0)
                if max_cols == 0:
                    continue

                for row_idx, row in enumerate(rows):
                    cells = [str(cell) if cell is not None else "" for cell in row]
                    cells += [""] * (max_cols - len(cells))
                    md_lines.append("| " + " | ".join(cells) + " |")
                    if row_idx == 0:
                        md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")

                if len(md_lines) >= 3:
                    table_text = f"**Bảng / Sheet: {sheet_name}**\n\n" + "\n".join(md_lines)
                    pages.append(PageContent(
                        page=page_num,
                        text=table_text,
                        route="xlsx",
                        is_table=True,
                    ))
                    page_num += 1

            wb.close()
            return ExtractedDocument(file_path=file_path, format_type="xlsx", pages=pages)
        except ImportError:
            logger.warning("[DocumentReader] openpyxl not installed")
            return ExtractedDocument(file_path=file_path, format_type="xlsx", error="openpyxl not installed")
        except Exception as e:
            logger.error(f"[DocumentReader] Spreadsheet extraction error: {e}")
            return ExtractedDocument(file_path=file_path, format_type="xlsx", error=str(e))

    def _extract_image(self, file_path: str) -> ExtractedDocument:
        """Extract text and tables from image files (.jpg, .jpeg, .png) via LLM Vision."""
        try:
            from ingestion.image_preprocessor import preprocess_page_image
            from ingestion.cloud_vision import llm_extract_page

            with open(file_path, "rb") as f:
                img_bytes = f.read()

            enhanced = preprocess_page_image(img_bytes, dpi=200)
            res = llm_extract_page(enhanced, page_num=1)
            text = res.get("text", "")
            is_table = res.get("is_table", False)
            layout = res.get("layout", [])

            pages = [PageContent(
                page=1,
                text=text,
                route="image_ocr",
                is_table=is_table,
                layout=layout,
            )]
            return ExtractedDocument(file_path=file_path, format_type="image", pages=pages)
        except Exception as e:
            logger.error(f"[DocumentReader] Image extraction error: {e}")
            return ExtractedDocument(file_path=file_path, format_type="image", error=str(e))


class InMemoryDocumentReader(DocumentReader):
    """In-memory test adapter for deterministic, offline unit testing."""

    def __init__(self):
        super().__init__()
        self.mock_documents: Dict[str, ExtractedDocument] = {}

    def set_mock_document(
        self,
        file_path: str,
        pages: List[PageContent],
        format_type: str = "pdf",
        error: Optional[str] = None,
    ):
        """Register deterministic mock pages for a given file path or name."""
        self.mock_documents[file_path] = ExtractedDocument(
            file_path=file_path,
            format_type=format_type,
            pages=pages,
            error=error,
        )

    def extract(self, file_path: Union[str, Path]) -> ExtractedDocument:
        path_str = str(file_path)
        base_name = os.path.basename(path_str)

        if path_str in self.mock_documents:
            return self.mock_documents[path_str]
        if base_name in self.mock_documents:
            return self.mock_documents[base_name]

        # Automatic deterministic fallback stub for unit tests
        ext = os.path.splitext(path_str)[1].lower().lstrip('.') or "pdf"
        stub_pages = [
            PageContent(
                page=1,
                text=f"Văn bản pháp luật mô phỏng ({base_name}). Điều 1. Phạm vi điều chỉnh.",
                route="in_memory",
                is_table=False,
                bbox=[0, 0, 1000, 1000],
            )
        ]
        return ExtractedDocument(file_path=path_str, format_type=ext, pages=stub_pages)
