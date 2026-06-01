from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ClientAccount, DirectCampaignDailyStat
from app.services.performance_summary import build_performance_summary, build_yesterday_campaign_summary


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _yesterday():
    return datetime.now(UTC).date() - timedelta(days=1)


def test_yesterday_summary_uses_goal_conversions_only() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        db.add(ClientAccount(id="client-yesterday", name="Client Yesterday", segment="Test", conversion_goal_ids="35371875"))
        db.add(
            DirectCampaignDailyStat(
                client_id="client-yesterday",
                stat_date=_yesterday(),
                campaign_id="1",
                campaign_name="Search",
                impressions=1000,
                clicks=100,
                cost=12000,
                ctr=10,
                avg_cpc=120,
                goal_ids="35371875",
                goal_conversions=12,
                goal_cpa=1000,
                conversion_rate=12,
                issue_flags="promising_campaign",
            )
        )
        db.commit()

        summary = build_yesterday_campaign_summary(db, "client-yesterday")

        assert summary["hasData"] is True
        assert summary["totals"]["goalConversions"] == 12
        assert summary["totals"]["goalCpa"] == 1000
        assert "totalConversions" not in summary["totals"]
        assert "conversions" not in summary["totals"]


def test_yesterday_summary_flags_spend_without_goal_conversions() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        db.add(ClientAccount(id="client-flags", name="Client Flags", segment="Test", conversion_goal_ids="35371875"))
        db.add(
            DirectCampaignDailyStat(
                client_id="client-flags",
                stat_date=_yesterday(),
                campaign_id="1",
                campaign_name="Search No Goals",
                impressions=800,
                clicks=12,
                cost=900,
                ctr=1.5,
                avg_cpc=75,
                goal_ids="35371875",
                goal_conversions=0,
                goal_cpa=None,
                conversion_rate=0,
                issue_flags="spend_without_conversions,check_queries_landing_goals",
            )
        )
        db.commit()

        summary = build_yesterday_campaign_summary(db, "client-flags")

        assert summary["insights"]["spendWithoutGoalConversions"][0]["campaignName"] == "Search No Goals"
        assert "Проверить кампанию" in summary["recommendations"][0]


def test_yesterday_summary_low_data_is_not_critical_by_itself() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        db.add(ClientAccount(id="client-low-data", name="Client Low Data", segment="Test", conversion_goal_ids="35371875"))
        db.add(
            DirectCampaignDailyStat(
                client_id="client-low-data",
                stat_date=_yesterday(),
                campaign_id="1",
                campaign_name="Tiny Campaign",
                impressions=20,
                clicks=1,
                cost=50,
                ctr=5,
                avg_cpc=50,
                goal_ids="35371875",
                goal_conversions=0,
                goal_cpa=None,
                conversion_rate=0,
                issue_flags="low_data",
            )
        )
        db.commit()

        summary = build_yesterday_campaign_summary(db, "client-low-data")

        assert summary["insights"]["spendWithoutGoalConversions"] == []
        assert "мало данных" in summary["recommendations"][0].lower()


def test_performance_summary_includes_yesterday_summary() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        db.add(ClientAccount(id="client-summary-yesterday", name="Client Summary", segment="Test", conversion_goal_ids="35371875"))
        db.add(
            DirectCampaignDailyStat(
                client_id="client-summary-yesterday",
                stat_date=_yesterday(),
                campaign_id="1",
                campaign_name="Search",
                impressions=1000,
                clicks=100,
                cost=12000,
                ctr=10,
                avg_cpc=120,
                goal_ids="35371875",
                goal_conversions=12,
                goal_cpa=1000,
                conversion_rate=12,
            )
        )
        db.commit()

        summary = build_performance_summary(db, "client-summary-yesterday")

        assert summary["yesterdayCampaignSummary"]["hasData"] is True
        assert summary["yesterdayCampaignSummary"]["totals"]["goalConversions"] == 12
