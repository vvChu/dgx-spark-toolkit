from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from models.schemas import SyncStatusRequest
from core.database import get_milvus_repo, get_neo4j_repo, get_state_manager
from repositories.milvus_repo import MilvusRepository
from repositories.neo4j_repo import Neo4jRepository
from ingestion.state_manager import PostgresStateManager
from services.lifecycle_service import LifecycleService

import logging
import subprocess
import sys
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Temporary Autoresearch Endpoints (remove after optimization) ────────
@router.get("/audit", response_class=PlainTextResponse)
async def run_audit():
    """Run comprehensive_audit.py and return raw output."""
    try:
        result = subprocess.run(
            [sys.executable, "/app/comprehensive_audit.py"],
            capture_output=True, text=True, timeout=300,
            cwd="/app",
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Audit timed out (>300s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/{action}", response_class=PlainTextResponse)
async def run_pipeline(action: str):
    """Run pipeline.py with --apply, --revert, or --dry-run."""
    if action not in ("apply", "revert", "dry-run"):
        raise HTTPException(status_code=400, detail="action must be: apply, revert, dry-run")
    try:
        result = subprocess.run(
            [sys.executable, "/app/pipeline.py", f"--{action}"],
            capture_output=True, text=True, timeout=120,
            cwd="/app",
        )
        return result.stdout + result.stderr
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync-status")
async def sync_document_status(
    request: SyncStatusRequest,
    state_manager: PostgresStateManager = Depends(get_state_manager),
    milvus_repo: MilvusRepository = Depends(get_milvus_repo),
    neo4j_repo: Neo4jRepository = Depends(get_neo4j_repo)
):
    """
    Cascading update of document validity status across all data stores.
    """
    try:
        service = LifecycleService(state_manager, milvus_repo, neo4j_repo)
        result = await service.sync_document_status(request.doc_id, request.new_status)
        
        if result["status"] == "partial_success":
            raise HTTPException(status_code=207, detail=result)
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin sync-status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
