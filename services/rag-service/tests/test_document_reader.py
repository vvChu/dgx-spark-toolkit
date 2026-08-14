"""Unit tests for the deep DocumentReader module and InMemoryDocumentReader test adapter."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ingestion.document_reader import (
    DocumentReader,
    InMemoryDocumentReader,
    PageContent,
    ExtractedDocument,
)
from ingestion.pipeline import DocumentIngestionPipeline
from ingestion.state_manager import InMemoryStateManager
from ingestion.models import ProcessedDocument, DocumentIdentity


class TestPageContentAndExtractedDocument:
    """Test PageContent and ExtractedDocument domain contracts."""

    def test_page_content_to_dict(self):
        page = PageContent(
            page=1,
            text="Điều 1. Phạm vi điều chỉnh",
            route="native",
            is_table=False,
            bbox=[0, 0, 500, 500],
            layout=[{"label": "text"}],
        )
        d = page.to_dict()
        assert d["page"] == 1
        assert d["text"] == "Điều 1. Phạm vi điều chỉnh"
        assert d["route"] == "native"
        assert d["is_table"] is False
        assert d["bbox"] == [0, 0, 500, 500]
        assert len(d["layout"]) == 1

    def test_extracted_document_properties(self):
        pages = [
            PageContent(page=1, text="Trang 1: Mở đầu"),
            PageContent(page=2, text="Trang 2: Điều 1"),
        ]
        doc = ExtractedDocument(
            file_path="/tmp/test.pdf",
            format_type="pdf",
            pages=pages,
            metadata={"author": "BXD"},
        )
        assert doc.total_pages == 2
        assert "Trang 1: Mở đầu\nTrang 2: Điều 1" == doc.full_text
        pages_dict = doc.to_pages_dict()
        assert len(pages_dict) == 2
        assert pages_dict[0]["page"] == 1
        assert pages_dict[1]["page"] == 2


class TestInMemoryDocumentReader:
    """Test InMemoryDocumentReader adapter for deterministic hermetic testing."""

    def test_set_and_extract_mock_document(self):
        reader = InMemoryDocumentReader()
        custom_pages = [
            PageContent(page=1, text="Nội dung trang 1", route="mock"),
            PageContent(page=2, text="Nội dung trang 2", route="mock"),
        ]
        reader.set_mock_document("sample_luat.pdf", custom_pages, format_type="pdf")

        extracted = reader.extract("sample_luat.pdf")
        assert extracted.total_pages == 2
        assert extracted.pages[0].text == "Nội dung trang 1"
        assert extracted.format_type == "pdf"
        assert extracted.error is None

    def test_extract_by_basename(self):
        reader = InMemoryDocumentReader()
        reader.set_mock_document("doc.docx", [PageContent(page=1, text="Word content")], format_type="docx")

        extracted = reader.extract("/path/to/nested/doc.docx")
        assert extracted.total_pages == 1
        assert extracted.pages[0].text == "Word content"

    def test_extract_fallback_stub(self):
        reader = InMemoryDocumentReader()
        extracted = reader.extract("/any/unknown/test_doc.pdf")
        assert extracted.total_pages == 1
        assert "test_doc.pdf" in extracted.pages[0].text
        assert extracted.pages[0].route == "in_memory"

    def test_extract_async(self):
        import asyncio
        reader = InMemoryDocumentReader()
        reader.set_mock_document("async_doc.pdf", [PageContent(page=1, text="Async text")])
        extracted = asyncio.run(reader.extract_async("async_doc.pdf"))
        assert extracted.total_pages == 1
        assert extracted.pages[0].text == "Async text"


class TestDocumentReader:
    """Test DocumentReader format dispatching and error handling."""

    def test_file_not_found(self):
        reader = DocumentReader()
        extracted = reader.extract("/nonexistent/path/missing_file.pdf")
        assert extracted.error is not None
        assert "File not found" in extracted.error
        assert extracted.total_pages == 0

    def test_unsupported_format(self, tmp_path):
        bad_file = tmp_path / "archive.zip"
        bad_file.write_text("dummy")
        reader = DocumentReader()
        extracted = reader.extract(str(bad_file))
        assert extracted.error is not None
        assert "Unsupported format" in extracted.error

    def test_extract_docx_mocked(self, tmp_path):
        import sys
        docx_file = tmp_path / "sample.docx"
        docx_file.write_text("dummy")

        reader = DocumentReader()
        mock_docx_module = MagicMock()
        mock_doc = MagicMock()
        mock_para1 = MagicMock(text="Đoạn văn 1: Căn cứ luật xây dựng.")
        mock_para2 = MagicMock(text="Đoạn văn 2: Điều 1.")
        mock_doc.paragraphs = [mock_para1, mock_para2]
        mock_doc.tables = []
        mock_docx_module.Document.return_value = mock_doc

        with patch.dict(sys.modules, {"docx": mock_docx_module}):
            extracted = reader.extract(str(docx_file))
            assert extracted.format_type == "docx"
            assert extracted.total_pages >= 1
            assert "Đoạn văn 1" in extracted.full_text

    def test_extract_spreadsheet_mocked(self, tmp_path):
        import sys
        xlsx_file = tmp_path / "table.xlsx"
        xlsx_file.write_text("dummy")

        reader = DocumentReader()
        mock_openpyxl = MagicMock()
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_sheet = MagicMock()
        mock_sheet.iter_rows.return_value = [
            [MagicMock(value="STT"), MagicMock(value="Tên")],
            [MagicMock(value="1"), MagicMock(value="Hạng mục A")],
        ]
        mock_wb.__getitem__.return_value = mock_sheet
        mock_openpyxl.load_workbook.return_value = mock_wb

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}):
            extracted = reader.extract(str(xlsx_file))
            assert extracted.format_type == "xlsx"
            assert extracted.total_pages == 1
            assert extracted.pages[0].is_table is True
            assert "Sheet1" in extracted.pages[0].text

    def test_extract_image_mocked(self, tmp_path):
        img_file = tmp_path / "scan.png"
        img_file.write_bytes(b"dummy image bytes")

        reader = DocumentReader()
        with patch("ingestion.image_preprocessor.preprocess_page_image", return_value=b"enhanced"), \
             patch("ingestion.cloud_vision.llm_extract_page", return_value={"text": "OCR từ ảnh", "is_table": False}):
            extracted = reader.extract(str(img_file))
            assert extracted.format_type == "image"
            assert extracted.total_pages == 1
            assert extracted.pages[0].text == "OCR từ ảnh"
            assert extracted.pages[0].route == "image_ocr"


class TestDocumentIngestionPipelineWithDocumentReader:
    """Test DocumentIngestionPipeline integration with DocumentReader."""

    def test_pipeline_uses_in_memory_reader_by_default_with_in_memory_state_manager(self):
        state_mgr = InMemoryStateManager()
        pipeline = DocumentIngestionPipeline(state_manager=state_mgr)
        assert isinstance(pipeline.document_reader, InMemoryDocumentReader)

    def test_pipeline_stage_ocr_with_in_memory_reader(self):
        state_mgr = InMemoryStateManager()
        reader = InMemoryDocumentReader()
        reader.set_mock_document("luat_50.pdf", [
            PageContent(page=1, text="Luật số 50/2014/QH13. Điều 1. Phạm vi điều chỉnh."),
            PageContent(page=2, text="Điều 2. Đối tượng áp dụng."),
        ])

        pipeline = DocumentIngestionPipeline(state_manager=state_mgr, document_reader=reader)

        doc = ProcessedDocument(
            identity=DocumentIdentity(
                doc_number="50/2014/QH13",
                namespace="VBPL",
                content_hash="abc123hash",
                file_name="luat_50.pdf",
                rel_path="luat_50.pdf",
            ),
            file_path="luat_50.pdf",
        )

        processed = pipeline._stage_ocr(doc)
        assert len(processed.pages) == 2
        assert processed.pages[0]["page"] == 1
        assert "Luật số 50/2014/QH13" in processed.pages[0]["text"]
        assert processed.pages[1]["page"] == 2
