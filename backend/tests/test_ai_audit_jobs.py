import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.services.ai_audit_jobs as audit_jobs
from app.api.routers.ai import chat_with_ai
from app.db import Base
from app.models import AiAuditJob, ClientAccount, Organization, User
from app.schemas import (
    AiAuditCreateRequest,
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
        assert kwargs["max_tokens_cap"] == 10000
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
    assert stages[:8] == [
        "create_investigation_plan", "validate_data_requests", "collect_live_data",
        "verify_hypotheses", "plan_next_investigation_round", "generate_answer", "finalize", "finalize",
    ]
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
    assert runtime["requestsCount"] == 2
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
    audit_jobs._save_full_drilldown_results(job, [full_result])

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
    assert len(audit_jobs._load_full_drilldown_results(job)[0]["data"]) == 1200
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
        "baselineResults": [{"capability_id": "campaign_performance", "data": rows}],
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
    assert len(snapshot["baselineResults"][0]["data"]) == 150
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


def test_multiple_hypotheses_for_same_campaign_are_not_collapsed():
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
        "observedFacts": [],
    }
    fallback = audit_jobs.build_rule_based_investigation_plan(snapshot)
    first = fallback.hypotheses[0]
    proposed = audit_jobs.AuditInvestigationPlan(hypotheses=[
        first.model_copy(update={"hypothesis": "Search-query intent is weak."}),
        first.model_copy(update={
            "hypothesis_id": "hyp_device",
            "hypothesis": "Mobile device traffic may be inefficient.",
        }),
    ])

    merged = audit_jobs._merge_investigation_plans(proposed, snapshot, fallback)

    assert len(merged.hypotheses) == 2
    assert len({item.hypothesis_id for item in merged.hypotheses}) == 2
    assert {item.campaign_name for item in merged.hypotheses} == {"Search Brand"}


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
    assert len(result["warnings"]) == 3
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


def test_total_timeout_does_not_leave_job_generating(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(audit_jobs.build_compact_audit_context(_context()))
    db.commit()

    async def slow_provider(*args, **kwargs):
        await asyncio.sleep(0.05)
        return {"model": "qwen/qwen3-14b", "content": _structured_answer()}

    monkeypatch.setitem(audit_jobs.AUDIT_STAGE_TOTAL_TIMEOUT_SECONDS, "generate_answer", 0.001)
    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", slow_provider)
    failed = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))

    assert failed.status == "failed"
    assert failed.error_code == "openrouter_total_timeout"
    assert failed.retryable is True
    assert failed.stage_execution_token is None


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


def test_timeout_is_saved_as_retryable_failure(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(audit_jobs.build_compact_audit_context(_context()))
    prompt = audit_jobs.build_full_audit_prompt(
        audit_jobs._json_load(job.context_snapshot_json, {}),
        output_budget_tokens=job.max_tokens,
    )
    job.prompt_snapshot_json = audit_jobs._json_dump(audit_jobs._prompt_metadata(prompt, job))
    db.commit()

    async def timeout(*args, **kwargs):
        raise HTTPException(status_code=504, detail={"error_code": "openrouter_timeout", "message": "timeout", "retryable": True})

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", timeout)
    failed = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert failed.status == "failed"
    assert failed.error_code == "openrouter_timeout"
    assert failed.retryable is True


def test_invalid_provider_format_is_not_exposed(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "context_ready"
    job.current_stage = "generate_answer"
    job.context_snapshot_json = audit_jobs._json_dump(audit_jobs.build_compact_audit_context(_context()))
    prompt = audit_jobs.build_full_audit_prompt(audit_jobs._json_load(job.context_snapshot_json, {}), output_budget_tokens=job.max_tokens)
    job.prompt_snapshot_json = audit_jobs._json_dump(audit_jobs._prompt_metadata(prompt, job))
    db.commit()

    async def invalid(*args, **kwargs):
        return {"model": "qwen/qwen3-14b", "content": "## Итог\nБезопасный fallback", "finish_reason": "stop"}

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", invalid)
    generated = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    result = audit_jobs._json_load(generated.result_json, {})
    assert result["structured"] is None
    assert result["fallbackMarkdown"] == audit_jobs._UNSUPPORTED_AUDIT_FORMAT_MESSAGE
    assert result["technicalResponse"] is None
    assert result["structuredParsing"]["status"] == "fallback"
    assert result["structuredParsing"]["sourceFormat"] == "invalid"
    assert result["structuredParsing"]["errorCode"] == "json_parse_failed"
    assert result["structuredParsing"]["validationErrorsCount"] == 0
    assert result["providerResponseMetadata"]["fullResponseStored"] is False
    assert result["completeness"] == "fallback"
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

    assert calls["count"] == 1
    assert result["structured"] is not None
    assert result["fallbackMarkdown"] is None
    assert result["technicalResponse"] is None
    assert result["structuredParsing"]["sourceFormat"] == "markdown_fenced_json"
    assert result["providerResponseMetadata"]["fullResponseStored"] is False
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
