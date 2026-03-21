from fastapi import APIRouter, Depends, HTTPException
from models.schemas import ConflictAnalysisRequest, ComplianceCheckRequest
from core.database import get_legal_analysis_service, get_compliance_service
from services.legal_analysis_service import LegalAnalysisService
from services.compliance_service import ComplianceService

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["Analysis"])

@router.post("/conflict")
async def analyze_conflict(
    request: ConflictAnalysisRequest,
    analysis_service: LegalAnalysisService = Depends(get_legal_analysis_service)
):
    """
    Analyze regulatory changes and potential conflicts between a document and its predecessors.
    """
    try:
        result = await analysis_service.analyze_conflicts(
            doc_id=request.doc_id,
            query=request.query,
            depth=request.depth
        )
        return result
    except Exception as e:
        logger.error(f"Legal analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/compliance")
async def check_compliance(
    request: ComplianceCheckRequest,
    compliance_service: ComplianceService = Depends(get_compliance_service)
):
    """
    Check a project profile for compliance against active regulations.
    """
    try:
        result = await compliance_service.check_compliance(
            project_profile=request.project_profile,
            focus_area=request.focus_area
        )
        return result
    except Exception as e:
        logger.error(f"Compliance analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
