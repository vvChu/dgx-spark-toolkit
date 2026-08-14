from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from models.schemas import SyncStatusRequest, SyncStatusResponse
from core.config import get_settings
from core.database import get_document_store
from repositories.document_store import DocumentStore
from services.lifecycle_service import LifecycleService

import asyncio
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


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


def _run_subprocess(cmd: list[str], timeout: int = 300) -> str:
    """Run a subprocess synchronously (called via asyncio.to_thread)."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd="/app",
    )
    return result.stdout + result.stderr


# ── Admin Script Endpoints ──────────────────────────────────────────────
@router.get("/audit", response_class=PlainTextResponse)
async def run_audit():
    """Run comprehensive_audit.py and return raw output."""
    try:
        output = await asyncio.to_thread(
            _run_subprocess,
            [sys.executable, "/app/scripts/comprehensive_audit.py"],
            300,
        )
        return output
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Audit timed out (>300s)")
    except Exception:
        logger.error("Audit execution failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error running audit")


@router.get("/pipeline/{action}", response_class=PlainTextResponse)
async def run_pipeline(action: str):
    """Run export_postprocessor.py with --apply, --revert, or --dry-run."""
    if action not in ("apply", "revert", "dry-run"):
        raise HTTPException(status_code=400, detail="action must be: apply, revert, dry-run")
    try:
        output = await asyncio.to_thread(
            _run_subprocess,
            [sys.executable, "/app/export_postprocessor.py", f"--{action}"],
            120,
        )
        return output
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
        service = LifecycleService(document_store=document_store)
        result = await service.sync_document_status(request.doc_id, request.new_status)

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
    import os
    import datetime
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
