import asyncio
import json
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.services.ai_audit_jobs as audit_jobs
from app.api.routers.ai import chat_with_ai
from app.db import Base
from app.models import AiAuditJob, ClientAccount, Organization, User
from app.schemas import AiAuditCreateRequest, AiChatRequest
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
        AiAuditCreateRequest(client_id=client_id, model="qwen/qwen3-14b", ai_preset="balanced", max_tokens=2500),
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


def test_full_staged_flow_completes_and_calls_openrouter_once(monkeypatch):
    db = _db()
    job = _create(db)
    monkeypatch.setattr(audit_jobs, "build_client_ai_context_from_db", lambda *args, **kwargs: _context())
    calls = {"count": 0}

    async def fake_generate(model, prompt, max_tokens, **kwargs):
        calls["count"] += 1
        assert "10000 токенов" not in prompt  # explicit test job uses 2500
        assert "не обрывай разделы" in prompt.lower()
        assert "не выводи campaignid" in prompt.lower()
        assert kwargs["max_tokens_cap"] == 10000
        assert kwargs["timeout"] is audit_jobs.OPENROUTER_AUDIT_TIMEOUT
        return {"model": model, "content": _structured_answer(), "usage": {"total_tokens": 500}, "id": "or-1", "finish_reason": "stop"}

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", fake_generate)

    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert (job.status, job.current_stage, job.progress_percent) == ("context_ready", "build_prompt", 35)
    assert "must-not-be-stored" not in (job.context_snapshot_json or "")
    assert audit_jobs._json_load(job.prompt_snapshot_json, {})["internalCampaignIds"] == ["1"]

    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert (job.status, job.current_stage) == ("context_ready", "generate_answer")
    assert audit_jobs._json_load(job.prompt_snapshot_json, {})["fullPromptStored"] is False

    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert (job.status, job.current_stage) == ("context_ready", "finalize")
    assert calls["count"] == 1

    job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert job.status == "completed"
    assert job.answer_text.startswith("Период анализа: 10.06.2026–09.07.2026, 30 дней.")
    assert audit_jobs.audit_job_response(job).result["structured"]["critical_findings"][0]["campaign_name"] == "Search"
    assert audit_jobs.audit_job_response(job).result["safety"]["appliedToYandexDirect"] is False
    assert calls["count"] == 1


def test_generating_status_prevents_duplicate_openrouter_call(monkeypatch):
    db = _db()
    job = _create(db)
    job.status = "generating"
    job.current_stage = "generate_answer"
    db.commit()

    async def forbidden_generate(*args, **kwargs):
        raise AssertionError("OpenRouter must not be called twice")

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", forbidden_generate)
    same_job = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    assert same_job.status == "generating"


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


def test_invalid_json_is_preserved_as_markdown_fallback(monkeypatch):
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
    assert result["fallbackMarkdown"].startswith("## Итог")
    assert result["completeness"] == "fallback"


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
    retrying = asyncio.run(audit_jobs.advance_audit_job(db, generated.id, organization_id="org-a", compact_retry=True))
    assert (retrying.status, retrying.current_stage) == ("context_ready", "build_prompt")
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
