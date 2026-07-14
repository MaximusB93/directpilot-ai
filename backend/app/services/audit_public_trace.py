from __future__ import annotations

import hashlib
from typing import Any

from app.models import DirectReportJob
from app.services.audit_evidence import parse_numeric_metric


SAFE_ERROR_MESSAGES = {
    "direct_auth_error": "Нужно переподключить аккаунт Яндекса.",
    "direct_permission_denied": "У аккаунта недостаточно прав для чтения этих данных.",
    "direct_rate_limited": "Яндекс временно ограничил частоту запросов.",
    "direct_report_processing": "Отчёт Яндекс.Директа ещё формируется.",
    "direct_report_failed": "Яндекс.Директ не сформировал отчёт.",
    "direct_invalid_field_combination": "Набор показателей не поддерживается для этого отчёта.",
    "direct_no_data": "За выбранный период данных нет.",
    "capability_not_supported": "Этот срез пока не поддерживается.",
    "capability_not_applicable": "Этот срез неприменим к типу кампании.",
    "hypothesis_type_capability_mismatch": "Запрос не соответствует проверяемой гипотезе.",
    "untrusted_fact_binding": "Гипотеза отклонена: нет доверенного исходного факта той же кампании.",
    "unknown_conversion_metric": "Данные по конверсиям отсутствуют или некорректны.",
    "saved_fallback_used": "Использованы сохранённые данные вместо live-отчёта.",
    "cache_miss": "Подходящих данных в кеше нет.",
    "provider_timeout": "AI-провайдер не ответил вовремя.",
    "json_schema_validation_failed": "Ответ AI не прошёл проверку формата.",
}

NUMERIC_KEYS = {
    "impressions", "clicks", "cost", "ctr", "avg_cpc", "cpc", "conversions",
    "goal_conversions", "cpa", "goal_cpa", "conversion_rate", "revenue", "roi",
}


def _trace_id(request_id: str) -> str:
    return f"trace_{hashlib.sha256(request_id.encode('utf-8')).hexdigest()[:12]}"


def _numeric_state_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"known": 0, "missing": 0, "invalid": 0}
    for row in rows:
        for key, value in row.items():
            if str(key).lower() not in NUMERIC_KEYS and not str(key).lower().startswith((
                "conversions_", "cost_per_conversion_", "conversion_rate_",
            )):
                continue
            counts[parse_numeric_metric(value).state] += 1
    return counts


def _source(result: dict[str, Any]) -> str:
    value = str(result.get("source") or "")
    if result.get("saved_fallback"):
        return "saved"
    if result.get("cached") or "cached" in value or "cache" in value:
        return "cached_live"
    if value.startswith("yandex_direct_live"):
        return "live"
    if "saved" in value:
        return "saved"
    return "unavailable" if result.get("status") in {"unavailable", "failed", "unsupported"} else "mixed"


def _status_history(
    status: str,
    *,
    report_job: DirectReportJob | None,
    fetched_at: str | None,
) -> list[dict[str, Any]]:
    created_at = report_job.created_at.isoformat() if report_job and report_job.created_at else None
    updated_at = report_job.updated_at.isoformat() if report_job and report_job.updated_at else fetched_at
    history = [{"status": "pending", "at": created_at}]
    if status == "processing" or (report_job and int(report_job.attempts or 0) > 0):
        history.append({"status": "processing", "at": updated_at})
    public_status = {
        "collected": "completed", "cached": "completed", "insufficient_data": "partial",
        "unsupported": "unavailable", "skipped_budget_limit": "unavailable",
    }.get(status, status)
    if public_status != "pending" and not (public_status == "processing" and history[-1]["status"] == "processing"):
        history.append({"status": public_status, "at": fetched_at or updated_at})
    unique = []
    for item in history:
        if not unique or unique[-1]["status"] != item["status"]:
            unique.append(item)
    return unique[-8:]


def build_public_audit_trace(
    snapshot: dict[str, Any],
    evidence_results: list[dict[str, Any]],
    report_jobs: list[DirectReportJob],
) -> dict[str, Any]:
    requests = {
        str(item.get("request_id")): item
        for item in (snapshot.get("validatedDataRequests") or [])
        if item.get("request_id")
    }
    for round_item in snapshot.get("investigationRounds") or []:
        for item in round_item.get("planned_requests") or []:
            if item.get("request_id"):
                requests.setdefault(str(item["request_id"]), item)
    for item in evidence_results:
        request_id = str(item.get("request_id") or "")
        if request_id and request_id not in requests:
            requests[request_id] = {
                "request_id": request_id,
                "hypothesis_id": item.get("hypothesis_id"),
                "campaign_name": item.get("campaign_name") or "Аккаунт",
                "dimension": item.get("capability_id") or item.get("dimension") or "validation",
                "capability_id": item.get("capability_id") or item.get("dimension"),
                "reason": "Backend проверил допустимость read-only запроса.",
                "expected_information_gain": "Не выполнять неподдерживаемый или недоверенный запрос.",
                "period": item.get("period") or {},
                "metrics": [],
                "required_for_conclusion": False,
                "data_preference": "live_required",
            }
    results = {str(item.get("request_id")): item for item in evidence_results if item.get("request_id")}
    samples = {
        str(item.get("request_id")): item for item in (snapshot.get("aiDrilldownSamples") or [])
        if item.get("request_id")
    }
    samples.update({
        str(item.get("request_id")): item for item in (snapshot.get("aiBaselineSamples") or [])
        if item.get("request_id")
    })
    jobs_by_hash = {str(item.request_hash): item for item in report_jobs if item.request_hash}
    jobs_by_capability = {str(item.capability_id): item for item in report_jobs}
    hypotheses = snapshot.get("hypothesisRegistry") or {}
    verifications = snapshot.get("verificationRegistry") or {}
    evidence = {
        str(item.get("request_id")): item for item in (snapshot.get("drilldownEvidenceSummaries") or [])
        if item.get("request_id")
    }
    round_by_hypothesis = {}
    for round_item in snapshot.get("investigationRounds") or []:
        for item in round_item.get("hypotheses") or []:
            round_by_hypothesis[str(item.get("hypothesis_id"))] = int(round_item.get("round_number") or 1)

    trace: list[dict[str, Any]] = []
    for request_id, request in requests.items():
        result = results.get(request_id, {})
        capability_id = str(request.get("capability_id") or request.get("dimension") or "")
        hypothesis_id = str(request.get("hypothesis_id") or "")
        hypothesis = hypotheses.get(hypothesis_id) or {}
        verification = verifications.get(hypothesis_id) or {}
        rows = result.get("data") if isinstance(result.get("data"), list) else []
        sample_rows = (samples.get(request_id) or {}).get("data") or []
        report_job = jobs_by_hash.get(str(result.get("request_hash") or "")) or jobs_by_capability.get(capability_id)
        status = str(result.get("status") or "pending")
        public_status = {
            "collected": "completed", "cached": "completed", "insufficient_data": "partial",
            "unsupported": "unavailable", "skipped_budget_limit": "unavailable",
        }.get(status, status)
        error_code = str(result.get("error_code") or result.get("live_error_code") or "") or None
        numeric_counts = _numeric_state_counts(rows)
        source = _source(result)
        fetched_at = str(result.get("fetched_at") or "") or None
        evidence_item = evidence.get(request_id) or {}
        matched_confirmation = (evidence_item.get("matched_confirmation_rules") or evidence_item.get("confirmation_rules") or [])[:5]
        matched_rejection = (evidence_item.get("matched_rejection_rules") or evidence_item.get("rejection_rules") or [])[:5]
        elapsed_ms = None
        if report_job and report_job.created_at and report_job.updated_at:
            elapsed_ms = max(0, int((report_job.updated_at - report_job.created_at).total_seconds() * 1000))
        trace.append({
            "publicTraceId": _trace_id(request_id),
            "roundNumber": round_by_hypothesis.get(hypothesis_id, 1),
            "hypothesisId": hypothesis_id,
            "hypothesisType": hypothesis.get("hypothesis_type") or "campaign_metadata_issue",
            "campaignName": request.get("campaign_name") or hypothesis.get("campaign_name") or "Аккаунт",
            "analysisLevel": request.get("dimension") or capability_id,
            "capabilityId": capability_id,
            "dimension": request.get("dimension") or capability_id,
            "reason": str(request.get("reason") or "Проверить данные для гипотезы.")[:500],
            "expectedInformationGain": str(request.get("expected_information_gain") or "Уточнить причину отклонения.")[:500],
            "requiredForConclusion": bool(request.get("required_for_conclusion")),
            "period": {
                "dateFrom": (request.get("period") or {}).get("date_from"),
                "dateTo": (request.get("period") or {}).get("date_to"),
            },
            "semanticMetrics": [str(item) for item in (request.get("metrics") or [])[:12]],
            "dataPreference": request.get("data_preference") or "live_preferred",
            "cachePolicy": (snapshot.get("metadata") or {}).get("cachePolicy") or "fresh",
            "source": source,
            "sourceType": result.get("source_type") or ("saved_stats" if source == "saved" else "report"),
            "status": public_status,
            "statusHistory": _status_history(status, report_job=report_job, fetched_at=fetched_at),
            "rowsReceived": int(result.get("rows_total") or len(rows)),
            "rowsNormalized": len(rows),
            "rowsAnalyzedByBackend": len(rows),
            "rowsSentToAi": len(sample_rows),
            "pagination": {
                "used": bool(report_job and int(report_job.pages_completed or 0) > 1),
                "pagesCompleted": int(report_job.pages_completed or 0) if report_job else 0,
                "rowsPerPage": int(report_job.limited_by or 0) if report_job else 0,
                "limitedBy": int(report_job.limited_by or 0) if report_job and report_job.limited_by else None,
                "hasMore": bool(report_job and report_job.status in {"queued", "processing"}),
            },
            "offlineReport": {
                "used": bool(report_job),
                "status": str(report_job.status) if report_job else None,
                "attempts": int(report_job.attempts or 0) if report_job else 0,
                "retryAfterSeconds": int(report_job.retry_after_seconds or 0) if report_job else 0,
            },
            "cache": {"hit": bool(result.get("cached")), "ageSeconds": None, "originalStatus": None},
            "fallback": {
                "used": bool(result.get("saved_fallback")),
                "type": "saved" if result.get("saved_fallback") else None,
                "reasonCode": "saved_fallback_used" if result.get("saved_fallback") else None,
            },
            "timing": {
                "startedAt": report_job.created_at.isoformat() if report_job and report_job.created_at else None,
                "completedAt": report_job.completed_at.isoformat() if report_job and report_job.completed_at else fetched_at,
                "elapsedMs": elapsed_ms,
            },
            "dataQuality": {
                "numericStateCounts": numeric_counts,
                "warnings": (["Часть числовых значений отсутствует или некорректна."] if numeric_counts["missing"] or numeric_counts["invalid"] else []),
            },
            "evidence": {
                "rowsAnalyzed": len(rows),
                "confirmationRules": matched_confirmation,
                "rejectionRules": matched_rejection,
                "limitations": list(evidence_item.get("data_quality_warnings") or [])[:5],
            },
            "verification": {
                "status": verification.get("status") or "unverified",
                "summary": str(verification.get("verification_summary") or "Проверка ещё не завершена.")[:500],
                "remainingDataNeeded": list(verification.get("remaining_data_needed") or [])[:8],
            },
            "nextStep": {
                "action": "stop" if verification.get("status") in {"confirmed", "rejected", "not_applicable"} else "request_more_data",
                "nextCapabilityId": (verification.get("remaining_data_needed") or [None])[0],
                "reason": "Достаточно данных." if verification.get("status") in {"confirmed", "rejected"} else "Требуется следующий доверенный срез данных.",
            },
            "safeError": {
                "code": error_code,
                "message": SAFE_ERROR_MESSAGES.get(error_code) if error_code else None,
                "retryable": bool(result.get("retryable")),
            },
        })

    for rejection in (snapshot.get("validationRejections") or [])[:20]:
        trace.append({
            "publicTraceId": _trace_id(f"rejected:{rejection.get('hypothesisId')}"),
            "roundNumber": 1,
            "hypothesisId": rejection.get("hypothesisId"),
            "hypothesisType": "campaign_metadata_issue",
            "campaignName": rejection.get("campaignName") or "Аккаунт",
            "analysisLevel": "validation",
            "capabilityId": None,
            "dimension": "validation",
            "reason": "Backend проверил привязку AI-гипотезы к trusted facts.",
            "expectedInformationGain": "Не выполнять недоверенный запрос.",
            "requiredForConclusion": False,
            "period": {}, "semanticMetrics": [], "dataPreference": "live_required", "cachePolicy": "fresh",
            "source": "unavailable", "sourceType": "saved_stats", "status": "rejected_by_validation",
            "statusHistory": [{"status": "rejected_by_validation", "at": None}],
            "rowsReceived": 0, "rowsNormalized": 0, "rowsAnalyzedByBackend": 0, "rowsSentToAi": 0,
            "pagination": {"used": False, "pagesCompleted": 0, "rowsPerPage": 0, "limitedBy": None, "hasMore": False},
            "offlineReport": {"used": False, "status": None, "attempts": 0, "retryAfterSeconds": 0},
            "cache": {"hit": False, "ageSeconds": None, "originalStatus": None},
            "fallback": {"used": False, "type": None, "reasonCode": None},
            "timing": {"startedAt": None, "completedAt": None, "elapsedMs": None},
            "dataQuality": {"numericStateCounts": {"known": 0, "missing": 0, "invalid": 0}, "warnings": []},
            "evidence": {"rowsAnalyzed": 0, "confirmationRules": [], "rejectionRules": [], "limitations": []},
            "verification": {"status": "unverified", "summary": rejection.get("message"), "remainingDataNeeded": []},
            "nextStep": {"action": "stop", "nextCapabilityId": None, "reason": "Запрос отклонён backend-валидатором."},
            "safeError": {"code": rejection.get("errorCode"), "message": SAFE_ERROR_MESSAGES.get(rejection.get("errorCode")), "retryable": False},
        })

    status_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    numeric_totals = {"known": 0, "missing": 0, "invalid": 0}
    for item in trace:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
        source_counts[item["source"]] = source_counts.get(item["source"], 0) + 1
        for key, value in item["dataQuality"]["numericStateCounts"].items():
            numeric_totals[key] += int(value or 0)
    diagnostics = {
        "planned": len(trace),
        "statusCounts": status_counts,
        "sourceCounts": source_counts,
        "rowsReceived": sum(item["rowsReceived"] for item in trace),
        "rowsAnalyzed": sum(item["rowsAnalyzedByBackend"] for item in trace),
        "rowsSentToAi": sum(item["rowsSentToAi"] for item in trace),
        "pagesLoaded": sum(item["pagination"]["pagesCompleted"] for item in trace),
        "offlineReports": sum(1 for item in trace if item["offlineReport"]["used"]),
        "cacheHits": sum(1 for item in trace if item["cache"]["hit"]),
        "savedFallbacks": sum(1 for item in trace if item["fallback"]["used"]),
    }
    return {
        "publicRequestTrace": trace[:100],
        "requestDiagnostics": diagnostics,
        "dataSourceSummary": source_counts,
        "dataQualitySummary": {"numericStateCounts": numeric_totals},
    }
