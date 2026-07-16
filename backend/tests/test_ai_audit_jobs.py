import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.services.ai_audit_jobs as audit_jobs
from app.api.routers.ai import chat_with_ai
from app.db import Base
from app.models import AiAuditJob, ClientAccount, DirectReportJob, Organization, User
from app.schemas import (
    AiAuditCreateRequest,
    AiAuditMeta,
    AiAuditResult,
    AiChatRequest,
    AuditDataRequestResult,
    AuditHypothesisVerification,
    AuditHypothesisVerificationSet,
    AuditNextRoundPlan,
)
from app.services.audit_evidence import evaluate_hypothesis_evidence
from app.core.config import normalize_ai_request_options, production_ai_model_ids, DEFAULT_PRODUCTION_AI_MODEL


def _db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    db.add_all(
        [
            Organization(id="org-a", name="A"),
            Organization(id="org-b", name="B"),
            User(id="user-a", organization_id="org-a", email="a@example.com", provider="email"),
            ClientAccount(id="client-a", organization_id="org-a", name="Client A", segment="Test", target_cpa=1000),
            ClientAccount(id="client-b", organization_id="org-b", name="Client B", segment="Test"),
        ]
    )
    db.commit()
    return db


def _context() -> dict:
    return {
        "client": {"id": "client-a", "name": "Client A", "direct_login": "login-a", "target_cpa": 1000},
        "business_context": {"status": "partial", "fields": {"business_niche": "hotel"}},
        "goals": {"selected_goal_ids": ["123"], "has_goal_data": True, "source_message": "Direct goals"},
        "summary": {
            "totals": {"cost": 5000, "clicks": 50, "goalConversions": 2, "goalCpa": 2500},
            "campaigns": [],
            "period": {"from": "2026-06-10", "to": "2026-07-09"},
        },
        "campaigns": [
            {
                "campaign_id": "1",
                "campaign_name": "Search",
                "severity": "critical",
                "cost": 5000,
                "clicks": 50,
                "goal_conversions": 0,
                "issue_flags": ["spend_without_conversions"],
            }
        ],
        "search_query_insights": {
            "totalQueries": 2,
            "insights": [{"query": "bad query", "cost": 1000, "goalConversions": 0}],
        },
        "campaign_dynamics_analysis": {
            "period": {
                "windows": {
                    "last30": {"dateFrom": "2026-06-10", "dateTo": "2026-07-09"},
                }
            },
            "dataQuality": {"rows": 30},
            "campaignDynamics": {
                "worstCampaigns": [{
                    "campaignName": "Search",
                    "severity": "critical",
                    "issueFlags": ["conversion_drop"],
                    "last7": {"cost": 5000, "clicks": 50, "goalConversions": 2, "goalCpa": 2500},
                    "previous7": {"cost": 4500, "clicks": 55, "goalConversions": 5, "goalCpa": 900},
                    "changes": {"last7VsPrevious7": {"goalConversionsDeltaPct": -60, "costDeltaPct": 11.11}},
                }],
                "bestCampaigns": [],
            },
            "missingData": [],
        },
        "yandex_direct_audit": {"score": 45, "grade": "D", "criticalIssues": [], "quickWins": []},
        "sync_diagnostics": {"hasGoalData": True},
        "optimization_plan": [],
        "warnings": [],
        "yandex_binding": {"access_token": "must-not-be-stored"},
    }


def _create(db: Session, client_id: str = "client-a") -> AiAuditJob:
    return audit_jobs.create_audit_job(
        db,
        AiAuditCreateRequest(
            client_id=client_id,
            model="qwen/qwen3-14b",
            ai_preset="balanced",
            max_tokens=2500,
            cache_policy="prefer_cache",
        ),
        organization_id="org-a",
        user_id="user-a",
        user_email="a@example.com",
    )


def _production_data_coverage() -> dict:
    return {
        "campaigns": {
            "available": 8,
            "analyzed": 8,
            "source": "yandex_direct_live",
            "period": {
                "dateFrom": "2026-06-15",
                "dateTo": "2026-07-14",
                "days": 30,
                "request_hash": "must-not-leak",
            },
            "limitations": ["Ограниченный срез", "Ограниченный срез", 123],
            "freshness": "live",
            "fetchedAt": "2026-07-14T13:33:51.497016+00:00",
            "requestId": "private-request-id",
        }
    }


def _structured_answer() -> str:
    return json.dumps(
        {
            "meta": {},
            "executive_summary": "Нужна ручная проверка дорогой кампании.",
            "data_quality": {"status": "sufficient", "facts": ["Есть 30 дней данных"], "limitations": []},
            "critical_findings": [
                {
                    "campaign_name": "Search",
                    "campaign_type": "search",
                    "analysis_level": "campaign",
                    "problem": "Расход без конверсий",
                    "fact": "Расход 5000 ₽, конверсий 0",
                    "evidence": ["50 кликов", "0 конверсий по цели"],
                    "hypothesis": "Нерелевантный трафик",
                    "confidence": "medium",
                    "risk": "high",
                    "recommendation": "Проверить поисковые запросы вручную",
                    "requires_human_approval": True,
                    "next_data_needed": [],
                }
            ],
            "opportunities": [],
            "insufficient_data_campaigns": [],
            "tracking_and_goals": {"status": "configured"},
            "drilldown_summary": {"analyzed_levels": ["campaign"], "not_analyzed_levels": ["keyword"], "next_data_needed": []},
            "action_plan": [
                {"priority": 1, "action": "Проверить запросы", "scope": "Search", "reason": "Нет конверсий", "mode": "manual_review", "requires_human_approval": True}
            ],
            "prohibited_actions": ["Не отключать кампанию автоматически"],
            "limitations": ["Ключевые фразы не собирались"],
            "conclusion": "Сначала проверить качество трафика.",
        },
        ensure_ascii=False,
    )


def _investigation_answer() -> str:
    return json.dumps({
        "hypotheses": [{
            "hypothesis_id": "model-id-is-replaced",
            "campaign_name": "Search",
            "campaign_family": "search",
            "campaign_subtype": "search",
            "observed_fact": "Расход без выбранных конверсий",
            "hypothesis": "Поисковые запросы могут быть нерелевантны",
            "current_status": "unverified",
            "data_requests": [{
                "request_id": "model-request-id-is-replaced",
                "hypothesis_id": "model-id-is-replaced",
                "campaign_name": "Search",
                "campaign_family": "search",
                "campaign_subtype": "search",
                "dimension": "search_queries",
                "reason": "Проверить интент запросов",
                "period": {"date_from": "2026-06-10", "date_to": "2026-07-09", "days": 30},
                "filters": {"campaign_name": "Search"},
                "metrics": ["query", "clicks", "cost", "conversions", "cpa"],
                "priority": "high",
                "required_for_conclusion": True,
            }],
        }]
    }, ensure_ascii=False)


def _verification_answer() -> str:
    return json.dumps({
        "verifications": [{
            "hypothesis_id": "hyp_001",
            "status": "confirmed",
            "verification_summary": "Запросы подтверждают гипотезу",
            "supporting_evidence": ["Высокий расход"],
            "contradicting_evidence": [],
            "limitations": [],
            "remaining_data_needed": [],
        }]
    }, ensure_ascii=False)


def test_trusted_result_data_coverage_normalizes_production_shape():
    snapshot = {
        "dataCoverage": {
            **_production_data_coverage(),
            "keywords": {"available": "unexpected", "total": "invalid", "analyzed": -2},
            "goals": {"available": "partial", "total": 1, "analyzed": "1"},
            "ignored": "not-an-item",
        }
    }

    coverage = audit_jobs.build_trusted_result_data_coverage(snapshot)
    campaigns = coverage["campaigns"]

    assert campaigns == {
        "available": True,
        "total": 8,
        "analyzed": 8,
        "source": "yandex_direct_live",
        "period": {"dateFrom": "2026-06-15", "dateTo": "2026-07-14", "days": 30},
        "reason": None,
        "limitations": ["Ограниченный срез"],
    }
    assert coverage["keywords"]["available"] is False
    assert coverage["keywords"]["total"] is None
    assert coverage["keywords"]["analyzed"] == 0
    assert coverage["goals"]["available"] is True
    assert "ignored" not in coverage
    AiAuditMeta.model_validate({"data_coverage": coverage})
    serialized = json.dumps(coverage, ensure_ascii=False)
    assert "freshness" not in serialized
    assert "fetchedAt" not in serialized
    assert "request_hash" not in serialized
    assert "private-request-id" not in serialized


def test_valid_provider_result_accepts_normalized_trusted_coverage(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["dataCoverage"] = _production_data_coverage()
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()
    calls = {"provider": 0}

    async def valid_provider(*args, **kwargs):
        calls["provider"] += 1
        return {
            "model": "deepseek/deepseek-chat",
            "content": _structured_answer(),
            "finish_reason": "stop",
        }

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", valid_provider)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    completed = asyncio.run(audit_jobs.advance_audit_job(db, generated.id, organization_id="org-a"))
    result = audit_jobs._json_load(completed.result_json, {})
    coverage = result["structured"]["meta"]["data_coverage"]["campaigns"]

    assert completed.status == "completed"
    assert calls["provider"] == 1
    assert result["backendFallbackUsed"] is False
    assert result["structured"] is not None
    assert coverage["available"] is True
    assert coverage["total"] == 8
    assert coverage["analyzed"] == 8
    assert "freshness" not in coverage
    assert "fetchedAt" not in coverage
    runtime = audit_jobs._json_load(completed.context_snapshot_json, {})["auditRuntime"]
    assert runtime["finalGenerationStatus"] == "provider_completed"


def test_internal_final_validation_error_is_not_exposed_publicly():
    db = _db()
    job = _create(db)
    with pytest.raises(ValidationError) as exc_info:
        AiAuditMeta.model_validate({
            "data_coverage": {
                "campaigns": {
                    "available": 8,
                    "freshness": "live",
                    "fetchedAt": "2026-07-14T13:33:51.497016+00:00",
                }
            }
        })

    failed = audit_jobs._save_failure(db, job, exc_info.value, stage="generate_answer")
    public = audit_jobs.audit_job_response(failed, db).model_dump(mode="json")
    public_dump = json.dumps(public, ensure_ascii=False)

    assert failed.error_code == "ai_audit_result_schema_error"
    assert public["error_message"] == "Не удалось сформировать итоговый структурированный отчёт. Собранные данные сохранены."
    assert "input_value=8" not in public_dump
    assert "errors.pydantic.dev" not in public_dump
    assert "validation errors for" not in public_dump
    assert "freshness" not in public_dump
    assert "fetchedAt" not in public_dump


def test_job_creation_and_organization_isolation():
    db = _db()
    job = _create(db)

    assert job.status == "queued"
    assert job.current_stage == "collect_context"
    assert job.expires_at is not None
    assert audit_jobs.get_audit_job(db, job.id, organization_id="org-a").id == job.id
    try:
        audit_jobs.get_audit_job(db, job.id, organization_id="org-b")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Cross-organization audit access was allowed")

    try:
        _create(db, "client-b")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Cross-organization client was accepted")


def test_compact_snapshot_has_expected_fields_and_no_secrets():
    snapshot = audit_jobs.build_compact_audit_context(_context())

    assert snapshot["accountTotals"]["cost"] == 5000
    assert snapshot["campaignGroups"]["critical"][0]["name"] == "Search"
    assert snapshot["selectedGoals"]["ids"] == ["123"]
    assert snapshot["metadata"]["campaignsIncluded"] == 1
    assert snapshot["metadata"]["estimatedTokens"] > 0
    assert snapshot["analysisPeriod"]["dateFrom"] == "2026-06-10"
    assert snapshot["analysisPeriod"]["days"] == 30
    assert snapshot["dataCoverage"]["campaigns"]["analyzed"] == 1
    assert snapshot["dataCoverage"]["keywords"]["reason"] == "not_collected"
    assert snapshot["periodComparison"]["worstCampaigns"][0]["last7"]["goalConversions"] == 2
    assert snapshot["periodComparison"]["worstCampaigns"][0]["changes"]["goalConversionsDeltaPct"] == -60
    assert "id" not in snapshot["campaignGroups"]["critical"][0]
    assert "campaign_id" not in audit_jobs._json_dump(snapshot)
    assert "must-not-be-stored" not in audit_jobs._json_dump(snapshot)


def test_staged_audit_has_separate_10000_token_budget_and_regular_cap_is_unchanged():
    db = _db()
    job = audit_jobs.create_audit_job(
        db,
        AiAuditCreateRequest(client_id="client-a", model="qwen/qwen3-14b", ai_preset="economy"),
        organization_id="org-a",
        user_id="user-a",
        user_email="a@example.com",
    )
    regular = normalize_ai_request_options(
        model="qwen/qwen3-14b",
        ai_preset="advanced",
        max_tokens=10000,
        models=production_ai_model_ids(),
        configured_default=DEFAULT_PRODUCTION_AI_MODEL,
        production_only=True,
    )
    assert job.max_tokens == 10000
    assert regular["max_tokens"] == 5000


def test_full_staged_flow_runs_planning_verification_and_final_answer(monkeypatch):
    db = _db()
    job = _create(db)
    monkeypatch.setattr(audit_jobs, "build_client_ai_context_from_db", lambda *args, **kwargs: _context())
    calls = {"count": 0}

    async def fake_generate(model, prompt, max_tokens, **kwargs):
        calls["count"] += 1
        if "Дополни безопасный read-only investigation plan" in prompt:
            assert model == audit_jobs.AI_AUDIT_HELPER_MODEL
            assert max_tokens == 1200
            assert kwargs["max_tokens_cap"] == 1200
            assert kwargs["timeout"] is audit_jobs.AUDIT_STAGE_PROVIDER_TIMEOUTS["create_investigation_plan"]
            return {"model": model, "content": _investigation_answer(), "usage": {"total_tokens": 100}, "id": "or-plan", "finish_reason": "stop"}
        if "Проверь максимум 5 гипотез" in prompt:
            assert model == audit_jobs.AI_AUDIT_HELPER_MODEL
            assert max_tokens == 1600
            assert kwargs["max_tokens_cap"] == 1600
            assert kwargs["timeout"] is audit_jobs.AUDIT_STAGE_PROVIDER_TIMEOUTS["verify_hypotheses"]
            assert "search_queries" in prompt
            return {"model": model, "content": _verification_answer(), "usage": {"total_tokens": 100}, "id": "or-verify", "finish_reason": "stop"}
        if "Plan the next read-only investigation round" in prompt:
            return {
                "model": model,
                    "content": json.dumps({
                        "continue_investigation": False,
                        "existing_hypothesis_requests": [],
                        "new_hypotheses": [],
                        "stop_reason": "enough_evidence",
                }),
                "usage": {"total_tokens": 50},
                "finish_reason": "stop",
            }
        assert model == job.model
        assert kwargs["max_tokens_cap"] == audit_jobs.FINAL_AUDIT_PROVIDER_MAX_TOKENS
        assert kwargs["timeout"] is audit_jobs.OPENROUTER_AUDIT_TIMEOUT
        assert "10000 токенов" not in prompt  # explicit test job uses 2500
        assert "не обрывай разделы" in prompt.lower()
        assert "не выводи campaignid" in prompt.lower()
        return {"model": model, "content": _structured_answer(), "usage": {"total_tokens": 500}, "id": "or-1", "finish_reason": "stop"}

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", fake_generate)

    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert (job.status, job.current_stage, job.progress_percent) == ("context_ready", "classify_campaigns", 15)
    assert "must-not-be-stored" not in (job.context_snapshot_json or "")
    assert audit_jobs._json_load(job.prompt_snapshot_json, {})["internalCampaignIds"] == ["1"]

    stages = []
    for _ in range(10):
        job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
        stages.append(job.current_stage)
        if job.status == "completed":
            break
    assert job.status == "completed"
    expected_order = [
        "create_investigation_plan", "validate_data_requests", "collect_live_data",
        "verify_hypotheses", "plan_next_investigation_round", "generate_answer", "finalize",
    ]
    cursor = -1
    for expected_stage in expected_order:
        cursor = stages.index(expected_stage, cursor + 1)
    assert audit_jobs._json_load(job.prompt_snapshot_json, {})["fullPromptStored"] is False
    assert job.answer_text.startswith("Период анализа: 10.06.2026–09.07.2026, 30 дней.")
    assert audit_jobs.audit_job_response(job).result["structured"]["critical_findings"][0]["campaign_name"] == "Search"
    assert audit_jobs.audit_job_response(job).result["safety"]["appliedToYandexDirect"] is False
    runtime = audit_jobs.audit_job_response(job).context_metadata["runtime"]
    assert calls["count"] == 4
    assert runtime["providerCallsCount"] == 4
    assert runtime["helperProviderCallsCount"] == 3
    assert runtime["finalProviderCallsCount"] == 1
    assert runtime["helperFallbacksCount"] == 0
    assert runtime["investigationRound"] == 1
    assert runtime["requestsCount"] >= 2
    assert runtime["policyVersion"] == "audit-evidence-v1"
    assert runtime["policyRequestsAdded"] > 0
    assert runtime["mandatoryRequirementsCount"] > 0
    assert runtime["plannerPromptTokensEstimated"] > 0
    assert runtime["verificationPromptTokensEstimated"] > 0
    snapshot = audit_jobs._json_load(job.context_snapshot_json, {})
    assert snapshot["investigationPlan"]["hypotheses"][0]["data_requests"][0]["request_id"] == "req_001_01"
    assert snapshot["verifiedHypotheses"][0]["status"] == "unverified"
    assert snapshot["auditModels"] == {
        "requested_model": job.model,
        "helper_model": audit_jobs.AI_AUDIT_HELPER_MODEL,
        "planner_returned_model": audit_jobs.AI_AUDIT_HELPER_MODEL,
        "verification_returned_model": audit_jobs.AI_AUDIT_HELPER_MODEL,
        "next_round_planner_returned_model": audit_jobs.AI_AUDIT_HELPER_MODEL,
        "final_returned_model": job.model,
    }
    assert job.returned_model == job.model


def test_helper_model_is_in_production_allowlist_and_planner_context_is_compact():
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["publicRequestTrace"] = [{"reason": "frontend-only-trace"}]
    snapshot["campaignClassifications"] = audit_jobs.classify_audit_campaigns(snapshot)
    base_plan = audit_jobs.build_rule_based_investigation_plan(snapshot)
    snapshot["ruleBasedInvestigationPlan"] = base_plan.model_dump(mode="json")
    planner_context = audit_jobs.build_investigation_planner_context(snapshot)
    serialized = audit_jobs._json_dump(planner_context)

    assert audit_jobs.AI_AUDIT_HELPER_MODEL in production_ai_model_ids()
    assert audit_jobs.should_call_ai_investigation_planner(base_plan, snapshot) is True
    assert audit_jobs.estimate_tokens(serialized) < 4000
    assert "directLogin" not in serialized
    assert "login-a" not in serialized
    assert set(planner_context) == {
        "analysisPeriod", "accountTotals", "targetKpis", "campaigns",
        "campaignClassifications", "dataCoverage", "ruleBasedInvestigationPlan",
        "publicToolManifest", "missingData", "trackingWarnings", "observedFacts",
        "directApiKnowledgeVersion", "capabilityDescriptions",
    }
    for excluded in ("businessContext", "auditFramework", "draftActions", "periodComparison", "searchQueryRisks"):
        assert excluded not in serialized
    assert "frontend-only-trace" not in serialized


@pytest.mark.parametrize("failure_mode", ["timeout", "rate_limit", "provider_error", "invalid_json"])
def test_planner_failure_uses_rule_based_fallback_and_continues(monkeypatch, failure_mode):
    db = _db()
    job = _create(db)
    monkeypatch.setattr(audit_jobs, "build_client_ai_context_from_db", lambda *args, **kwargs: _context())
    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert job.current_stage == "create_investigation_plan"

    async def failed_planner(model, prompt, max_tokens, **kwargs):
        assert model == audit_jobs.AI_AUDIT_HELPER_MODEL
        assert max_tokens == audit_jobs.AI_AUDIT_PLANNER_MAX_TOKENS
        if failure_mode == "timeout":
            raise HTTPException(status_code=504, detail={"error_code": "openrouter_timeout", "retryable": True})
        if failure_mode == "rate_limit":
            raise HTTPException(status_code=429, detail={"error_code": "openrouter_rate_limited", "retryable": True})
        if failure_mode == "provider_error":
            raise RuntimeError("provider unavailable")
        return {"model": model, "content": "not-json", "usage": {"completion_tokens": 3}}

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", failed_planner)
    continued = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))

    assert continued.status == "context_ready"
    assert continued.current_stage == "validate_data_requests"
    assert continued.error_code is None
    snapshot = audit_jobs._json_load(continued.context_snapshot_json, {})
    assert snapshot["investigationPlan"] == snapshot["ruleBasedInvestigationPlan"]
    assert snapshot["helperStages"]["planner"]["status"] == "fallback"
    assert snapshot["helperStages"]["planner"]["warningCode"] == "planner_fallback_used"
    assert snapshot["auditRuntime"]["helperFallbacksCount"] == 1
    assert snapshot["auditRuntime"]["helperProviderCallsCount"] == 1
    if failure_mode == "invalid_json":
        assert snapshot["helperStages"]["planner"]["parsing"]["errorCode"] == "json_parse_failed"


def test_planner_total_timeout_uses_fallback_instead_of_failing_job(monkeypatch):
    db = _db()
    job = _create(db)
    monkeypatch.setattr(audit_jobs, "build_client_ai_context_from_db", lambda *args, **kwargs: _context())
    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))

    async def slow_planner(*args, **kwargs):
        await asyncio.sleep(0.05)
        return {"model": audit_jobs.AI_AUDIT_HELPER_MODEL, "content": _investigation_answer()}

    monkeypatch.setitem(audit_jobs.AUDIT_STAGE_TOTAL_TIMEOUT_SECONDS, "create_investigation_plan", 0.001)
    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", slow_planner)
    continued = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))

    assert continued.status == "context_ready"
    assert continued.current_stage == "validate_data_requests"
    snapshot = audit_jobs._json_load(continued.context_snapshot_json, {})
    assert snapshot["helperStages"]["planner"]["warningCode"] == "planner_fallback_used"


def test_planner_is_skipped_when_no_investigation_is_needed(monkeypatch):
    context = _context()
    context["campaigns"][0].update({"severity": "ok", "goal_conversions": 2, "issue_flags": []})
    db = _db()
    job = _create(db)
    monkeypatch.setattr(audit_jobs, "build_client_ai_context_from_db", lambda *args, **kwargs: context)

    async def forbidden_provider(*args, **kwargs):
        raise AssertionError("Planner provider must be skipped")

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", forbidden_provider)
    skipped = job
    for _ in range(4):
        skipped = asyncio.run(audit_jobs.advance_audit_job(db, skipped.id, organization_id="org-a"))
        if skipped.current_stage == "validate_data_requests":
            break

    assert skipped.current_stage == "validate_data_requests"
    snapshot = audit_jobs._json_load(skipped.context_snapshot_json, {})
    assert snapshot["helperStages"]["planner"]["status"] == "skipped_not_needed"
    assert snapshot["auditRuntime"]["providerCallsCount"] == 0


def test_ai_next_round_creates_device_child_after_rejected_query_hypothesis():
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30},
        "auditRuntime": {"investigationRound": 1, "requestsCount": 1},
        "investigationPlan": {"hypotheses": [{
            "hypothesis_id": "hyp-1",
            "hypothesis_type": "search_query_waste",
            "campaign_name": "Search Brand",
            "campaign_family": "search",
            "campaign_subtype": "search",
            "hypothesis": "Search queries may explain high CPA.",
            "forbidden_capabilities": [],
        }]},
        "verifiedHypotheses": [{
            "hypothesis_id": "hyp-1",
            "status": "rejected",
            "remaining_data_needed": ["devices"],
        }],
        "validatedDataRequests": [{
            "hypothesis_id": "hyp-1", "capability_id": "search_queries",
        }],
    }
    plan = AuditNextRoundPlan.model_validate({
        "continue_investigation": True,
        "existing_hypothesis_requests": [],
        "new_hypotheses": [{
            "hypothesis_id": "hyp-2",
            "hypothesis_type": "device_segment_gap",
            "parent_hypothesis_id": "hyp-1",
            "campaign_name": "Search Brand",
            "hypothesis": "Mobile traffic may explain high CPA.",
            "rationale": "The search-query hypothesis was rejected.",
            "required_capabilities": ["devices"],
            "confirmation_rule_codes": ["devices_cpa_segment_gap"],
            "requests": [],
        }],
        "stop_reason": None,
    })

    accepted, rejected = audit_jobs._next_round_requests_from_plan(snapshot, plan)

    assert rejected == []
    assert [item.capability_id for item in accepted] == ["devices"]
    assert accepted[0].hypothesis_id == "hyp-2"
    assert accepted[0].request_id == "req_r2_001"
    registry = snapshot["hypothesisRegistry"]
    assert registry["hyp-1"]["hypothesis"] == "Search queries may explain high CPA."
    assert registry["hyp-2"]["parent_hypothesis_id"] == "hyp-1"
    assert snapshot["activeHypothesisIds"] == ["hyp-2"]


def test_hypothesis_registry_keeps_rejected_parent_and_activates_child():
    hypotheses = [
        {
            "hypothesis_id": f"hyp-{index}",
            "hypothesis_type": "search_query_waste",
            "campaign_name": f"Search {index}",
            "campaign_family": "search",
            "campaign_subtype": "search",
            "hypothesis": f"Hypothesis {index}",
            "current_status": "rejected" if index == 1 else "unverified",
            "forbidden_capabilities": [],
        }
        for index in range(1, 6)
    ]
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30},
        "auditRuntime": {"investigationRound": 1, "requestsCount": 5},
        "investigationPlan": {"hypotheses": hypotheses},
        "verifiedHypotheses": [
            {"hypothesis_id": item["hypothesis_id"], "status": item["current_status"]}
            for item in hypotheses
        ],
        "validatedDataRequests": [],
        "investigationRounds": [{
            "round_number": 1,
            "hypotheses": [{**item, "status": item["current_status"]} for item in hypotheses],
            "verification_results": [],
            "completed_at": None,
            "stop_reason": None,
        }],
    }
    plan = AuditNextRoundPlan.model_validate({
        "continue_investigation": True,
        "existing_hypothesis_requests": [],
        "new_hypotheses": [{
            "hypothesis_id": "hyp-child",
            "hypothesis_type": "device_segment_gap",
            "parent_hypothesis_id": "hyp-1",
            "campaign_name": "Search 1",
            "hypothesis": "Device mix may explain the deviation.",
            "rationale": "The parent cause was rejected by trusted evidence.",
            "required_capabilities": ["devices"],
            "requests": [],
        }],
        "stop_reason": None,
    })

    accepted, rejected = audit_jobs._next_round_requests_from_plan(snapshot, plan)
    audit_jobs._apply_next_round_requests(snapshot, accepted)

    assert rejected == []
    assert len(snapshot["hypothesisRegistry"]) == 6
    assert len(snapshot["activeHypothesisIds"]) <= 5
    assert "hyp-child" in snapshot["activeHypothesisIds"]
    assert snapshot["hypothesisRegistry"]["hyp-1"]["current_status"] == "rejected"
    assert snapshot["investigationRounds"][0]["hypotheses"][0]["status"] == "rejected"
    assert snapshot["investigationRounds"][1]["hypotheses"][0]["hypothesis_id"] == "hyp-child"
    prompt = audit_jobs.build_verification_prompt(snapshot)
    assert "hyp-child" in prompt
    assert '"hypothesis_id": "hyp-1"' not in prompt


def test_existing_follow_up_for_another_cause_is_rejected():
    hypothesis = {
        "hypothesis_id": "hyp-query",
        "hypothesis_type": "search_query_waste",
        "campaign_name": "Search Brand",
        "campaign_family": "search",
        "campaign_subtype": "search",
        "hypothesis": "Query quality may explain CPA.",
        "current_status": "unverified",
        "required_capabilities": ["search_queries"],
        "optional_capabilities": [],
        "confirmation_rule_codes": ["search_queries_waste_without_goals"],
        "rejection_rule_codes": ["search_queries_no_material_waste"],
        "forbidden_capabilities": [],
        "data_requests": [],
    }
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30},
        "auditRuntime": {"investigationRound": 1, "requestsCount": 1},
        "investigationPlan": {"hypotheses": [hypothesis]},
        "verifiedHypotheses": [{"hypothesis_id": "hyp-query", "status": "unverified"}],
        "validatedDataRequests": [{"hypothesis_id": "hyp-query", "capability_id": "search_queries"}],
    }
    plan = AuditNextRoundPlan.model_validate({
        "continue_investigation": True,
        "existing_hypothesis_requests": [{
            "hypothesis_id": "hyp-query",
            "capability_id": "devices",
            "reason": "Compare device efficiency.",
            "expected_information_gain": "A material CPA gap would change the causal conclusion.",
            "required_for_conclusion": True,
        }],
        "new_hypotheses": [],
        "stop_reason": None,
    })

    accepted, rejected = audit_jobs._next_round_requests_from_plan(snapshot, plan)
    canonical = snapshot["hypothesisRegistry"]["hyp-query"]

    assert accepted == []
    assert rejected[0].error_code == "hypothesis_type_capability_mismatch"
    assert canonical["required_capabilities"] == ["search_queries"]
    assert "devices_cpa_segment_gap" not in canonical["confirmation_rule_codes"]


def test_new_hypothesis_without_parent_or_trusted_facts_is_rejected():
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30},
        "auditRuntime": {"investigationRound": 1, "requestsCount": 0},
        "investigationPlan": {"hypotheses": []},
        "observedFacts": [],
        "validatedDataRequests": [],
    }
    plan = AuditNextRoundPlan.model_validate({
        "continue_investigation": True,
        "existing_hypothesis_requests": [],
        "new_hypotheses": [{
            "hypothesis_id": "hyp-unbound",
            "hypothesis_type": "device_segment_gap",
            "campaign_name": "Search Brand",
            "hypothesis": "Device mix may explain the deviation.",
            "rationale": "Model-only idea without trusted binding.",
            "required_capabilities": ["devices"],
            "requests": [],
        }],
        "stop_reason": None,
    })

    accepted, rejected = audit_jobs._next_round_requests_from_plan(snapshot, plan)

    assert accepted == []
    assert rejected[0].error_code == "untrusted_fact_binding"
    assert "hyp-unbound" not in snapshot.get("hypothesisRegistry", {})


def test_child_with_parent_cannot_bind_unknown_fact_id():
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30},
        "auditRuntime": {"investigationRound": 1, "requestsCount": 0},
        "investigationPlan": {"hypotheses": [{
            "hypothesis_id": "hyp-parent",
            "hypothesis_type": "search_query_waste",
            "campaign_name": "Search Brand",
            "campaign_family": "search",
            "campaign_subtype": "search",
            "hypothesis": "Query waste may explain CPA.",
            "fact_ids": ["fact-trusted"],
            "forbidden_capabilities": [],
        }]},
        "observedFacts": [{
            "fact_id": "fact-trusted", "campaign_name": "Search Brand", "sufficient_data": True,
        }],
        "validatedDataRequests": [],
    }
    plan = AuditNextRoundPlan.model_validate({
        "continue_investigation": True,
        "existing_hypothesis_requests": [],
        "new_hypotheses": [{
            "hypothesis_id": "hyp-child",
            "hypothesis_type": "device_segment_gap",
            "parent_hypothesis_id": "hyp-parent",
            "fact_ids": ["fact-invented"],
            "campaign_name": "Search Brand",
            "hypothesis": "Device mix may explain CPA.",
            "rationale": "Check another cause.",
            "required_capabilities": ["devices"],
            "requests": [],
        }],
        "stop_reason": None,
    })

    accepted, rejected = audit_jobs._next_round_requests_from_plan(snapshot, plan)

    assert accepted == []
    assert rejected[0].error_code == "untrusted_fact_binding"


def test_full_drilldown_evidence_is_not_limited_by_ai_sample_budget():
    rows = [
        {
            "query": f"query-{index}-" + ("x" * 180),
            "impressions": 100,
            "clicks": 25,
            "cost": 10,
            "conversions": 0,
        }
        for index in range(1200)
    ]
    full_result = {
        "request_id": "req-query",
        "hypothesis_id": "hyp-query",
        "capability_id": "search_queries",
        "dimension": "search_queries",
        "status": "collected",
        "source": "yandex_direct_live_report",
        "rows_analyzed": 1200,
        "rows_total": 1200,
        "data": rows,
    }
    snapshot = {
        "analysisPeriod": {"days": 30},
        "targetKpis": {"targetCpa": 5},
    }
    db = _db()
    job = _create(db)
    audit_jobs._save_full_drilldown_results(db, job, [full_result])

    audit_jobs._refresh_drilldown_projections(snapshot, [full_result])
    sample = snapshot["aiDrilldownSamples"][0]
    summary = snapshot["drilldownEvidenceSummaries"][0]
    backend = evaluate_hypothesis_evidence(
        {
            "hypothesis_id": "hyp-query",
            "hypothesis_type": "search_query_waste",
            "confirmation_rule_codes": ["search_queries_waste_without_goals"],
            "rejection_rule_codes": ["search_queries_no_material_waste"],
        },
        [{
            "request_id": "req-query",
            "hypothesis_id": "hyp-query",
            "capability_id": "search_queries",
            "required_for_conclusion": True,
        }],
        [full_result],
        target_cpa=5,
        period_days=30,
    )

    assert sample["ai_sample_rows"] < 1200
    assert len(audit_jobs._load_full_drilldown_results(db, job)[0]["data"]) == 1200
    assert "fullDrilldownResults" not in (job.prompt_snapshot_json or "")
    assert sample["rows_analyzed"] == 1200
    assert summary["rows_total"] == 1200
    assert summary["metrics"]["cost"] == 12000
    assert summary["segments"] == 1200
    assert backend["evidence_summaries"][0]["rows_total"] == 1200
    assert backend["matched_confirmation_rules"][0]["result"]["matching_rows"] == 1200


def test_verification_registry_preserves_prior_round_and_filters_active_prompt():
    snapshot = {
        "hypothesisRegistry": {
            "hyp-001": {"hypothesis_id": "hyp-001", "hypothesis": "First", "current_status": "unverified"},
            "hyp-006": {"hypothesis_id": "hyp-006", "hypothesis": "Child", "current_status": "unverified"},
        },
        "activeHypothesisIds": ["hyp-001"],
        "investigationPlan": {"hypotheses": []},
        "drilldownEvidenceSummaries": [
            {"hypothesis_id": "hyp-001", "marker": "old-summary"},
            {"hypothesis_id": "hyp-006", "marker": "active-summary"},
        ],
        "aiDrilldownSamples": [
            {"hypothesis_id": "hyp-001", "marker": "old-sample"},
            {"hypothesis_id": "hyp-006", "marker": "active-sample"},
        ],
    }
    audit_jobs._apply_verification_statuses(snapshot, AuditHypothesisVerificationSet(
        verifications=[AuditHypothesisVerification(
            hypothesis_id="hyp-001", status="confirmed", verification_summary="Confirmed in round one.",
        )],
    ))
    snapshot["activeHypothesisIds"] = ["hyp-006"]
    audit_jobs._sync_active_investigation_plan(snapshot)
    audit_jobs._apply_verification_statuses(snapshot, AuditHypothesisVerificationSet(
        verifications=[AuditHypothesisVerification(
            hypothesis_id="hyp-006", status="unverified", verification_summary="Needs more data.",
        )],
    ))

    assert snapshot["verificationRegistry"]["hyp-001"]["status"] == "confirmed"
    assert snapshot["verificationRegistry"]["hyp-006"]["status"] == "unverified"
    assert [item["hypothesis_id"] for item in snapshot["activeVerifications"]] == ["hyp-006"]
    prompt = audit_jobs.build_verification_prompt(snapshot)
    assert "hyp-006" in prompt and "active-summary" in prompt and "active-sample" in prompt
    assert "hyp-001" not in prompt and "old-summary" not in prompt and "old-sample" not in prompt

    safe_result = audit_jobs._enforce_verified_result({
        "critical_findings": [{
            "hypothesis_id": "hyp-001",
            "hypothesis": "First",
            "recommendation": "Review manually",
            "next_data_needed": [],
        }],
        "opportunities": [],
        "action_plan": [],
        "limitations": [],
    }, snapshot)
    assert safe_result["critical_findings"][0]["verification_status"] == "confirmed"

    db = _db()
    job = _create(db)
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()
    public_registry = audit_jobs.audit_job_response(job, db).context_metadata["verificationRegistryPublic"]
    assert {item["hypothesisId"]: item["status"] for item in public_registry} == {
        "hyp-001": "confirmed", "hyp-006": "unverified",
    }


def test_rejected_verification_is_immutable_in_registry_and_active_round():
    snapshot = {
        "hypothesisRegistry": {
            "hyp-001": {"hypothesis_id": "hyp-001", "hypothesis": "First", "current_status": "rejected"},
        },
        "activeHypothesisIds": ["hyp-001"],
        "verificationRegistry": {
            "hyp-001": {"hypothesis_id": "hyp-001", "status": "rejected", "verification_summary": "Rejected."},
        },
        "investigationPlan": {"hypotheses": []},
        "investigationRounds": [{
            "hypotheses": [{"hypothesis_id": "hyp-001", "status": "rejected"}],
        }],
    }
    audit_jobs._apply_verification_statuses(snapshot, AuditHypothesisVerificationSet(
        verifications=[AuditHypothesisVerification(
            hypothesis_id="hyp-001", status="confirmed", verification_summary="Model tried to reopen.",
        )],
    ))

    assert snapshot["verificationRegistry"]["hyp-001"]["status"] == "rejected"
    assert snapshot["activeVerifications"][0]["status"] == "rejected"
    assert snapshot["investigationRounds"][0]["hypotheses"][0]["status"] == "rejected"


def test_live_source_wording_does_not_claim_saved_snapshot():
    prompt = audit_jobs.build_full_audit_prompt({
        "analysisPeriod": {"source": "yandex_direct_live_report"},
        "metadata": {},
    })

    assert "fresh report" in prompt
    assert "сохранённая read-only статистика" not in prompt


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0), ("", 0), ("--", 0), ("—", 0), ("0", 0), ("0,5", 0.5), ("1 250,75", 1250.75)],
)
def test_audit_numeric_parsing_is_resilient(value, expected):
    assert audit_jobs._number_or_zero(value) == expected


def test_valid_next_round_stop_does_not_require_backend_fallback():
    plan, valid, parsing = audit_jobs._parse_next_round_plan(json.dumps({
        "continue_investigation": False,
        "existing_hypothesis_requests": [],
        "new_hypotheses": [],
        "stop_reason": "low_data",
    }))

    assert valid is True
    assert parsing["status"] == "success"
    assert plan is not None and plan.stop_reason == "low_data"


def test_planner_docs_lookup_is_local_bounded_and_non_executing(monkeypatch):
    calls = []

    def fake_lookup(query):
        calls.append(query)
        return {
            "knowledge_version": "test-v1",
            "matches": [{"capability_id": "devices", "supported_now": True}],
            "executable": False,
        }

    monkeypatch.setattr(audit_jobs, "search_direct_api_docs", fake_lookup)
    snapshot = {
        "auditRuntime": {"investigationRound": 1},
        "investigationPlan": {"hypotheses": [
            {"hypothesis_id": "hyp-1", "campaign_subtype": "search", "hypothesis": "First"},
            {"hypothesis_id": "hyp-2", "campaign_subtype": "search", "hypothesis": "Second"},
            {"hypothesis_id": "hyp-3", "campaign_subtype": "search", "hypothesis": "Third"},
        ]},
        "verifiedHypotheses": [
            {"hypothesis_id": "hyp-1", "status": "unverified"},
            {"hypothesis_id": "hyp-2", "status": "rejected"},
            {"hypothesis_id": "hyp-3", "status": "partially_confirmed"},
        ],
    }

    knowledge = audit_jobs._planner_docs_lookup(snapshot)

    assert len(calls) == 2
    assert len(knowledge) == 1
    assert knowledge[0]["capability_id"] == "devices"
    assert knowledge[0]["permitted_metrics"]
    trace = snapshot["docsLookupTrace"][-1]["lookups"]
    assert len(trace) == 2
    assert all(item["apiExecuted"] is False for item in trace)
    assert all("query" not in item for item in trace)
    prompt = audit_jobs.build_next_round_prompt(snapshot)
    assert '"local_documentation"' in prompt
    assert '"permitted_metrics"' in prompt
    assert len(calls) == 4  # two bounded lookups per planner invocation


def test_fresh_baseline_is_live_required_and_never_silently_uses_saved_campaigns():
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30},
        "campaignGroups": {"critical": [{"name": "Saved campaign", "cost": 9999}]},
        "accountTotals": {"cost": 9999, "clicks": 100},
    }
    requests = audit_jobs._fresh_baseline_requests(snapshot)
    assert {item.capability_id for item in requests} == {"campaigns", "campaign_performance"}
    assert all(item.data_preference == "live_required" for item in requests)
    assert all(item.campaign_name == "__all_campaigns__" for item in requests)

    audit_jobs._apply_live_baseline(
        snapshot,
        [
            {"capability_id": "campaigns", "status": "failed", "error_code": "direct_unavailable"},
            {"capability_id": "campaign_performance", "status": "failed", "error_code": "direct_unavailable"},
        ],
        allow_saved_fallback=False,
    )

    assert snapshot["freshBaseline"]["status"] == "partial"
    assert snapshot["freshBaseline"]["savedFallbackUsed"] is False
    assert snapshot["campaignGroups"]["critical"] == []
    assert snapshot["accountTotals"]["cost"] == 0


def test_fresh_baseline_with_150_campaigns_is_recompacted_with_full_aggregates():
    rows = [
        {
            "campaign_name": f"Campaign {index}", "cost": 1000 + index,
            "clicks": 40, "impressions": 2000, "conversions_123_auto": 0,
        }
        for index in range(150)
    ]
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30},
        "targetKpis": {"targetCpa": 500},
        "selectedGoals": {"ids": ["123"], "hasGoalData": False},
        "metadata": {"tokenTarget": audit_jobs.CONTEXT_TOKEN_TARGET},
    }

    audit_jobs._apply_live_baseline(
        snapshot,
        [
            {"capability_id": "campaigns", "status": "collected", "data": []},
            {"capability_id": "campaign_performance", "status": "collected", "data": rows},
        ],
        allow_saved_fallback=False,
    )

    assert snapshot["metadata"]["campaignsTotal"] == 150
    assert snapshot["metadata"]["campaignsIncluded"] <= 25
    assert snapshot["metadata"]["estimatedTokens"] <= audit_jobs.CONTEXT_TOKEN_TARGET
    assert snapshot["freshBaseline"]["campaignAggregates"]["campaignsTotal"] == 150
    assert len(snapshot["campaignAnalysisRows"]) == 150
    assert snapshot["dataCoverage"]["campaigns"]["analyzed"] == 150
    assert snapshot["dataCoverage"]["campaigns"]["source"] == "yandex_direct_live_report"
    assert snapshot["analysisPeriod"]["source"] == "yandex_direct_live_report"


def test_api_campaign_type_wins_when_name_is_unknown_and_conflict_is_explicit():
    api_classified = audit_jobs._campaign_classification("Campaign 1", {
        "type": "UNIFIED_CAMPAIGN",
        "unified_campaign": {"bidding_strategy": {
            "search": {"bidding_strategy_type": "SERVING_OFF"},
            "network": {"bidding_strategy_type": "AVERAGE_CPA"},
        }},
    })
    conflict = audit_jobs._campaign_classification("Search Brand", {
        "type": "TEXT_CAMPAIGN",
        "text_campaign": {"bidding_strategy": {
            "search": {"bidding_strategy_type": "SERVING_OFF"},
            "network": {"bidding_strategy_type": "AVERAGE_CPA"},
        }},
    })

    assert api_classified["campaign_family"] == "yan"
    assert api_classified["classification_source"] == "direct_api_strategy"
    assert conflict["campaign_family"] == "unknown"
    assert conflict["classification_source"] == "api_name_conflict"
    assert conflict["warnings"]


def test_text_and_unified_mixed_campaigns_use_current_strategy_metadata():
    text_search = audit_jobs._campaign_classification("Campaign 1", {
        "type": "TEXT_CAMPAIGN",
        "text_campaign": {"bidding_strategy": {
            "search": {"bidding_strategy_type": "AVERAGE_CPA"},
            "network": {"bidding_strategy_type": "SERVING_OFF"},
        }},
    })
    unified_mixed = audit_jobs._campaign_classification("РСЯ prospecting", {
        "type": "UNIFIED_CAMPAIGN",
        "unified_campaign": {"bidding_strategy": {
            "search": {"bidding_strategy_type": "AVERAGE_CPA"},
            "network": {"bidding_strategy_type": "AVERAGE_CPA"},
        }},
    })

    assert text_search["campaign_family"] == "search"
    assert text_search["classification_source"] == "direct_api_strategy"
    assert unified_mixed["campaign_family"] == "unknown"
    assert unified_mixed["classification_source"] == "direct_api_mixed"
    assert unified_mixed["warnings"]


def test_initial_planner_cannot_add_independent_hypothesis():
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30},
        "targetKpis": {"targetCpa": 500},
        "campaignGroups": {
            "critical": [{
                "name": "Search Brand", "cost": 5000, "clicks": 80, "impressions": 5000,
                "goalConversions": 0, "flags": ["spend_without_conversions"],
                "diagnostic": "Spend without selected-goal conversions.",
            }],
            "warning": [], "opportunity": [], "low_data": [], "stable": [],
        },
        "campaignClassifications": [{
            "campaign_name": "Search Brand", "campaign_family": "search",
            "campaign_subtype": "brand_search", "classification_source": "name_fallback",
        }],
        "observedFacts": [{
            "fact_id": "fact-1", "campaign_name": "Search Brand", "metric": "spend_without_goal_conversions",
            "sufficient_data": True,
        }],
    }
    fallback = audit_jobs.build_rule_based_investigation_plan(snapshot)
    first = fallback.hypotheses[0].model_copy(update={"fact_ids": ["fact-1"]})
    proposed = audit_jobs.AuditInvestigationPlan(hypotheses=[
        first.model_copy(update={"hypothesis": "Search-query intent is weak."}),
        first.model_copy(update={
            "hypothesis_id": "hyp_device",
            "hypothesis": "Mobile device traffic may be inefficient.",
        }),
    ])

    merged = audit_jobs._merge_investigation_plans(proposed, snapshot, fallback)

    assert len(merged.hypotheses) == 1
    assert merged.hypotheses[0].hypothesis_id == first.hypothesis_id
    assert snapshot["validationRejections"][0]["status"] == "rejected_by_validation"
    assert snapshot["validationRejections"][0]["errorCode"] == "untrusted_fact_binding"


def test_initial_planner_rejects_cross_campaign_fact_binding():
    snapshot = {
        "analysisPeriod": {"days": 30},
        "campaignGroups": {"critical": [{
            "name": "Campaign A", "cost": 5000, "clicks": 80, "impressions": 5000,
            "goalConversions": 0, "flags": ["spend_without_conversions"],
        }], "warning": [], "opportunity": [], "low_data": [], "stable": []},
        "campaignClassifications": [{
            "campaign_name": "Campaign A", "campaign_family": "search", "campaign_subtype": "search",
        }],
        "observedFacts": [{
            "fact_id": "fact-a", "campaign_name": "Campaign A",
            "metric": "spend_without_goal_conversions", "sufficient_data": True,
        }],
    }
    fallback = audit_jobs.build_rule_based_investigation_plan(snapshot)
    base = fallback.hypotheses[0]
    proposed = audit_jobs.AuditInvestigationPlan(hypotheses=[
        base.model_copy(update={"campaign_name": "Campaign B", "fact_ids": ["fact-a"]}),
    ])

    merged = audit_jobs._merge_investigation_plans(proposed, snapshot, fallback)

    assert merged.hypotheses[0].campaign_name == "Campaign A"
    assert merged.hypotheses[0].fact_ids == ["fact-a"]
    assert snapshot["validationRejections"] == [{
        "hypothesisId": base.hypothesis_id,
        "campaignName": "Campaign B",
        "status": "rejected_by_validation",
        "errorCode": "untrusted_fact_binding",
        "message": "AI-гипотеза отклонена backend-валидатором: отсутствует trusted fact той же кампании.",
    }]


def test_fresh_baseline_advance_uses_all_rows_but_limits_ai_sample(monkeypatch):
    db = _db()
    job = _create(db)
    rows = [{
        "campaign_name": f"Campaign {index}",
        "cost": index + 1,
        "clicks": 30,
        "impressions": 1000,
        "conversions_123_auto": 0,
        "provider_note": "x" * 1000,
    } for index in range(150)]
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["analysisPeriod"] = {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30}
    snapshot["selectedGoals"] = {"ids": ["123"], "hasGoalData": True}
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    job.status = "context_ready"
    job.current_stage = "collect_fresh_baseline"
    db.commit()

    def fake_collect(*args, **kwargs):
        return [
            AuditDataRequestResult(
                request_id="baseline_campaigns", hypothesis_id="baseline", capability_id="campaigns",
                dimension="campaigns", status="collected", source="yandex_direct_live_report",
                source_type="report", data=[], rows_analyzed=0, rows_total=0,
            ),
            AuditDataRequestResult(
                request_id="baseline_campaign_performance", hypothesis_id="baseline",
                capability_id="campaign_performance", dimension="campaign_performance", status="collected",
                source="yandex_direct_live_report", source_type="report", data=rows,
                rows_analyzed=150, rows_total=150,
            ),
        ], 1

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", fake_collect)
    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert job.current_stage == "classify_campaigns"
    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    snapshot = audit_jobs._json_load(job.context_snapshot_json, {})
    sample_names = {
        row.get("campaign_name")
        for result in snapshot["aiBaselineSamples"]
        for row in result.get("data") or []
    }
    facts_by_campaign = {item["campaign_name"] for item in snapshot["observedFacts"]}

    assert snapshot["metadata"]["campaignsTotal"] == 150
    assert snapshot["accountTotals"]["cost"] == sum(range(1, 151))
    assert snapshot["metadata"]["rowsReceived"] == 150
    assert snapshot["metadata"]["rowsAnalyzed"] == 150
    assert snapshot["metadata"]["rowsSentToAi"] < 150
    assert len(snapshot["campaignClassifications"]) == 150
    assert len(facts_by_campaign) == 150
    assert facts_by_campaign - sample_names


def test_fresh_baseline_queue_wait_is_normal_active_response(monkeypatch):
    db = _db()
    job = _create(db)
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["analysisPeriod"] = {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30}
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    job.status = "context_ready"
    job.current_stage = "collect_fresh_baseline"
    db.commit()

    def fake_collect(*args, **kwargs):
        return [
            AuditDataRequestResult(
                request_id="baseline_campaigns", hypothesis_id="baseline", capability_id="campaigns",
                dimension="campaigns", status="collected", source="yandex_direct_live_service",
                source_type="service_get", data=[],
            ),
            AuditDataRequestResult(
                request_id="baseline_campaign_performance", hypothesis_id="baseline",
                capability_id="campaign_performance", dimension="campaign_performance",
                status="processing", source="yandex_direct_live_report", source_type="report",
                error_code="direct_report_queue_full", retryable=True,
                next_retry_at="2026-07-16T10:00:15+00:00",
            ),
        ], 1

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", fake_collect)
    current = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    response = audit_jobs.audit_job_response(current, db)

    assert current.status == "context_ready"
    assert current.current_stage == "collect_fresh_baseline"
    assert current.progress_percent == 18
    assert response.error_code is None
    assert response.retryable is False


def test_fresh_baseline_queue_timeout_continues_to_classification(monkeypatch):
    db = _db()
    job = _create(db)
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["analysisPeriod"] = {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30}
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    job.status = "context_ready"
    job.current_stage = "collect_fresh_baseline"
    db.commit()

    def fake_collect(*args, **kwargs):
        return [
            AuditDataRequestResult(
                request_id="baseline_campaigns", hypothesis_id="baseline", capability_id="campaigns",
                dimension="campaigns", status="collected", source="yandex_direct_live_service",
                source_type="service_get", data=[],
            ),
            AuditDataRequestResult(
                request_id="baseline_campaign_performance", hypothesis_id="baseline",
                capability_id="campaign_performance", dimension="campaign_performance",
                status="unavailable", source="unavailable", source_type="report",
                error_code="direct_report_queue_full_timeout", retryable=False,
                limitations=["Свежий срез не получен."],
            ),
        ], 0

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", fake_collect)
    current = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    stored = audit_jobs._load_full_baseline_results(db, current)

    assert current.status == "context_ready"
    assert current.current_stage == "classify_campaigns"
    assert current.progress_percent == 22
    assert any(item.get("error_code") == "direct_report_queue_full_timeout" for item in stored)


def test_public_trace_is_safe_and_distinguishes_backend_and_ai_rows():
    db = _db()
    job = _create(db)
    result = {
        "request_id": "req-safe", "hypothesis_id": "hyp-safe", "capability_id": "search_queries",
        "dimension": "search_queries", "status": "collected", "source": "yandex_direct_live_report",
        "source_type": "report", "request_hash": "must-not-leak", "rows_total": 2,
        "data": [
            {"query": "one", "cost": "0", "conversions": None, "CampaignId": "secret-id"},
            {"query": "two", "cost": "bad", "conversions": "1"},
        ],
    }
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot.update({
        "validatedDataRequests": [{
            "request_id": "req-safe", "hypothesis_id": "hyp-safe", "campaign_name": "Search",
            "campaign_family": "search", "campaign_subtype": "search", "dimension": "search_queries",
            "capability_id": "search_queries", "reason": "Проверить запросы", "period": {}, "filters": {"campaign_name": "Search"},
            "metrics": ["clicks", "cost", "conversions"], "priority": "high", "required_for_conclusion": True,
            "data_preference": "live_required",
        }],
        "hypothesisRegistry": {"hyp-safe": {
            "hypothesis_id": "hyp-safe", "hypothesis_type": "search_query_waste", "campaign_name": "Search",
        }},
        "activeHypothesisIds": ["hyp-safe"],
        "aiDrilldownSamples": [{**result, "data": result["data"][:1]}],
    })
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    audit_jobs._save_full_drilldown_results(db, job, [result])
    db.add(DirectReportJob(
        audit_job_id=job.id, client_id=job.client_id, capability_id="search_queries",
        request_hash="must-not-leak", report_name="safe", report_spec_json="{}",
        status="ready", attempts=3, rows_count=2, rows_collected=2, limited_by=1,
        pages_completed=3, partial=False,
    ))
    db.commit()

    metadata = audit_jobs.audit_job_response(job, db).context_metadata
    serialized = json.dumps(metadata, ensure_ascii=False)
    trace = metadata["publicRequestTrace"][0]

    assert trace["rowsReceived"] == 2
    assert trace["rowsAnalyzedByBackend"] == 2
    assert trace["rowsSentToAi"] == 1
    assert trace["dataQuality"]["numericStateCounts"] == {"known": 2, "missing": 1, "invalid": 1}
    assert [item["status"] for item in trace["statusHistory"]] == ["pending", "processing", "completed"]
    assert trace["pagination"]["pagesCompleted"] == 3
    for forbidden in ("must-not-leak", "secret-id", "request_hash", "CampaignId", "result_json", "Authorization"):
        assert forbidden not in serialized


def test_queue_full_trace_is_safe_and_polling_uses_persistent_retry_time(monkeypatch):
    db = _db()
    job = _create(db)
    now = datetime.now(UTC)
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["validatedDataRequests"] = [{
        "request_id": "req-queue", "hypothesis_id": "hyp-queue", "campaign_name": "Search",
        "campaign_family": "search", "campaign_subtype": "search", "dimension": "campaign_performance",
        "capability_id": "campaign_performance", "reason": "Проверить эффективность", "period": {},
        "filters": {"campaign_name": "Search"}, "metrics": ["cost", "conversions"],
        "priority": "high", "required_for_conclusion": True, "data_preference": "live_required",
    }]
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    job.status = "context_ready"
    job.current_stage = "collect_fresh_baseline"
    audit_jobs._save_full_baseline_results(db, job, [{
        "request_id": "req-queue", "hypothesis_id": "hyp-queue",
        "capability_id": "campaign_performance", "dimension": "campaign_performance",
        "status": "processing", "source": "yandex_direct_live_report", "source_type": "report",
        "request_hash": "private-request-hash", "error_code": "direct_report_queue_full",
        "retryable": True, "data": [],
    }])
    db.add(DirectReportJob(
        audit_job_id=job.id, client_id=job.client_id, capability_id="campaign_performance",
        request_hash="private-request-hash", report_name="private-report-name", report_spec_json="{}",
        status="waiting_for_report_queue", attempts=1, queue_full_attempts=2,
        first_queue_full_at=now - timedelta(seconds=15), last_queue_full_at=now,
        next_retry_at=now + timedelta(seconds=30), retry_after_seconds=30,
        error_code="direct_report_queue_full", error_message="raw provider response must not leak",
    ))
    db.commit()
    monkeypatch.setattr(audit_jobs, "_now", lambda: now)

    response = audit_jobs.audit_job_response(job, db)
    trace = response.context_metadata["publicRequestTrace"][0]
    serialized = json.dumps(response.model_dump(mode="json"), ensure_ascii=False)

    assert response.poll_after_ms == 30_000
    assert trace["status"] == "waiting_for_report_queue"
    assert trace["offlineReport"]["used"] is False
    assert trace["offlineReport"]["attempts"] == 1
    assert trace["offlineReport"]["queueFullAttempts"] == 2
    assert trace["safeError"]["code"] == "direct_report_queue_full"
    assert "private-request-hash" not in serialized
    assert "private-report-name" not in serialized
    assert "raw provider response" not in serialized


def test_public_trace_includes_full_baseline_with_bounded_ai_sample():
    db = _db()
    job = _create(db)
    rows = [{"campaign_name": f"Campaign {index}", "cost": index} for index in range(150)]
    baseline = [{
        "request_id": "baseline-performance", "capability_id": "campaign_performance",
        "status": "collected", "source": "yandex_direct_live_report", "rows_total": 150,
        "data": rows,
    }]
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["aiBaselineSamples"] = [{**baseline[0], "data": rows[:10]}]
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    audit_jobs._save_full_baseline_results(db, job, baseline)
    db.commit()

    trace = audit_jobs.audit_job_response(job, db).context_metadata["publicRequestTrace"]
    baseline_trace = next(item for item in trace if item["capabilityId"] == "campaign_performance")

    assert baseline_trace["rowsReceived"] == 150
    assert baseline_trace["rowsAnalyzedByBackend"] == 150
    assert baseline_trace["rowsSentToAi"] == 10


def test_ai_sample_removes_private_execution_fields_recursively():
    sample = audit_jobs._safe_ai_sample({
        "CampaignId": "123", "request_hash": "hash", "cost": 10,
        "nested": {"Authorization": "Bearer secret", "goal_conversions": 2},
    })

    assert sample == {"cost": 10, "nested": {"goal_conversions": 2}}


def test_large_persistent_evidence_does_not_expand_prompt_snapshot():
    db = _db()
    job = _create(db)
    results = [{
        "request_id": f"req-{index}", "hypothesis_id": f"hyp-{index}",
        "capability_id": "search_queries", "dimension": "search_queries", "status": "collected",
        "data": [{"query": f"q-{row_index}", "cost": row_index} for row_index in range(2000)],
        "rows_total": 2000, "rows_analyzed": 2000,
    } for index in range(20)]

    audit_jobs._save_full_drilldown_results(db, job, results)
    db.commit()

    loaded = audit_jobs._load_full_drilldown_results(db, job)
    assert len(loaded) == 20
    assert sum(len(item["data"]) for item in loaded) == 40000
    assert len(job.prompt_snapshot_json or "") < 1000
    assert "q-1999" not in (job.prompt_snapshot_json or "")
    assert "request_hash" not in (job.prompt_snapshot_json or "")
    public_payload = json.dumps(
        audit_jobs.audit_job_response(job, db).model_dump(mode="json"),
        ensure_ascii=False,
    )
    assert len(public_payload) < 250_000
    assert "q-1999" not in public_payload
    assert '"data"' not in public_payload


def test_rule_plan_separates_retargeting_and_placement_hypotheses():
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-10", "dateTo": "2026-07-09", "days": 30},
        "targetKpis": {"targetCpa": 500},
        "campaignGroups": {"critical": [{
            "name": "РСЯ Ретаргетинг", "cost": 5000, "clicks": 80, "impressions": 5000,
            "goalConversions": 0, "flags": ["spend_without_conversions"],
            "diagnostic": "Расход без конверсий.",
        }], "warning": [], "opportunity": [], "low_data": [], "stable": []},
        "campaignClassifications": [{
            "campaign_name": "РСЯ Ретаргетинг", "campaign_family": "yan",
            "campaign_subtype": "yan_retargeting", "classification_source": "name_fallback",
        }],
        "observedFacts": [{
            "fact_id": "fact-retargeting", "campaign_name": "РСЯ Ретаргетинг",
            "metric": "spend_without_goal_conversions", "sufficient_data": True,
        }],
    }

    plan = audit_jobs.build_rule_based_investigation_plan(snapshot)
    retargeting = next(item for item in plan.hypotheses if item.hypothesis_type == "retargeting_segment_issue")
    placement = next(item for item in plan.hypotheses if item.hypothesis_type == "placement_waste")
    retargeting_capabilities = {item.capability_id or item.dimension for item in retargeting.data_requests}

    assert {"retargeting_lists", "retargeting_segments", "audience_targets"} <= retargeting_capabilities
    assert "search_queries" not in retargeting_capabilities
    assert {item.capability_id or item.dimension for item in placement.data_requests} == {"placements"}
    assert retargeting.fact_ids == ["fact-retargeting"]
    assert placement.fact_ids == ["fact-retargeting"]


def test_rule_plan_uses_only_sufficient_triggering_fact():
    snapshot = {
        "analysisPeriod": {"days": 30},
        "targetKpis": {"targetCpa": 500},
        "campaignGroups": {"critical": [{
            "name": "Search", "cost": 10000, "clicks": 100, "impressions": 5000,
            "goalConversions": 5, "goalCpa": 2000, "flags": ["high_cpa"],
        }], "warning": [], "opportunity": [], "low_data": [], "stable": []},
        "campaignClassifications": [{
            "campaign_name": "Search", "campaign_family": "search", "campaign_subtype": "search",
        }],
        "observedFacts": [
            {"fact_id": "fact-high-cpa", "campaign_name": "Search", "metric": "cpa_above_target", "sufficient_data": True},
            {"fact_id": "fact-dynamics-low", "campaign_name": "Search", "metric": "low_data", "sufficient_data": False},
        ],
    }

    plan = audit_jobs.build_rule_based_investigation_plan(snapshot)

    assert plan.hypotheses[0].fact_ids == ["fact-high-cpa"]


def test_verification_timeout_uses_unverified_fallback_and_continues(monkeypatch):
    db = _db()
    job = _create(db)
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["campaignClassifications"] = audit_jobs.classify_audit_campaigns(snapshot)
    plan = audit_jobs.build_rule_based_investigation_plan(snapshot)
    snapshot["ruleBasedInvestigationPlan"] = plan.model_dump(mode="json")
    snapshot["investigationPlan"] = plan.model_dump(mode="json")
    snapshot["drilldownResults"] = [
        {
            "request_id": request.request_id,
            "hypothesis_id": request.hypothesis_id,
            "dimension": request.dimension,
            "status": "unavailable",
            "summary": "Нет данных",
        }
        for hypothesis in plan.hypotheses
        for request in hypothesis.data_requests
    ]
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    job.status = "context_ready"
    job.current_stage = "verify_hypotheses"
    db.commit()

    async def timeout(model, prompt, max_tokens, **kwargs):
        assert model == audit_jobs.AI_AUDIT_HELPER_MODEL
        assert max_tokens == audit_jobs.AI_AUDIT_VERIFICATION_MAX_TOKENS
        raise HTTPException(status_code=504, detail={"error_code": "openrouter_timeout", "retryable": True})

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", timeout)
    continued = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))

    assert continued.status == "context_ready"
    assert continued.current_stage == "plan_next_investigation_round"
    snapshot = audit_jobs._json_load(continued.context_snapshot_json, {})
    assert snapshot["helperStages"]["verification"]["status"] == "fallback"
    assert snapshot["verifiedHypotheses"]
    assert all(item["status"] in {"unverified", "not_applicable"} for item in snapshot["verifiedHypotheses"])
    assert not any(item["status"] == "confirmed" for item in snapshot["verifiedHypotheses"])


def test_audit_completes_when_all_helper_stages_fallback(monkeypatch):
    db = _db()
    job = _create(db)
    monkeypatch.setattr(audit_jobs, "build_client_ai_context_from_db", lambda *args, **kwargs: _context())

    async def fallback_helpers(model, prompt, max_tokens, **kwargs):
        if model == audit_jobs.AI_AUDIT_HELPER_MODEL:
            raise HTTPException(status_code=504, detail={"error_code": "openrouter_timeout", "retryable": True})
        assert model == job.model
        return {"model": model, "content": _structured_answer(), "usage": {"total_tokens": 500}, "finish_reason": "stop"}

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", fallback_helpers)
    for _ in range(12):
        job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
        if job.status == "completed":
            break

    assert job.status == "completed"
    snapshot = audit_jobs._json_load(job.context_snapshot_json, {})
    assert snapshot["auditRuntime"]["helperFallbacksCount"] == 3
    assert snapshot["auditRuntime"]["helperProviderCallsCount"] == 3
    assert snapshot["auditRuntime"]["finalProviderCallsCount"] == 1
    assert snapshot["helperStages"]["planner"]["status"] == "fallback"
    assert snapshot["helperStages"]["verification"]["status"] == "fallback"
    result = audit_jobs._json_load(job.result_json, {})
    assert len(result["warnings"]) >= 3
    assert job.returned_model == job.model


def test_generating_status_prevents_duplicate_openrouter_call(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "generating"
    job.current_stage = "generate_answer"
    job.stage_execution_token = "active-token"
    job.stage_started_at = datetime.now(UTC)
    job.stage_lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
    job.stage_attempt = 1
    db.commit()

    async def forbidden_generate(*args, **kwargs):
        raise AssertionError("OpenRouter must not be called twice")

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", forbidden_generate)
    same_job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert same_job.status == "generating"


def test_expired_generating_lease_becomes_retryable_failure_on_read():
    db = _db()
    job = _create(db)
    job.status = "generating"
    job.current_stage = "generate_answer"
    job.stage_execution_token = "expired-token"
    job.stage_started_at = datetime.now(UTC) - timedelta(minutes=5)
    job.stage_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    recovered = audit_jobs.get_audit_job(db, job.id, organization_id="org-a")

    assert recovered.status == "failed"
    assert recovered.current_stage == "generate_answer"
    assert recovered.error_code == "ai_audit_stage_stale"
    assert recovered.retryable is True
    assert recovered.stage_execution_token is None
    response = audit_jobs.audit_job_response(recovered)
    assert response.is_stage_stale is True
    assert response.stage_attempt == 0


def test_expired_final_stage_with_saved_evidence_completes_backend_fallback(monkeypatch):
    db = _db()
    job = _create(db)
    snapshot = _realistic_oversized_final_snapshot()
    initial_direct_calls = snapshot["auditRuntime"]["directApiCallsCount"]
    job.status = "generating"
    job.current_stage = "generate_answer"
    job.stage_execution_token = "expired-token"
    job.stage_started_at = datetime.now(UTC) - timedelta(minutes=5)
    job.stage_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()

    def forbidden_direct(*args, **kwargs):
        raise AssertionError("Stale final recovery must not recollect Direct evidence")

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    recovered = audit_jobs.get_audit_job(db, job.id, organization_id="org-a")
    result = audit_jobs._json_load(recovered.result_json, {})
    runtime = audit_jobs._json_load(recovered.context_snapshot_json, {})["auditRuntime"]

    assert recovered.status == "completed"
    assert recovered.progress_percent == 100
    assert recovered.answer_text
    assert result["structured"]
    assert result["backendFallbackUsed"] is True
    assert runtime["finalGenerationStatus"] == "backend_fallback_after_final_stage_stale"
    assert runtime["directApiCallsCount"] == initial_direct_calls


def test_legacy_generating_job_without_lease_is_recovered_from_updated_at():
    db = _db()
    job = _create(db)
    job.status = "generating"
    job.current_stage = "generate_answer"
    job.stage_execution_token = None
    job.stage_started_at = None
    job.stage_lease_expires_at = None
    job.updated_at = datetime.now(UTC) - timedelta(minutes=10)
    db.commit()

    recovered = audit_jobs.get_audit_job(db, job.id, organization_id="org-a")

    assert recovered.status == "failed"
    assert recovered.error_code == "ai_audit_stage_stale"


def test_advance_recovers_stale_helper_stage_with_fallback_without_provider_call(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "generating"
    job.current_stage = "verify_hypotheses"
    job.stage_execution_token = "expired-token"
    job.stage_started_at = datetime.now(UTC) - timedelta(minutes=5)
    job.stage_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    async def forbidden_generate(*args, **kwargs):
        raise AssertionError("Stale recovery must not start a provider request without explicit retry")

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", forbidden_generate)
    recovered = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))

    assert recovered.status == "context_ready"
    assert recovered.current_stage == "plan_next_investigation_round"
    assert recovered.error_code is None
    snapshot = audit_jobs._json_load(recovered.context_snapshot_json, {})
    assert snapshot["helperStages"]["verification"]["status"] == "fallback"


def test_cancel_is_allowed_while_generating_and_late_result_is_discarded(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(audit_jobs.build_compact_audit_context(_context()))
    db.commit()

    async def cancel_then_return(*args, **kwargs):
        cancelled = audit_jobs.cancel_audit_job(db, job.id, organization_id="org-a")
        assert cancelled.status == "cancelled"
        assert cancelled.cancel_requested is True
        return {"model": "qwen/qwen3-14b", "content": _structured_answer(), "id": "late"}

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", cancel_then_return)
    cancelled = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))

    assert cancelled.status == "cancelled"
    assert cancelled.result_json is None
    assert cancelled.answer_text is None


def test_late_result_from_old_execution_token_is_discarded(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(audit_jobs.build_compact_audit_context(_context()))
    db.commit()

    async def replace_token_then_return(*args, **kwargs):
        current = db.get(AiAuditJob, job.id)
        current.stage_execution_token = "newer-attempt-token"
        current.stage_attempt += 1
        db.commit()
        return {"model": "qwen/qwen3-14b", "content": _structured_answer(), "id": "old"}

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", replace_token_then_return)
    current = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))

    assert current.status == "generating"
    assert current.stage_execution_token == "newer-attempt-token"
    assert current.result_json is None


def test_retry_reuses_saved_context_and_creates_new_execution_token(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "failed"
    job.current_stage = "generate_answer"
    job.retryable = True
    job.error_code = "ai_audit_stage_stale"
    job.stage_attempt = 1
    job.stage_execution_token = "old-attempt-token"
    job.context_snapshot_json = audit_jobs._json_dump(audit_jobs.build_compact_audit_context(_context()))
    db.commit()
    seen_tokens = []
    seen_attempts = []

    def forbidden_context(*args, **kwargs):
        raise AssertionError("Retry must reuse the saved context")

    async def successful_retry(*args, **kwargs):
        current = db.get(AiAuditJob, job.id)
        seen_tokens.append(current.stage_execution_token)
        seen_attempts.append(current.stage_attempt)
        return {"model": "qwen/qwen3-14b", "content": _structured_answer(), "id": "retry", "finish_reason": "stop"}

    monkeypatch.setattr(audit_jobs, "build_client_ai_context_from_db", forbidden_context)
    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", successful_retry)
    retried = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a", retry=True))

    assert retried.current_stage == "finalize"
    assert seen_attempts == [2]
    assert seen_tokens and seen_tokens[0] not in {None, "old-attempt-token"}


def test_nested_advance_during_provider_call_does_not_call_provider_twice(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(audit_jobs.build_compact_audit_context(_context()))
    db.commit()
    calls = {"count": 0}

    async def nested_advance(*args, **kwargs):
        calls["count"] += 1
        nested = await audit_jobs.advance_audit_job(db, job.id, organization_id="org-a")
        assert nested.status == "generating"
        return {"model": "qwen/qwen3-14b", "content": _structured_answer(), "id": "one", "finish_reason": "stop"}

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", nested_advance)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))

    assert calls["count"] == 1
    assert generated.current_stage == "finalize"


def test_total_timeout_completes_with_saved_backend_fallback(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    snapshot = _realistic_oversized_final_snapshot()
    initial_direct_calls = snapshot["auditRuntime"]["directApiCallsCount"]
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()
    calls = {"provider": 0, "direct": 0}

    async def slow_provider(*args, **kwargs):
        calls["provider"] += 1
        await asyncio.sleep(0.05)
        return {"model": "qwen/qwen3-14b", "content": _structured_answer()}

    def forbidden_direct(*args, **kwargs):
        calls["direct"] += 1
        raise AssertionError("Final timeout fallback must not recollect Direct evidence")

    monkeypatch.setitem(audit_jobs.AUDIT_STAGE_TOTAL_TIMEOUT_SECONDS, "generate_answer", 0.001)
    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", slow_provider)
    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    completed = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    result = audit_jobs._json_load(completed.result_json, {})
    public = audit_jobs.audit_job_response(completed, db).model_dump(mode="json")
    runtime = audit_jobs._json_load(completed.context_snapshot_json, {})["auditRuntime"]

    assert completed.status == "completed"
    assert completed.progress_percent == 100
    assert completed.answer_text
    assert result["structured"]
    assert result["backendFallbackUsed"] is True
    assert result["finalWarning"]["code"] == "final_provider_timeout"
    assert result["finalWarning"]["retryable"] is True
    assert runtime["finalGenerationStatus"] == "backend_fallback_after_provider_timeout"
    assert runtime["providerErrorCode"] == "openrouter_total_timeout"
    assert runtime["directApiCallsCount"] == initial_direct_calls
    assert calls == {"provider": 1, "direct": 0}
    assert "Authorization" not in audit_jobs._json_dump(public)
    assert completed.stage_execution_token is None

    async def forbidden_provider(*args, **kwargs):
        raise AssertionError("Completed fallback must not call the provider again")

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", forbidden_provider)
    same_job = asyncio.run(audit_jobs.advance_audit_job(db, completed.id, organization_id="org-a"))
    assert same_job.status == "completed"


def test_stale_or_cancelled_job_can_be_reset_without_deletion():
    db = _db()
    job = _create(db)
    job.status = "generating"
    job.current_stage = "generate_answer"
    job.stage_execution_token = "expired"
    job.stage_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    reset = audit_jobs.reset_audit_job(db, job.id, organization_id="org-a")

    assert reset.id == job.id
    assert reset.status == "cancelled"
    assert reset.cancel_requested is True
    assert reset.stage_execution_token is None


def test_final_result_does_not_turn_rejected_or_unverified_hypotheses_into_actions():
    result = {
        "critical_findings": [
            {"hypothesis_id": "hyp-rejected", "hypothesis": "Wrong", "recommendation": "Pause campaign"},
            {"hypothesis_id": "hyp-unverified", "hypothesis": "Possible", "recommendation": "Raise budget", "next_data_needed": ["placements"]},
        ],
        "opportunities": [],
        "action_plan": [
            {"hypothesis_id": "hyp-rejected", "action": "Pause", "reason": "Wrong", "mode": "dry_run"},
            {"hypothesis_id": "hyp-unverified", "action": "Raise budget", "reason": "Possible", "mode": "dry_run"},
        ],
    }
    snapshot = {"verifiedHypotheses": [
        {"hypothesis_id": "hyp-rejected", "status": "rejected"},
        {"hypothesis_id": "hyp-unverified", "status": "unverified", "remaining_data_needed": ["placements"]},
    ]}

    safe = audit_jobs._enforce_verified_result(result, snapshot)

    assert safe["critical_findings"][0]["recommendation"].startswith("Не выполнять")
    assert safe["critical_findings"][1]["recommendation"] == "Собрать недостающие данные: placements"
    assert len(safe["action_plan"]) == 1
    assert safe["action_plan"][0]["action"].startswith("Собрать дополнительные данные")


def test_provider_timeout_uses_fallback_but_auth_error_is_not_masked(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    snapshot = _realistic_oversized_final_snapshot()
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    prompt = audit_jobs.build_full_audit_prompt(
        audit_jobs._json_load(job.context_snapshot_json, {}),
        output_budget_tokens=job.max_tokens,
    )
    job.prompt_snapshot_json = audit_jobs._json_dump(audit_jobs._prompt_metadata(prompt, job))
    db.commit()

    async def timeout(*args, **kwargs):
        raise HTTPException(status_code=504, detail={
            "error_code": "openrouter_timeout",
            "message": "timeout",
            "retryable": True,
            "Authorization": "Bearer must-not-leak",
        })

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", timeout)
    completed = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert completed.status == "completed"
    assert completed.error_code == "final_provider_timeout"
    runtime = audit_jobs._json_load(completed.context_snapshot_json, {})["auditRuntime"]
    assert runtime["providerErrorCode"] == "openrouter_timeout"
    assert "must-not-leak" not in audit_jobs._json_dump(
        audit_jobs.audit_job_response(completed, db).model_dump(mode="json")
    )

    auth_job = _create(db)
    auth_job.status = "context_ready"
    auth_job.current_stage = "generate_answer"
    auth_job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()

    async def auth_error(*args, **kwargs):
        raise HTTPException(status_code=401, detail={"error_code": "openrouter_auth_error", "message": "auth"})

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", auth_error)
    failed = asyncio.run(audit_jobs.advance_audit_job(db, auth_job.id, organization_id="org-a"))
    assert failed.status == "failed"
    assert failed.error_code == "openrouter_auth_error"


def test_invalid_provider_format_is_not_exposed(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    snapshot = audit_jobs.build_compact_audit_context(_context())
    initial_direct_calls = (snapshot.get("auditRuntime") or {}).get("directApiCallsCount", 0)
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    prompt = audit_jobs.build_full_audit_prompt(audit_jobs._json_load(job.context_snapshot_json, {}), output_budget_tokens=job.max_tokens)
    job.prompt_snapshot_json = audit_jobs._json_dump(audit_jobs._prompt_metadata(prompt, job))
    db.commit()

    calls = {"provider": 0, "direct": 0}
    raw_answer = "## Итог\nraw-model-answer-must-not-leak"

    def forbidden_direct(*args, **kwargs):
        calls["direct"] += 1
        raise AssertionError("Parse fallback must not recollect Direct evidence")

    async def invalid(*args, **kwargs):
        calls["provider"] += 1
        return {
            "model": "qwen/qwen3-14b",
            "content": raw_answer,
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 111, "completion_tokens": 22, "total_tokens": 133},
        }

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", invalid)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    completed = asyncio.run(audit_jobs.advance_audit_job(db, generated.id, organization_id="org-a"))
    result = audit_jobs._json_load(completed.result_json, {})
    public = audit_jobs.audit_job_response(completed, db).model_dump(mode="json")
    runtime = audit_jobs._json_load(completed.context_snapshot_json, {})["auditRuntime"]

    assert completed.status == "completed"
    assert completed.error_code is None
    assert calls == {"provider": 1, "direct": 0}
    assert result["structured"] is not None
    assert result["fallbackMarkdown"] is None
    assert result["technicalResponse"] is None
    assert result["backendFallbackUsed"] is True
    assert result["compactRetryAvailable"] is False
    assert result["completeness"] == "backend_fallback"
    assert public["result"]["completeness"] == "backend_fallback"
    assert result["structuredParsing"]["status"] == "success"
    assert result["structuredParsing"]["fallbackReason"] == "json_parse_failed"
    assert result["modelResponseParsing"]["status"] == "fallback"
    assert result["modelResponseParsing"]["sourceFormat"] == "invalid"
    assert result["modelResponseParsing"]["errorCode"] == "json_parse_failed"
    assert result["providerResponseMetadata"]["fullResponseStored"] is False
    assert result["finalTokenUsage"] == {"prompt": 111, "completion": 22, "total": 133}
    assert runtime["finalGenerationStatus"] == "backend_fallback_after_json_parse"
    assert runtime["backendFallbackUsed"] is True
    assert runtime["directApiCallsCount"] == initial_direct_calls
    assert "rawResponse" not in result
    assert raw_answer not in audit_jobs._json_dump(public)


def test_schema_invalid_final_response_uses_backend_fallback_without_external_retries(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    snapshot = _realistic_oversized_final_snapshot()
    snapshot["dataCoverage"] = _production_data_coverage()
    initial_direct_calls = snapshot["auditRuntime"]["directApiCallsCount"]
    original_verification = {
        key: value["status"] for key, value in snapshot["verificationRegistry"].items()
    }
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()
    calls = {"provider": 0, "direct": 0}
    raw_marker = "raw-schema-answer access_token=secret CampaignId=123 request_hash=private"
    raw_answer = json.dumps({"executive_summary": raw_marker}, ensure_ascii=False)

    def forbidden_direct(*args, **kwargs):
        calls["direct"] += 1
        raise AssertionError("Schema fallback must not recollect Direct evidence")

    async def schema_invalid(*args, **kwargs):
        calls["provider"] += 1
        return {
            "model": "deepseek/deepseek-chat",
            "content": raw_answer,
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10918, "completion_tokens": 1800, "total_tokens": 12718},
        }

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", schema_invalid)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    completed = asyncio.run(audit_jobs.advance_audit_job(db, generated.id, organization_id="org-a"))
    result = audit_jobs._json_load(completed.result_json, {})
    persisted_snapshot = audit_jobs._json_load(completed.context_snapshot_json, {})
    runtime = persisted_snapshot["auditRuntime"]
    public_dump = audit_jobs._json_dump(
        audit_jobs.audit_job_response(completed, db).model_dump(mode="json")
    )
    public_result = audit_jobs.audit_job_response(completed, db).model_dump(mode="json")["result"]

    assert completed.status == "completed"
    assert completed.error_code is None
    assert calls == {"provider": 1, "direct": 0}
    assert result["structured"] is not None
    AiAuditResult.model_validate(result["structured"])
    assert result["structured"]["critical_findings"]
    assert result["backendFallbackUsed"] is True
    assert result["completeness"] == "backend_fallback"
    assert public_result["completeness"] == "backend_fallback"
    assert result["compactRetryAvailable"] is False
    assert result["truncated"] is False
    assert result["modelResponseParsing"]["errorCode"] == "json_schema_validation_failed"
    assert result["modelResponseParsing"]["validationErrorsCount"] > 0
    assert len(result["modelResponseParsing"]["validationErrorPaths"]) <= 20
    assert len(result["modelResponseParsing"]["validationErrorTypes"]) <= 20
    assert result["structuredParsing"]["status"] == "success"
    assert result["structuredParsing"]["fallbackReason"] == "json_schema_validation_failed"
    assert result["providerResponseMetadata"]["fullResponseStored"] is False
    coverage = result["structured"]["meta"]["data_coverage"]["campaigns"]
    assert coverage["available"] is True
    assert coverage["total"] == 8
    assert "freshness" not in coverage
    assert "fetchedAt" not in coverage
    assert result["finalTokenUsage"] == {"prompt": 10918, "completion": 1800, "total": 12718}
    assert runtime["finalGenerationStatus"] == "backend_fallback_after_schema_validation"
    assert runtime["backendFallbackUsed"] is True
    assert runtime["directApiCallsCount"] == initial_direct_calls
    assert {
        key: value["status"] for key, value in persisted_snapshot["verificationRegistry"].items()
    } == original_verification
    assert raw_marker not in public_dump
    assert "access_token=secret" not in public_dump
    assert "CampaignId=123" not in public_dump
    assert "request_hash=private" not in public_dump
    assert "rawResponse" not in result


@pytest.mark.parametrize(
    ("wrapper", "expected_format"),
    [
        (lambda value: value, "plain_json"),
        (lambda value: f"```json\n{value}\n```", "markdown_fenced_json"),
        (lambda value: f"```\n{value}\n```", "markdown_fenced_json"),
        (lambda value: f"  ```  json  \n{value}\n```  ", "markdown_fenced_json"),
        (lambda value: f"\ufeff  {value}", "plain_json"),
    ],
)
def test_extract_model_json_object_accepts_supported_formats(wrapper, expected_format):
    parsed, source_format = audit_jobs.extract_model_json_object(wrapper('{"ok":true}'))

    assert parsed == {"ok": True}
    assert source_format == expected_format


@pytest.mark.parametrize(
    ("answer", "expected_format"),
    [
        ("", "empty"),
        ("До ответа {\"ok\":true}", "invalid"),
        ('{"ok":true} после ответа', "invalid"),
        ('```json\n{"ok":}\n```', "invalid"),
        ('[1, 2, 3]', "invalid"),
    ],
)
def test_extract_model_json_object_rejects_empty_prose_and_invalid_json(answer, expected_format):
    parsed, source_format = audit_jobs.extract_model_json_object(answer)

    assert parsed is None
    assert source_format == expected_format


def test_structured_result_accepts_json_markdown_fence_and_overrides_model_meta():
    db = _db()
    job = _create(db)
    snapshot = audit_jobs.build_compact_audit_context(_context())
    payload = json.loads(_structured_answer())
    payload["meta"] = {"model": "untrusted/model", "period": {"date_from": "1900-01-01"}, "output_budget_tokens": 999999}
    fenced_answer = f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"

    structured, parsing = audit_jobs._validate_structured_result_with_metadata(
        fenced_answer,
        snapshot=snapshot,
        job=job,
        response={"model": "qwen/qwen3-14b"},
    )

    assert structured is not None
    assert structured["executive_summary"]
    assert structured["meta"]["model"] == "qwen/qwen3-14b"
    assert structured["meta"]["period"]["date_from"] != "1900-01-01"
    assert structured["meta"]["output_budget_tokens"] == job.max_tokens
    assert parsing["status"] == "success"
    assert parsing["sourceFormat"] == "markdown_fenced_json"
    assert parsing["errorCode"] is None
    assert parsing["validationErrorsCount"] == 0
    assert parsing["validationErrorPaths"] == []
    assert parsing["validationErrorTypes"] == []


def test_generate_stage_stores_fenced_json_as_structured_without_raw_answer(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(audit_jobs.build_compact_audit_context(_context()))
    db.commit()
    calls = {"count": 0}

    async def fenced_provider(*args, **kwargs):
        calls["count"] += 1
        return {
            "model": "qwen/qwen3-14b",
            "content": f"```json\n{_structured_answer()}\n```",
            "finish_reason": "stop",
        }

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", fenced_provider)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    result = audit_jobs._json_load(generated.result_json, {})
    runtime = audit_jobs._json_load(generated.context_snapshot_json, {})["auditRuntime"]

    assert calls["count"] == 1
    assert result["structured"] is not None
    assert result["backendFallbackUsed"] is False
    assert result["fallbackMarkdown"] is None
    assert result["technicalResponse"] is None
    assert result["structuredParsing"]["sourceFormat"] == "markdown_fenced_json"
    assert result["providerResponseMetadata"]["fullResponseStored"] is False
    assert runtime["finalGenerationStatus"] == "provider_completed"
    assert "```json" not in generated.answer_text


def test_legacy_fenced_json_job_is_repaired_and_raw_response_is_not_exposed():
    db = _db()
    job = _create(db)
    snapshot = audit_jobs.build_compact_audit_context(_context())
    fenced_answer = f"```json\n{_structured_answer()}\n```"
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    job.answer_text = fenced_answer
    job.result_json = audit_jobs._json_dump({
        "structured": None,
        "fallbackMarkdown": fenced_answer,
        "rawResponse": fenced_answer,
        "warnings": ["Модель вернула ответ вне JSON-контракта."],
        "completeness": "fallback",
    })
    db.commit()

    response = audit_jobs.audit_job_response(job)

    assert response.result["structured"] is not None
    assert response.result["fallbackMarkdown"] is None
    assert response.result["completeness"] == "structured"
    assert response.result["structuredParsing"]["sourceFormat"] == "markdown_fenced_json"
    assert "rawResponse" not in response.result
    assert "```json" not in response.answer


def test_schema_invalid_json_is_hidden_from_public_result():
    db = _db()
    job = _create(db)
    raw_answer = '```json\n{"executive_summary":"incomplete"}\n```'
    job.context_snapshot_json = audit_jobs._json_dump(audit_jobs.build_compact_audit_context(_context()))
    job.answer_text = raw_answer
    job.result_json = audit_jobs._json_dump({
        "structured": None,
        "fallbackMarkdown": raw_answer,
        "rawResponse": raw_answer,
        "warnings": [],
        "completeness": "fallback",
    })
    db.commit()

    response = audit_jobs.audit_job_response(job)

    assert response.result["structured"] is None
    assert response.result["fallbackMarkdown"] == audit_jobs._UNSUPPORTED_AUDIT_FORMAT_MESSAGE
    assert "technicalResponse" not in response.result
    assert response.result["structuredParsing"]["errorCode"] == "json_schema_validation_failed"
    assert response.result["structuredParsing"]["validationErrorsCount"] > 0
    assert response.answer == audit_jobs._UNSUPPORTED_AUDIT_FORMAT_MESSAGE
    assert "rawResponse" not in response.result
    assert "executive_summary" not in response.answer


def test_context_metadata_reports_saved_live_and_unavailable_drilldowns():
    db = _db()
    job = _create(db)
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["auditRuntime"] = {
        "requestsCount": 5,
        "savedDataRequestsCount": 2,
        "directApiCallsCount": 0,
    }
    snapshot["drilldownResults"] = [
        {"request_id": "1", "dimension": "search_queries", "status": "collected", "source": "directpilot_saved_read_only_stats"},
        {"request_id": "2", "dimension": "goals", "status": "collected", "source": "directpilot_saved_read_only_stats"},
        {"request_id": "3", "dimension": "placements", "status": "unavailable"},
        {"request_id": "4", "dimension": "devices", "status": "insufficient_data"},
        {"request_id": "5", "dimension": "demographics", "status": "not_applicable"},
    ]
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()

    data_requests = audit_jobs.audit_job_response(job).context_metadata["investigation"]["dataRequests"]

    assert data_requests == {
        "planned": 5,
        "allowed": 4,
        "saved": 2,
        "live": 0,
        "liveCompleted": 0,
        "processing": 0,
        "cacheHits": 0,
        "liveAttempts": 0,
        "liveSucceeded": 0,
        "liveProcessing": 0,
        "liveFailed": 0,
        "savedFallbacks": 0,
        "liveFailureReasons": {},
        "statusCounts": {"collected": 2, "unavailable": 1, "insufficient_data": 1, "not_applicable": 1},
        "unavailableDimensions": ["placements"],
        "unavailableCapabilities": [],
        "freshestDataAt": None,
        "pending": 0,
        "completed": 0,
        "failed": 0,
        "unavailable": 0,
    }


def test_live_runtime_counters_distinguish_attempts_cache_processing_and_fallbacks():
    snapshot = {
        "auditRuntime": {},
        "drilldownResults": [
            {"status": "collected", "live_attempted": True, "live": True},
            {"status": "processing", "live_attempted": True, "live": True, "live_error_code": "direct_report_processing"},
            {"status": "collected", "live_attempted": True, "saved_fallback": True, "source": "directpilot_saved_stats", "live_error_code": "direct_rate_limited"},
            {"status": "cached", "cached": True, "source": "yandex_direct_cached_live"},
        ],
    }

    audit_jobs._refresh_direct_read_runtime(snapshot, direct_api_calls=2)
    runtime = snapshot["auditRuntime"]

    assert runtime["liveAttempts"] == 3
    assert runtime["liveSucceeded"] == 1
    assert runtime["liveProcessing"] == 1
    assert runtime["liveFailed"] == 1
    assert runtime["cacheHits"] == 1
    assert runtime["savedFallbacks"] == 1
    assert runtime["liveFailureReasons"] == {
        "direct_report_processing": 1,
        "direct_rate_limited": 1,
    }


def test_processing_direct_report_waits_before_hypothesis_verification(monkeypatch):
    db = _db()
    job = _create(db)
    plan = json.loads(_investigation_answer())
    request = plan["hypotheses"][0]["data_requests"][0]
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["investigationPlan"] = plan
    snapshot["validatedDataRequests"] = [request]
    snapshot["drilldownResults"] = []
    snapshot["auditRuntime"] = {"requestsCount": 1}
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    job.status = "context_ready"
    job.current_stage = "collect_live_data"
    db.commit()
    calls = {"count": 0}

    def fake_collect(*args, **kwargs):
        calls["count"] += 1
        status_value = "processing" if calls["count"] == 1 else "collected"
        return [AuditDataRequestResult(
            request_id=request["request_id"],
            hypothesis_id=request["hypothesis_id"],
            capability_id="search_queries",
            dimension="search_queries",
            campaign_name="Search",
            status=status_value,
            source="yandex_direct_live_report",
            source_type="report",
            live=True,
            data=[] if status_value == "processing" else [{"query": "hotel"}],
            rows_analyzed=0 if status_value == "processing" else 1,
            rows_total=0 if status_value == "processing" else 1,
            error_code="direct_report_processing" if status_value == "processing" else None,
            retryable=status_value == "processing",
        )], 1

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", fake_collect)

    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert job.current_stage == "wait_for_offline_reports"
    assert job.progress_percent == 58

    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert job.current_stage == "verify_hypotheses"
    assert audit_jobs.audit_job_response(job).context_metadata["investigation"]["dataRequests"]["liveCompleted"] == 1


def test_truncated_invalid_json_reports_truncated_provider_response():
    db = _db()
    job = _create(db)
    structured, parsing = audit_jobs._validate_structured_result_with_metadata(
        '```json\n{"executive_summary":',
        snapshot=audit_jobs.build_compact_audit_context(_context()),
        job=job,
        response={"model": job.model},
        finish_reason="length",
    )

    assert structured is None
    assert parsing["status"] == "fallback"
    assert parsing["errorCode"] == "truncated_provider_response"


def test_finish_reason_length_marks_result_truncated_and_allows_compact_retry(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(audit_jobs.build_compact_audit_context(_context()))
    prompt = audit_jobs.build_full_audit_prompt(audit_jobs._json_load(job.context_snapshot_json, {}), output_budget_tokens=job.max_tokens)
    job.prompt_snapshot_json = audit_jobs._json_dump(audit_jobs._prompt_metadata(prompt, job))
    db.commit()

    async def truncated(*args, **kwargs):
        return {"model": "qwen/qwen3-14b", "content": _structured_answer(), "finish_reason": "length"}

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", truncated)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    generated = asyncio.run(audit_jobs.advance_audit_job(db, generated.id, organization_id="org-a"))
    result = audit_jobs._json_load(generated.result_json, {})
    assert generated.status == "completed"
    assert result["truncated"] is True
    assert result["completeness"] == "truncated"
    assert result["structuredParsing"]["status"] == "success"
    assert result["structuredParsing"]["errorCode"] == "truncated_provider_response"
    retrying = asyncio.run(audit_jobs.advance_audit_job(db, generated.id, organization_id="org-a", compact_retry=True))
    assert (retrying.status, retrying.current_stage) == ("context_ready", "generate_answer")
    assert audit_jobs._json_load(retrying.input_options_json, {})["compact_retry"] is True


def _realistic_oversized_final_snapshot() -> dict:
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["campaignClassifications"] = [
        {
            "campaign_name": f"Campaign {index}",
            "campaign_family": "search" if index % 2 else "yan",
            "campaign_subtype": "search" if index % 2 else "yan_prospecting",
        }
        for index in range(12)
    ]
    snapshot["observedFacts"] = []
    snapshot["hypothesisRegistry"] = {}
    snapshot["verificationRegistry"] = {}
    snapshot["drilldownEvidenceSummaries"] = []
    for index in range(12):
        fact_id = f"fact-{index}"
        hypothesis_id = f"hyp-{index}"
        snapshot["observedFacts"].append({
            "fact_id": fact_id,
            "campaign_name": f"Campaign {index}",
            "metric": "spend_without_goal_conversions",
            "evidence": [f"Расход {1000 + index} ₽, конверсий по цели 0."],
            "sufficient_data": True,
        })
        snapshot["hypothesisRegistry"][hypothesis_id] = {
            "hypothesis_id": hypothesis_id,
            "fact_ids": [fact_id],
            "campaign_name": f"Campaign {index}",
            "campaign_family": "search",
            "campaign_subtype": "search",
            "hypothesis_type": "search_query_waste",
            "observed_fact": "Расход без выбранных конверсий.",
            "priority": "high" if index < 3 else "medium",
            "current_status": "confirmed" if index < 3 else "unverified",
        }
        snapshot["verificationRegistry"][hypothesis_id] = {
            "hypothesis_id": hypothesis_id,
            "status": "confirmed" if index < 3 else "unverified",
            "supporting_evidence": [f"Backend подтвердил метрику кампании {index}."],
            "contradicting_evidence": [],
            "limitations": ["Нет данных по качеству лида."],
            "remaining_data_needed": [] if index < 3 else ["search_queries"],
        }
        snapshot["drilldownEvidenceSummaries"].append({
            "hypothesis_id": hypothesis_id,
            "capability_id": "search_queries",
            "status": "collected",
            "rows_total": 76,
            "metrics": {"cost": 1000 + index, "clicks": 20, "goal_conversions": 0},
            "numeric_state_counts": {"known": 25, "missing": 1, "invalid": 0},
            "matched_confirmation_rules": [{
                "rule_code": "search_queries_waste_without_goals",
                "passed": index < 3,
                "summary": "Проверено backend-правилом.",
            }],
            "limitations": ["Доступен ограниченный срез."],
        })
    huge_private_value = "private-ui-trace-" + ("x" * 60000)
    snapshot["publicRequestTrace"] = [
        {"requestId": f"request-{index}", "reason": huge_private_value, "request_hash": "secret-request-hash"}
        for index in range(11)
    ]
    snapshot["aiDrilldownSamples"] = [{
        "request_id": "request-1",
        "data": [{"CampaignId": "private-campaign-id", "query": "sample"}] * 202,
    }]
    snapshot["drilldownResults"] = snapshot["aiDrilldownSamples"]
    snapshot["investigationRounds"] = [{
        "round_number": index,
        "requestLifecycle": [huge_private_value],
        "statusHistory": ["processing", "completed"],
    } for index in range(1, 4)]
    snapshot.setdefault("auditRuntime", {}).update({
        "requestsCount": 11,
        "rowsReceived": 839,
        "rowsAnalyzed": 839,
        "rowsSentToAi": 202,
        "directApiCallsCount": 18,
        "stopReason": "low_expected_information_gain",
    })
    return snapshot


def test_final_projection_excludes_runtime_noise_and_completes_without_direct_recall(monkeypatch):
    db = _db()
    job = _create(db)
    snapshot = _realistic_oversized_final_snapshot()
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()
    calls = {"provider": 0, "direct": 0}
    full_prompt = audit_jobs.build_full_audit_prompt(snapshot, output_budget_tokens=job.max_tokens)
    assert audit_jobs.estimate_tokens(f"{audit_jobs.DEFAULT_SYSTEM_PROMPT}\n{full_prompt}") > audit_jobs.context_limit_for_model(job.model)

    def forbidden_direct(*args, **kwargs):
        calls["direct"] += 1
        raise AssertionError("Final generation must not recollect Direct evidence")

    async def final_provider(model, prompt, **kwargs):
        calls["provider"] += 1
        assert "private-ui-trace" not in prompt
        assert "private-campaign-id" not in prompt
        assert "secret-request-hash" not in prompt
        assert "publicRequestTrace" not in prompt
        assert "aiDrilldownSamples" not in prompt
        assert "search_queries" in prompt
        assert "search_queries_waste_without_goals" in prompt
        return {"model": model, "content": _structured_answer(), "finish_reason": "stop"}

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", final_provider)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    completed = asyncio.run(audit_jobs.advance_audit_job(db, generated.id, organization_id="org-a"))

    assert completed.status == "completed"
    assert calls == {"provider": 1, "direct": 0}
    runtime = audit_jobs._json_load(completed.context_snapshot_json, {})["auditRuntime"]
    assert runtime["finalPromptEstimatedTokens"] + runtime["reservedOutputTokens"] + runtime["safetyMarginTokens"] <= runtime["modelContextLimit"]
    assert runtime["finalGenerationStatus"] == "provider_completed"


def test_final_provider_output_is_capped_without_changing_requested_job_setting(monkeypatch):
    db = _db()
    job = _create(db)
    job.max_tokens = 10000
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(_realistic_oversized_final_snapshot())
    db.commit()
    captured = {}

    async def final_provider(model, prompt, max_tokens, **kwargs):
        captured.update({"max_tokens": max_tokens, "cap": kwargs["max_tokens_cap"]})
        return {
            "model": model,
            "content": _structured_answer(),
            "usage": {"total_tokens": 500},
            "id": "final-capped",
            "finish_reason": "stop",
        }

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", final_provider)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    runtime = audit_jobs._json_load(generated.context_snapshot_json, {})["auditRuntime"]

    assert generated.max_tokens == 10000
    assert captured == {"max_tokens": 4000, "cap": 4000}
    assert runtime["requestedOutputTokens"] == 10000
    assert runtime["effectiveFinalOutputTokens"] == 4000
    assert runtime["reservedOutputTokens"] == 4000


def test_final_projection_l3_uses_backend_fallback_instead_of_failed_job(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(_realistic_oversized_final_snapshot())
    db.commit()

    async def forbidden_provider(*args, **kwargs):
        raise AssertionError("Oversized L3 projection must not be sent to OpenRouter")

    monkeypatch.setattr(audit_jobs, "context_limit_for_model", lambda model: 500)
    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", forbidden_provider)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    completed = asyncio.run(audit_jobs.advance_audit_job(db, generated.id, organization_id="org-a"))
    result = audit_jobs._json_load(completed.result_json, {})

    assert completed.status == "completed"
    assert result["backendFallbackUsed"] is True
    assert result["compactRetryAvailable"] is False
    assert result["structured"]["conclusion"]
    assert "повторить компактную генерацию" not in result["structured"]["conclusion"].lower()
    assert result["safety"]["appliedToYandexDirect"] is False
    runtime = audit_jobs._json_load(completed.context_snapshot_json, {})["auditRuntime"]
    assert runtime["finalCompactionLevel"] == 3
    assert runtime["finalGenerationStatus"] == "backend_fallback"


def test_provider_context_rejection_retries_once_then_completes_with_safe_fallback(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    snapshot = _realistic_oversized_final_snapshot()
    initial_direct_api_calls = snapshot["auditRuntime"]["directApiCallsCount"]
    initial_compaction_level = audit_jobs.build_final_audit_prompt_bundle(snapshot, job)["diagnostics"][
        "finalCompactionLevel"
    ]
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()
    calls = {"provider": 0, "direct": 0}
    raw_provider_error = "Maximum context length exceeded: raw-provider-payload-must-not-leak"

    def forbidden_direct(*args, **kwargs):
        calls["direct"] += 1
        raise AssertionError("Context recovery must not recollect Direct evidence")

    async def context_rejected(*args, **kwargs):
        calls["provider"] += 1
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "context_length_exceeded", "message": raw_provider_error}},
        )

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", context_rejected)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    completed = asyncio.run(audit_jobs.advance_audit_job(db, generated.id, organization_id="org-a"))
    result = audit_jobs._json_load(completed.result_json, {})
    public = audit_jobs.audit_job_response(completed, db).model_dump(mode="json")
    runtime = audit_jobs._json_load(completed.context_snapshot_json, {})["auditRuntime"]

    assert completed.status == "completed"
    assert completed.error_code == audit_jobs.PROVIDER_CONTEXT_OVERFLOW_CODE
    assert calls == {"provider": 2, "direct": 0}
    assert result["backendFallbackUsed"] is True
    assert result["compactRetryAvailable"] is False
    assert result["structuredParsing"]["errorCode"] == audit_jobs.PROVIDER_CONTEXT_OVERFLOW_CODE
    assert runtime["preflightFitsModelContext"] is True
    assert runtime["providerContextRejected"] is True
    assert runtime["providerContextErrorCode"] == audit_jobs.PROVIDER_CONTEXT_OVERFLOW_CODE
    assert runtime["backendFallbackUsed"] is True
    assert runtime["finalGenerationStatus"] == "backend_fallback_after_provider_context_rejection"
    assert runtime["finalCompactionLevel"] > initial_compaction_level
    assert runtime["finalProviderCallsCount"] == 2
    assert runtime["directApiCallsCount"] == initial_direct_api_calls
    assert raw_provider_error not in audit_jobs._json_dump(public)


@pytest.mark.parametrize(
    "exc",
    [
        HTTPException(status_code=504, detail={"error_code": "openrouter_timeout", "message": "context window timed out"}),
        HTTPException(status_code=429, detail={"error_code": "openrouter_rate_limited", "message": "token limit exceeded"}),
        HTTPException(status_code=401, detail={"message": "maximum context auth error"}),
        RuntimeError("provider unavailable"),
    ],
)
def test_context_overflow_recovery_does_not_capture_unrelated_provider_errors(exc):
    assert audit_jobs.is_provider_context_overflow(exc) is False


def test_backend_fallback_preserves_unknown_goal_conversions():
    db = _db()
    job = _create(db)
    snapshot = _realistic_oversized_final_snapshot()
    snapshot.setdefault("accountTotals", {})["goalConversions"] = None

    result = audit_jobs.build_backend_fallback_audit_result(snapshot, job)
    data_facts = " ".join(result["data_quality"]["facts"])

    assert "Конверсии по выбранным целям: недоступны." in data_facts
    assert "Конверсии по выбранным целям: 0." not in data_facts

    snapshot["accountTotals"]["goalConversions"] = 0
    zero_result = audit_jobs.build_backend_fallback_audit_result(snapshot, job)
    assert "Конверсии по выбранным целям: 0." in " ".join(zero_result["data_quality"]["facts"])


def test_compact_retry_reuses_existing_evidence_and_starts_from_l2(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "completed"
    job.current_stage = "finalize"
    job.completed_at = datetime.now(UTC)
    job.context_snapshot_json = audit_jobs._json_dump(_realistic_oversized_final_snapshot())
    job.result_json = audit_jobs._json_dump({
        "structured": None,
        "backendFallbackUsed": True,
        "compactRetryAvailable": True,
        "truncated": False,
    })
    db.commit()
    direct_calls = {"count": 0}

    def forbidden_direct(*args, **kwargs):
        direct_calls["count"] += 1
        raise AssertionError("Compact retry must reuse persisted evidence")

    async def compact_provider(model, prompt, **kwargs):
        assert "private-ui-trace" not in prompt
        return {"model": model, "content": _structured_answer(), "finish_reason": "stop"}

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", compact_provider)
    retrying = asyncio.run(audit_jobs.advance_audit_job(
        db, job.id, organization_id="org-a", compact_retry=True,
    ))
    assert (retrying.status, retrying.current_stage) == ("context_ready", "generate_answer")
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    runtime = audit_jobs._json_load(generated.context_snapshot_json, {})["auditRuntime"]

    assert generated.current_stage == "finalize"
    assert runtime["finalCompactionLevel"] >= 2
    assert direct_calls["count"] == 0


def test_final_projection_is_an_allowlist_without_private_ids_or_samples():
    snapshot = _realistic_oversized_final_snapshot()
    audit_jobs.ensure_evidence_coverage_registry(snapshot)
    snapshot["client_id"] = "private-client-id"
    snapshot["organization_id"] = "private-organization-id"
    snapshot["access_token"] = "private-access-token"
    snapshot["observedFacts"][0]["evidence"].append(
        "CampaignId=embedded-campaign-id access_token=embedded-oauth request_hash=embedded-hash"
    )

    projection = audit_jobs.build_final_audit_projection(snapshot, compaction_level=1)
    serialized = audit_jobs._json_dump(projection)

    assert "private-client-id" not in serialized
    assert "private-organization-id" not in serialized
    assert "private-access-token" not in serialized
    assert "private-campaign-id" not in serialized
    assert "secret-request-hash" not in serialized
    assert "private-ui-trace" not in serialized
    assert "embedded-campaign-id" not in serialized
    assert "embedded-oauth" not in serialized
    assert "embedded-hash" not in serialized
    assert "drilldownResults" not in serialized
    assert projection["evidenceCoverageSummary"]["required"] > 0
    assert isinstance(projection["missingRequiredEvidence"], list)
    assert isinstance(projection["partialRequiredEvidence"], list)
    assert "requestIds" not in serialized


def test_cancel_before_generation_and_preserve_completed_result():
    db = _db()
    job = _create(db)
    cancelled = audit_jobs.cancel_audit_job(db, job.id, organization_id="org-a")
    assert cancelled.status == "cancelled"

    completed = _create(db)
    completed.status = "completed"
    completed.answer_text = "done"
    completed.completed_at = datetime.now(UTC)
    db.commit()
    unchanged = audit_jobs.cancel_audit_job(db, completed.id, organization_id="org-a")
    assert unchanged.status == "completed"
    assert unchanged.answer_text == "done"


def test_heavy_audit_intent_is_deterministic():
    assert audit_jobs.requires_staged_audit("Проведи аудит Яндекс.Директа по чеклисту") is True
    assert audit_jobs.requires_staged_audit("Покажи все критические проблемы") is True
    assert audit_jobs.requires_staged_audit("Какая ты модель?") is False
    assert audit_jobs.requires_staged_audit("Объясни CPA кампании") is False


def test_chat_routes_heavy_audit_to_staged_job_without_openrouter():
    response = asyncio.run(
        chat_with_ai(
            AiChatRequest(client_id="client-a", message="Проведи аудит по чеклисту и покажи критические проблемы"),
            db=None,
            current=None,
        )
    )

    assert response.error_code == "staged_audit_required"
    assert response.suggested_action == "create_audit_job"
    assert response.source == "staged_audit_router"


def test_all_audit_parsers_accept_fenced_json():
    snapshot = audit_jobs.build_compact_audit_context(_context())
    snapshot["campaignClassifications"] = audit_jobs.classify_audit_campaigns(snapshot)
    base_plan = audit_jobs.build_rule_based_investigation_plan(snapshot)

    plan, plan_valid, plan_parsing = audit_jobs._parse_investigation_plan(
        f"```json\n{_investigation_answer()}\n```", snapshot, base_plan,
    )

    assert plan_valid is True
    assert plan.hypotheses
    assert plan_parsing["sourceFormat"] == "markdown_fenced_json"

    snapshot["investigationPlan"] = plan.model_dump(mode="json")
    snapshot["drilldownResults"] = [{
        "request_id": plan.hypotheses[0].data_requests[0].request_id,
        "hypothesis_id": plan.hypotheses[0].hypothesis_id,
        "status": "collected",
        "rows_analyzed": 12,
        "summary": "Получено 12 доверенных строк.",
    }]
    verification_payload = json.loads(_verification_answer())
    verification_payload["verifications"][0]["hypothesis_id"] = plan.hypotheses[0].hypothesis_id
    verifications, verification_valid, verification_parsing = audit_jobs._parse_verifications(
        f"```json\n{json.dumps(verification_payload, ensure_ascii=False)}\n```", snapshot,
    )

    assert verification_valid is True
    assert verifications.verifications[0].status == "unverified"
    assert verification_parsing["sourceFormat"] == "markdown_fenced_json"


def test_strict_schema_reports_safe_validation_metadata_without_values():
    db = _db()
    job = _create(db)
    payload = json.loads(_structured_answer())
    payload["unexpected_secret_field"] = "must-not-leak"

    structured, parsing = audit_jobs._validate_structured_result_with_metadata(
        json.dumps(payload, ensure_ascii=False),
        snapshot=audit_jobs.build_compact_audit_context(_context()),
        job=job,
        response={"model": job.model},
    )

    assert structured is not None
    assert parsing["status"] == "partial"
    assert parsing["errorCode"] == "partial_schema_validation"
    assert parsing["validationErrorsCount"] == 1
    assert parsing["validationErrorPaths"] == ["unexpected_secret_field"]
    assert parsing["validationErrorTypes"] == ["extra_forbidden"]
    assert "must-not-leak" not in json.dumps(parsing)


def test_production_like_result_is_structured_and_unsafe_unverified_actions_are_downgraded():
    db = _db()
    job = _create(db)
    snapshot = audit_jobs.build_compact_audit_context(_context())
    payload = json.loads(_structured_answer())
    payload["insufficient_data_campaigns"] = [{
        "campaign_name": "РСЯ",
        "reason": "Мало кликов",
        "recommendation": "Собрать данные",
        "next_data_needed": ["search_queries"],
    }]
    payload["critical_findings"][0]["hypothesis_id"] = None
    payload["action_plan"] = [
        {
            "priority": 1,
            "hypothesis_id": None,
            "action": "pause_campaign",
            "scope": "Search",
            "reason": "Высокий CPA",
            "mode": "dry_run",
            "requires_human_approval": True,
        },
        {
            "priority": 2,
            "hypothesis_id": None,
            "action": "review_search_queries",
            "scope": "Search",
            "reason": "Проверить интент",
            "mode": "manual_review",
            "requires_human_approval": True,
        },
    ]
    payload["tracking_and_goals"] = {"status": "perfect", "goal_conversions": 999999}

    structured, parsing = audit_jobs._validate_structured_result_with_metadata(
        f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```",
        snapshot=snapshot,
        job=job,
        response={"model": job.model},
    )

    assert parsing["status"] == "success"
    assert structured["insufficient_data_campaigns"][0]["campaign_name"] == "РСЯ"
    assert structured["critical_findings"][0]["verification_status"] == "unverified"
    assert "Неподтверждённая гипотеза" in structured["critical_findings"][0]["hypothesis"]
    assert structured["action_plan"][0]["action"].startswith("Собрать дополнительные данные")
    assert structured["action_plan"][1]["action"] == "review_search_queries"
    assert structured["tracking_and_goals"]["goal_conversions"] != 999999
    assert any("missing_hypothesis_id" in item for item in structured["limitations"])


def test_completion_gate_blocks_final_provider_when_mandatory_evidence_is_missing(monkeypatch):
    db = _db()
    job = _create(db)
    snapshot = _realistic_oversized_final_snapshot()
    audit_jobs.ensure_evidence_coverage_registry(snapshot)
    runtime = audit_jobs._audit_runtime(snapshot)
    runtime["requestsCount"] = audit_jobs.MAX_AUDIT_DATA_REQUESTS
    runtime["completionGateRemediationAttempted"] = True
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()
    calls = {"provider": 0, "direct": 0}

    async def forbidden_provider(*args, **kwargs):
        calls["provider"] += 1
        raise AssertionError("Blocked evidence coverage must not call the final provider")

    def forbidden_direct(*args, **kwargs):
        calls["direct"] += 1
        raise AssertionError("Completion fallback must not recollect Direct evidence")

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", forbidden_provider)
    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    completed = asyncio.run(audit_jobs.advance_audit_job(db, generated.id, organization_id="org-a"))
    result = audit_jobs._json_load(completed.result_json, {})
    public = audit_jobs.audit_job_response(completed, db).model_dump(mode="json")

    assert completed.status == "completed"
    assert calls == {"provider": 0, "direct": 0}
    assert result["backendFallbackUsed"] is True
    assert result["auditCompletionState"] == "blocked_missing_evidence"
    assert result["completeness"] == "blocked_missing_evidence"
    assert result["structured"]["action_plan"] == []
    assert public["context_metadata"]["evidenceCoverage"]["completionState"] == "blocked_missing_evidence"
    assert "requestIds" not in audit_jobs._json_dump(public["context_metadata"]["evidenceCoverage"])
