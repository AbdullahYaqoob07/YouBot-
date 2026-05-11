from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["Frontend"])

@router.get("/")
async def root():
    """Redirect to test frontend"""
    return RedirectResponse(url="/static/index.html")

@router.get("/admin")
async def admin_dashboard():
    """Redirect to admin supervision dashboard"""
    return RedirectResponse(url="/static/admin_dashboard.html")

@router.get("/kb-management")
async def kb_management():
    """Redirect to KB management page"""
    return RedirectResponse(url="/static/kb-management.html")

@router.get("/phase1/tenant-validation")
async def phase1_tenant_validation():
    """Redirect to Phase 1 tenant/workspace validation page."""
    return RedirectResponse(url="/static/phase1_tenant_validation.html")

@router.get("/phase2/llm-validation")
async def phase2_llm_validation():
    """Redirect to Phase 2 LLM provider/model validation page."""
    return RedirectResponse(url="/static/phase2_llm_validation.html")

@router.get("/phase3/retrieval-validation")
async def phase3_retrieval_validation():
    """Redirect to Phase 3 retrieval validation page."""
    return RedirectResponse(url="/static/phase3_retrieval_validation.html")

@router.get("/phase3/ingestion-validation")
async def phase3_ingestion_validation():
    """Redirect to Phase 3 ingestion validation page."""
    return RedirectResponse(url="/static/phase3_ingestion_validation.html")

@router.get("/phase4/supervision-validation")
async def phase4_supervision_validation():
    """Redirect to Phase 4 supervision and channels validation page."""
    return RedirectResponse(url="/static/phase4_supervision_validator.html")

@router.get("/phase5/analytics-validation")
async def phase5_analytics_validator():
    """Redirect to Phase 5 analytics validator page."""
    return RedirectResponse(url="/static/phase5_analytics_validator.html")

@router.get("/saas-readiness")
async def saas_readiness_verifier():
    """Redirect to SaaS readiness smoke validation page."""
    return RedirectResponse(url="/static/saas_readiness_verifier.html")
