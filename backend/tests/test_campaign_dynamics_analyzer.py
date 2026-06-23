import asyncio
from dataclasses import replace
from datetime import date, timedelta

import app.services.ai_chat as ai_chat_module
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routers.ai import _apply_intent_token_floor
from app.core.config import settings as base_settings
from app.db import Base
from app.models import ClientAccount, DirectCampaignDailyStat
from app.services.campaign_dynamics_analyzer import analyze_campaign_dynamics


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _test_settings():
    return replace(base_settings, openrouter_api_key="test-key", openrouter_allow_custom_models=True)


def _add_daily(
    db,
    *,
    client_id: str = "client-dynamics",
    stat_date: date,
    campaign_id: str,
    campaign_name: str,
    cost: float,
    impressions: int,
    clicks: int,
    goal_conversions: float | None,
    avg_cpc: float | None = None,
    ctr: float | None = None,
):
    db.add(
        DirectCampaignDailyStat(
            client_id=client_id,
            stat_date=stat_date,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            impressions=impressions,
            clicks=clicks,
            cost=cost,
            ctr=ctr if ctr is not None else (clicks / impressions * 100 if impressions else 0),
            avg_cpc=avg_cpc if avg_cpc is not None else (cost / clicks if clicks else 0),
            goal_ids="35371875",
            goal_conversions=goal_conversions,
            goal_cpa=(cost / goal_conversions) if goal_conversions else None,
            conversion_rate=(goal_conversions / clicks * 100) if goal_conversions is not None and clicks else None,
        )
    )


def test_dynamics_intent_uses_token_floor_only_when_not_explicit():
    base = {"max_tokens": 900, "max_tokens_cap": 5000}
    raised = _apply_intent_token_floor(
        base,
        message="campaign dynamics last 7 14 30 days",
        explicit_max_tokens=False,
    )
    explicit = _apply_intent_token_floor(
        base,
        message="campaign dynamics last 7 14 30 days",
        explicit_max_tokens=True,
    )

    assert raised["max_tokens"] == 2500
    assert explicit["max_tokens"] == 900


def test_campaign_dynamics_windows_and_aggregation():
    today = date(2026, 6, 23)
    date_to = today - timedelta(days=1)
    SessionLocal = _session()
    with SessionLocal() as db:
        db.add(
            ClientAccount(
                id="client-dynamics",
                name="Dynamics",
                segment="Test",
                conversion_goal_ids="35371875",
                target_cpa=100,
            )
        )
        for offset in range(30):
            day = date_to - timedelta(days=offset)
            _add_daily(
                db,
                stat_date=day,
                campaign_id="good",
                campaign_name="Good Campaign",
                cost=100,
                impressions=1000,
                clicks=100,
                goal_conversions=2,
            )
        db.commit()

        result = analyze_campaign_dynamics(db, "client-dynamics", today=today)

        assert result["period"]["windows"]["last7"]["dateFrom"] == "2026-06-16"
        assert result["period"]["windows"]["last7"]["dateTo"] == "2026-06-22"
        assert result["period"]["windows"]["previous7"]["dateFrom"] == "2026-06-09"
        assert result["accountDynamics"]["last7"]["cost"] == 700
        assert result["accountDynamics"]["last7"]["clicks"] == 700
        assert result["accountDynamics"]["last7"]["goalConversions"] == 14
        assert result["accountDynamics"]["last7"]["goalCpa"] == 50
        assert result["accountDynamics"]["changes"]["last7VsPrevious7"]["costDeltaPct"] == 0


def test_campaign_dynamics_delta_handles_zero_previous_period():
    today = date(2026, 6, 23)
    date_to = today - timedelta(days=1)
    SessionLocal = _session()
    with SessionLocal() as db:
        db.add(ClientAccount(id="client-dynamics", name="Dynamics", segment="Test", conversion_goal_ids="35371875"))
        _add_daily(
            db,
            stat_date=date_to,
            campaign_id="new",
            campaign_name="New Campaign",
            cost=100,
            impressions=1000,
            clicks=100,
            goal_conversions=1,
        )
        db.commit()

        result = analyze_campaign_dynamics(db, "client-dynamics", today=today)

        assert result["accountDynamics"]["changes"]["last7VsPrevious7"]["costDeltaPct"] is None
        assert result["accountDynamics"]["changes"]["last7VsPrevious7"]["goalConversionsDeltaPct"] is None


def test_campaign_dynamics_classifies_core_cases():
    today = date(2026, 6, 23)
    date_to = today - timedelta(days=1)
    SessionLocal = _session()
    with SessionLocal() as db:
        db.add(
            ClientAccount(
                id="client-dynamics",
                name="Dynamics",
                segment="Test",
                conversion_goal_ids="35371875",
                target_cpa=100,
            )
        )
        for offset in range(7):
            day = date_to - timedelta(days=offset)
            _add_daily(db, stat_date=day, campaign_id="zero", campaign_name="Zero Conv", cost=150, impressions=1000, clicks=20, goal_conversions=0)
            _add_daily(db, stat_date=day, campaign_id="cpa", campaign_name="CPA Growth", cost=300, impressions=1000, clicks=30, goal_conversions=1)
            _add_daily(db, stat_date=day, campaign_id="drop", campaign_name="Conversion Drop", cost=100, impressions=1000, clicks=30, goal_conversions=1)
            _add_daily(db, stat_date=day, campaign_id="ctr", campaign_name="CTR Drop", cost=100, impressions=1000, clicks=10, goal_conversions=1)
            _add_daily(db, stat_date=day, campaign_id="cpc", campaign_name="CPC Growth", cost=500, impressions=1000, clicks=20, goal_conversions=5)
            _add_daily(db, stat_date=day, campaign_id="good", campaign_name="Promising", cost=100, impressions=1000, clicks=100, goal_conversions=2)
            _add_daily(db, stat_date=day, campaign_id="low", campaign_name="Low Data", cost=5, impressions=10, clicks=1, goal_conversions=0)
        for offset in range(7, 14):
            day = date_to - timedelta(days=offset)
            _add_daily(db, stat_date=day, campaign_id="cpa", campaign_name="CPA Growth", cost=100, impressions=1000, clicks=30, goal_conversions=2)
            _add_daily(db, stat_date=day, campaign_id="drop", campaign_name="Conversion Drop", cost=100, impressions=1000, clicks=30, goal_conversions=4)
            _add_daily(db, stat_date=day, campaign_id="ctr", campaign_name="CTR Drop", cost=100, impressions=1000, clicks=30, goal_conversions=1)
            _add_daily(db, stat_date=day, campaign_id="cpc", campaign_name="CPC Growth", cost=100, impressions=1000, clicks=20, goal_conversions=5)
            _add_daily(db, stat_date=day, campaign_id="good", campaign_name="Promising", cost=100, impressions=1000, clicks=100, goal_conversions=1)
        db.commit()

        result = analyze_campaign_dynamics(db, "client-dynamics", today=today)
        by_name = {item["campaignName"]: item for item in result["campaignDynamics"]["allCampaignsCompact"]}

        assert "spend_without_conversions" in by_name["Zero Conv"]["issueFlags"]
        assert "high_cpa" in by_name["CPA Growth"]["issueFlags"]
        assert "cpa_growth" in by_name["CPA Growth"]["issueFlags"]
        assert "conversion_drop" in by_name["Conversion Drop"]["issueFlags"]
        assert "ctr_drop" in by_name["CTR Drop"]["issueFlags"]
        assert "cpc_growth" in by_name["CPC Growth"]["issueFlags"]
        assert "promising_growth" in by_name["Promising"]["issueFlags"]
        assert "low_data" in by_name["Low Data"]["issueFlags"]
        assert result["drilldownPlan"]


def test_ai_chat_dynamics_prompt_and_trace_include_compact_analysis(monkeypatch):
    captured = {}
    monkeypatch.setattr(ai_chat_module, "settings", _test_settings())

    async def fake_generate(*args, **kwargs):
        captured.update(kwargs)
        return {"model": kwargs["model"], "content": "ok"}

    monkeypatch.setattr(ai_chat_module, "generate_openrouter_response", fake_generate)

    context = {
        "client": {"id": "client-dynamics", "name": "Dynamics"},
        "campaign_dynamics_analysis": {
            "period": {"windows": {"last7": {}, "previous7": {}, "last14": {}, "previous14": {}, "last30": {}}},
            "dataQuality": {"rows": 30, "campaigns": 2, "hasGoalData": True, "missingDays": [], "limitations": []},
            "accountDynamics": {"last7": {"cost": 100}, "previous7": {"cost": 80}, "last14": {}, "previous14": {}, "last30": {}, "changes": {}},
            "campaignDynamics": {
                "worstCampaigns": [{"campaignName": "Bad", "severity": "critical", "issueFlags": ["spend_without_conversions"], "last7": {"cost": 100, "clicks": 20, "goalConversions": 0}, "changes": {"last7VsPrevious7": {"costDeltaPct": 20}}}],
                "bestCampaigns": [{"campaignName": "Good", "severity": "opportunity", "issueFlags": ["promising_growth"], "last7": {"cost": 50, "goalConversions": 5}, "changes": {"last7VsPrevious7": {"goalConversionsDeltaPct": 50}}}],
            },
            "drilldownPlan": [{"campaignName": "Bad", "issue": "spend_without_conversions"}],
            "recommendations": [{"title": "Check Bad"}],
        },
        "summary": {"searchQueryInsights": {"insights": [{"query": "should-not-dump"}]}, "yandexDirectAudit": {"criticalIssues": ["full-audit-should-not-dominate"]}},
    }

    response = asyncio.run(
        ai_chat_module.answer_ai_chat(
            client_id="client-dynamics",
            message="Проанализируй динамику за последние 7 14 30 дней",
            model="google/gemma-3-12b-it",
            history=[],
            client_context=context,
            max_tokens=2500,
        )
    )

    assert response.answer == "ok"
    assert response.requestTrace["analysisPlan"]["intent"] == "campaign_dynamics_analysis"
    assert response.requestTrace["campaignDynamicsAnalysis"]["available"] is True
    assert response.requestTrace["campaignDynamicsAnalysis"]["rows"] == 30
    assert response.requestTrace["campaignDynamicsAnalysis"]["worstCampaignsCount"] == 1
    prompt = captured["prompt"]
    assert "campaignDynamicsAnalysis" in prompt
    assert "Разбери динамику от общего к частному" in prompt
    assert "full-audit-should-not-dominate" not in prompt
    assert "should-not-dump" not in prompt
