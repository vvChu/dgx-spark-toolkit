from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from models.schemas import SyncStatusRequest, SyncStatusResponse
from core.config import get_settings
from core.database import get_milvus_repo, get_neo4j_repo, get_state_manager
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from ingestion.state_manager import PostgresStateManager
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
    except Exception as e:
        logger.error("Audit execution failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error running audit")


@router.get("/pipeline/{action}", response_class=PlainTextResponse)
async def run_pipeline(action: str):
    """Run pipeline.py with --apply, --revert, or --dry-run."""
    if action not in ("apply", "revert", "dry-run"):
        raise HTTPException(status_code=400, detail="action must be: apply, revert, dry-run")
    try:
        output = await asyncio.to_thread(
            _run_subprocess,
            [sys.executable, "/app/pipeline.py", f"--{action}"],
            120,
        )
        return output
    except Exception as e:
        logger.error("Pipeline execution failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error running pipeline")


@router.post("/sync-status", response_model=SyncStatusResponse)
async def sync_document_status(
    request: SyncStatusRequest,
    state_manager: PostgresStateManager = Depends(get_state_manager),
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo),
):
    """Cascading update of document validity status across all data stores."""
    try:
        service = LifecycleService(state_manager, milvus_repo, neo4j_repo)
        result = await service.sync_document_status(request.doc_id, request.new_status)

        if result["status"] == "partial_success":
            return JSONResponse(status_code=207, content=result)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Admin sync-status error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error syncing document status")
