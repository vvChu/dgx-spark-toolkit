"""PDF document preview endpoint."""
from fastapi import APIRouter, HTTPException, Query
from core.config import get_settings
import base64
import fitz  # PyMuPDF
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Visualization"])


@router.get("/preview", tags=["Visualization"])
async def preview_page(
    source: str = Query(..., description="Document ID"),
    page: int = Query(1, ge=1),
):
    """Render a PDF page as a base64-encoded PNG image."""
    settings = get_settings()
    pdf_dir = settings.PDF_DIR

    pdf_path = _resolve_pdf(source, pdf_dir)
    if not pdf_path:
        raise HTTPException(status_code=404, detail=f"PDF not found for {source}")

    try:
        doc = fitz.open(pdf_path)
        if page > len(doc):
            page = len(doc)
        pix = doc[page - 1].get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()
        return {
            "source": source,
            "page": page,
            "image_b64": base64.b64encode(img_bytes).decode(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render error: {e}")


def _resolve_pdf(source: str, pdf_dir: str) -> str | None:
    """Find a PDF file matching the given document ID."""
    candidate = os.path.join(pdf_dir, f"{source}.pdf")
    if os.path.isfile(candidate):
        return candidate
    for root, _, files in os.walk(pdf_dir):
        for f in files:
            if f.endswith(".pdf") and source in f:
                return os.path.join(root, f)
    return None
