from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ClientAccount, DirectCampaignPeriodStat
from app.services.ai_recommendations import build_client_ai_context_from_db
from app.services.direct_analyst_playbook import DIRECT_ANALYST_PLAYBOOK_TEXT
from app.services.performance_summary import build_performance_summary


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_playbook_contains_no_apply_guardrails() -> None:
    text = DIRECT_ANALYST_PLAYBOOK_TEXT.lower()
    assert "never claim changes were applied" in text
    assert "never recommend write actions without approval" in text
    assert "goal data is missing" in text


def test_sync_diagnostics_counts_matched_and_unmatched_goal_campaigns() -> None:
    SessionLocal = _session_factory()

    with SessionLocal() as db:
        db.add(
            ClientAccount(
                id="client-1",
                name="Client 1",
                segment="Test",
                conversion_goal_ids="111, 222",
            )
        )
        db.add_all(
            [
                DirectCampaignPeriodStat(
                    client_id="client-1",
                    campaign_id="campaign-1",
                    campaign_name="Matched",
                    period_from=datetime(2026, 5, 1, tzinfo=UTC),
                    period_to=datetime(2026, 5, 7, tzinfo=UTC),
                    impressions=1000,
                    clicks=100,
                    cost=5000.0,
                    ctr=10.0,
                    avg_cpc=50.0,
                    conversions=4.0,
                    goal_ids="111,222",
                    goal_conversions=2.0,
                    conversion_source="metrika_goals",
                ),
                DirectCampaignPeriodStat(
                    client_id="client-1",
                    campaign_id="campaign-2",
                    campaign_name="Unmatched",
                    period_from=datetime(2026, 5, 1, tzinfo=UTC),
                    period_to=datetime(2026, 5, 7, tzinfo=UTC),
                    impressions=500,
                    clicks=20,
                    cost=2000.0,
                    ctr=4.0,
                    avg_cpc=100.0,
                    conversions=1.0,
                    goal_ids="111,222",
                    conversion_source="metrika_goal_unavailable",
                    conversion_warning="Metrika goal data could not be matched.",
                ),
            ]
        )
        db.commit()

        summary = build_performance_summary(db, "client-1")
        context = build_client_ai_context_from_db(db, "client-1")

    diagnostics = summary["syncDiagnostics"]
    assert diagnostics["directRowsLoaded"] == 2
    assert diagnostics["hasGoalIds"] is True
    assert diagnostics["hasGoalData"] is True
    assert diagnostics["goalMatchedCampaigns"] == 1
    assert diagnostics["goalUnmatchedCampaigns"] == 1
    assert diagnostics["dataQualityLevel"] == "warning"
    assert summary["syncDiagnostics"] == context["sync_diagnostics"]
    assert "direct_analyst_playbook" in context
