from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_optional_db
from app.schemas import AuditIssue
from app.services.client_data import campaigns_from_direct
from app.services.mock_data import AUDIT_ISSUES
from app.services.performance_audit import build_audit_issues

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/issues", response_model=list[AuditIssue])
def list_audit_issues(client_id: str = "furniture", db: Session | None = Depends(get_optional_db)) -> list[AuditIssue]:
    if db is None:
        return AUDIT_ISSUES
    try:
        campaigns, _source = campaigns_from_direct(db=db)
    except Exception:
        return AUDIT_ISSUES
    generated = build_audit_issues(campaigns)
    return generated or AUDIT_ISSUES
