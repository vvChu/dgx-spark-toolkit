from fastapi import APIRouter, Depends
from models.schemas import ConflictAnalysisRequest, ComplianceCheckRequest
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
