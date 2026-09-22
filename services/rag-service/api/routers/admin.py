from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from models.schemas import SyncStatusRequest, SyncStatusResponse
from core.config import get_settings
from core.database import get_document_store
from repositories.document_store import DocumentStore
from ingestion.exporter import DataExporter

import asyncio
import datetime
import logging
import os

from scripts.comprehensive_audit import run_comprehensive_audit

logger = logging.getLogger(__name__)

# In-memory lock for pipeline operations (single-process uvicorn worker).
# For multi-worker deployments (workers > 1), replace with Redis distributed lock.
_pipeline_lock = asyncio.Lock()


async def verify_admin_key(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    """Validate the admin secret sent via X-Admin-Key header."""
    settings = get_settings()
    expected = settings.ADMIN_SECRET.get_secret_value()
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(verify_admin_key)],
)


# ── Admin Script Endpoints ──────────────────────────────────────────────
@router.get("/audit", response_class=PlainTextResponse)
async def run_audit():
    """Run comprehensive audit in-process and return formatted report."""
    try:
        settings = get_settings()
        pdf_source_dir = os.environ.get("PDF_SOURCE_DIR", "/app/data/legal_docs_source")
        output = await asyncio.wait_for(
            asyncio.to_thread(
                run_comprehensive_audit,
                json_dir=f"{settings.EXPORT_DIR}/json",
                md_dir=f"{settings.EXPORT_DIR}/markdown",
                pdf_dir=pdf_source_dir,
            ),
            timeout=60.0,
        )
        return output
    except asyncio.TimeoutError:
        logger.error("Audit execution timed out after 60s")
        raise HTTPException(status_code=504, detail="Audit timed out after 60s")
    except Exception:
        logger.error("Audit execution failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error running audit")


@router.get("/pipeline/{action}", response_class=PlainTextResponse)
async def run_pipeline(action: str):
    """Run export postprocessor in-process with apply, revert, or dry-run."""
    if action not in ("apply", "revert", "dry-run"):
        raise HTTPException(status_code=400, detail="action must be: apply, revert, dry-run")
    if _pipeline_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A pipeline operation is already in progress. Please wait until it completes.",
        )
    async with _pipeline_lock:
        try:
            settings = get_settings()
            exporter = DataExporter(settings.EXPORT_DIR)
            stats = await asyncio.to_thread(exporter.reprocess_exports, action)
            action_verb = "Would fix" if action == "dry-run" else ("Reverted" if action == "revert" else "Fixed")
            output = (
                f"Action: {action}\n"
                f"{action_verb} {stats.get('md_changed', 0)}/{stats.get('md_total', 0)} markdown files\n"
                f"{action_verb} {stats.get('json_changed', 0)}/{stats.get('json_total', 0)} JSON files\n"
                f"Summary: {stats}\n"
            )
            return output
        except HTTPException:
            raise
        except Exception:
            logger.error("Pipeline execution failed", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal error running pipeline")


@router.post("/sync-status", response_model=SyncStatusResponse)
async def sync_document_status(
    request: SyncStatusRequest,
    document_store: DocumentStore = Depends(get_document_store),
):
    """Cascading update of document validity status across all data stores."""
    try:
        result = await document_store.sync_status(doc_id=request.doc_id, new_status=request.new_status)

        if result["status"] == "partial_success":
            return JSONResponse(status_code=207, content=result)

        return result
    except HTTPException:
        raise
    except Exception:
        logger.error("Admin sync-status error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error syncing document status")


@router.get("/quota-status")
async def get_quota_status():
    """Retrieve real-time Google AI Studio Free Tier model quotas & Redis tracking status."""
    try:
        import redis
        redis_url = os.environ.get("REDIS_URL", "redis://litellm-redis:6379/1")
        r = redis.from_url(redis_url, decode_responses=True, socket_timeout=2.0)
        redis_connected = bool(r.ping())
    except Exception as e:
        logger.warning(f"Redis connection check failed for quota-status: {e}")
        redis_connected = False

    return {
        "status": "ok",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "redis_connected": redis_connected,
        "master_limits_file": "docs/google_ai_studio_free_tier_limits.md",
        "free_tier_quota_summary": {
            "gemini-3.1-flash-lite": {"rpm": 15, "tpm": 250000, "rpd": 500, "role": "Primary OCR & Ingestion"},
            "gemini-3.5-flash-lite": {"rpm": 15, "tpm": 250000, "rpd": 500, "role": "Chatbot & Metadata Extraction"},
            "gemma-4-26b": {"rpm": 30, "tpm": 16000, "rpd": 14400, "role": "Short Text Query Offloading"},
            "gemma-4-31b": {"rpm": 30, "tpm": 16000, "rpd": 14400, "role": "Short Text Query Offloading"},
            "gemini-embedding-2": {"rpm": 100, "tpm": 30000, "rpd": 1000, "role": "RAG Vector Search"},
            "antigravity-agents": {"rpm": 60, "tpm": 100000, "rpd": 100, "role": "Antigravity Agent Workflows"},
            "imagen-4-fast": {"daily_generate": 25, "role": "SOP & Diagram Generation"},
            "search-grounding": {"rpd": 1500, "role": "Web Search Knowledge Fallback"}
        }
    }
