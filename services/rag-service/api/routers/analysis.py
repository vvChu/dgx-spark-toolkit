from fastapi import APIRouter, Depends
from models.schemas import (
    ConflictAnalysisRequest, ComplianceCheckRequest,
    DiagramGenerationRequest, DiagramGenerationResponse,
)
from core.database import get_legal_analysis_engine, get_compliance_service
from services.legal_analysis_service import LegalAnalysisEngine
from services.compliance_service import ComplianceService

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.post("/conflict")
async def analyze_conflict(
    request: ConflictAnalysisRequest,
    analysis_engine: LegalAnalysisEngine = Depends(get_legal_analysis_engine)
):
    """
    Analyze regulatory changes and potential conflicts between a document and its predecessors.
    """
    return await analysis_engine.analyze_conflicts(
        doc_id=request.doc_id,
        query=request.query,
        depth=request.depth
    )


@router.post("/compliance")
async def check_compliance(
    request: ComplianceCheckRequest,
    compliance_service: ComplianceService = Depends(get_compliance_service)
):
    """
    Check a project profile for compliance against active regulations.
    """
    return await compliance_service.check_compliance(
        project_profile=request.project_profile,
        focus_area=request.focus_area
    )


@router.post("/generate-diagram", response_model=DiagramGenerationResponse)
async def generate_diagram(request: DiagramGenerationRequest):
    """
    Generate an SOP/QCVN workflow diagram prompt using Imagen 4 Fast (Free Tier 25/day limit).
    """
    steps_formatted = " -> ".join(request.workflow_steps)
    image_prompt = (
        f"A clean, professional {request.style} diagram for standard operating procedure: '{request.sop_title}'. "
        f"Workflow sequence: {steps_formatted}. High legibility, vector blueprint aesthetic."
    )
    logger.info(f"[IMAGEN-4-FAST] Generated diagram prompt for SOP: '{request.sop_title}' (25/day limit pool)")
    return DiagramGenerationResponse(
        status="ok",
        sop_title=request.sop_title,
        image_prompt=image_prompt,
        model="imagen-4-fast",
        daily_quota_limit=25
    )
