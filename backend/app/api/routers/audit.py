from fastapi import APIRouter

from app.schemas import AuditIssue
from app.services.mock_data import AUDIT_ISSUES

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/issues", response_model=list[AuditIssue])
def list_audit_issues() -> list[AuditIssue]:
    return AUDIT_ISSUES
