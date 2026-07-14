from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AiAuditEvidenceResult, AiAuditJob


EVIDENCE_TTL_DAYS = 7


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_load(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def save_audit_evidence_results(
    db: Session,
    job: AiAuditJob,
    *,
    evidence_kind: str,
    results: list[dict[str, Any]],
) -> None:
    now = datetime.now(UTC)
    expires_at = job.expires_at or (now + timedelta(days=EVIDENCE_TTL_DAYS))
    db.execute(delete(AiAuditEvidenceResult).where(AiAuditEvidenceResult.expires_at <= now))
    db.execute(delete(AiAuditEvidenceResult).where(
        AiAuditEvidenceResult.audit_job_id == job.id,
        AiAuditEvidenceResult.organization_id == job.organization_id,
        AiAuditEvidenceResult.client_id == job.client_id,
        AiAuditEvidenceResult.evidence_kind == evidence_kind,
    ))
    for index, result in enumerate(results):
        request_id = str(result.get("request_id") or f"{evidence_kind}_{index:04d}")[:128]
        rows = result.get("data") if isinstance(result.get("data"), list) else []
        fetched_at = None
        if result.get("fetched_at"):
            try:
                fetched_at = datetime.fromisoformat(str(result["fetched_at"]).replace("Z", "+00:00"))
            except ValueError:
                fetched_at = None
        db.add(AiAuditEvidenceResult(
            audit_job_id=job.id,
            organization_id=job.organization_id,
            client_id=job.client_id,
            evidence_kind=evidence_kind,
            request_id=request_id,
            hypothesis_id=str(result.get("hypothesis_id") or "")[:128] or None,
            capability_id=str(result.get("capability_id") or result.get("dimension") or "")[:64] or None,
            status=str(result.get("status") or "unavailable")[:32],
            result_json=_json_dump(result),
            rows_count=len(rows),
            fetched_at=fetched_at,
            expires_at=expires_at,
        ))
    db.flush()


def load_audit_evidence_results(
    db: Session,
    job: AiAuditJob,
    *,
    evidence_kind: str,
) -> list[dict[str, Any]]:
    rows = db.scalars(select(AiAuditEvidenceResult).where(
        AiAuditEvidenceResult.audit_job_id == job.id,
        AiAuditEvidenceResult.organization_id == job.organization_id,
        AiAuditEvidenceResult.client_id == job.client_id,
        AiAuditEvidenceResult.evidence_kind == evidence_kind,
        AiAuditEvidenceResult.expires_at > datetime.now(UTC),
    ).order_by(AiAuditEvidenceResult.created_at, AiAuditEvidenceResult.request_id)).all()
    return [
        item for row in rows
        if isinstance((item := _json_load(row.result_json, None)), dict)
    ]


def audit_evidence_references(db: Session, job: AiAuditJob) -> list[dict[str, Any]]:
    rows = db.scalars(select(AiAuditEvidenceResult).where(
        AiAuditEvidenceResult.audit_job_id == job.id,
        AiAuditEvidenceResult.organization_id == job.organization_id,
        AiAuditEvidenceResult.client_id == job.client_id,
        AiAuditEvidenceResult.expires_at > datetime.now(UTC),
    ).order_by(AiAuditEvidenceResult.created_at, AiAuditEvidenceResult.request_id)).all()
    return [{
        "evidenceKind": row.evidence_kind,
        "requestId": row.request_id,
        "hypothesisId": row.hypothesis_id,
        "capabilityId": row.capability_id,
        "status": row.status,
        "rowsCount": int(row.rows_count or 0),
        "fetchedAt": row.fetched_at.isoformat() if row.fetched_at else None,
    } for row in rows]
