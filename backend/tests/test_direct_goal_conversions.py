from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors.yandex_direct import YandexDirectConnector, _build_campaign_report_payload
from app.db import Base
from app.models import ClientAccount, DirectCampaignPeriodStat
from app.services.client_sync import DIRECT_GOAL_FALLBACK_MESSAGE, run_client_sync
from app.services.performance_summary import build_performance_summary

PERIOD_FROM = datetime(2026, 5, 1, tzinfo=UTC)
PERIOD_TO = datetime(2026, 5, 30, tzinfo=UTC)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_direct_report_payload_includes_goal_ids() -> None:
    payload = _build_campaign_report_payload(
        selection_criteria={"DateFrom": "2026-05-01", "DateTo": "2026-05-30"},
        report_period="2026-05-01 2026-05-30",
        date_range_type="CUSTOM_DATE",
        limit=1000,
        goal_ids=["35371875", "344527023"],
    )

    params = payload["params"]
    assert params["Goals"] == [35371875, 344527023]
    assert "Conversions" in params["FieldNames"]
    assert params["ReportType"] == "CAMPAIGN_PERFORMANCE_REPORT"


def test_sync_stores_direct_goal_conversions(monkeypatch) -> None:
    SessionLocal = _session()

    def fake_token(db, account_id):
        return "token"

    def fake_report(self, **kwargs):
        assert kwargs["goal_ids"] == ["35371875", "344527023"]
        return [
            {
                "CampaignId": "1",
                "CampaignName": "Search",
                "Impressions": "1000",
                "Clicks": "100",
                "Cost": "17700",
                "Ctr": "10",
                "AvgCpc": "177",
                "Conversions": "177",
                "_TotalConversions": "919",
                "Conversions_35371875_LSC": "100",
                "Conversions_344527023_LSC": "77",
            }
        ]

    monkeypatch.setattr("app.services.client_sync.get_yandex_access_token_for_account", fake_token)
    monkeypatch.setattr(YandexDirectConnector, "get_campaign_report", fake_report)

    with SessionLocal() as db:
        db.add(
            ClientAccount(
                id="client-goals",
                name="Client Goals",
                segment="Test",
                yandex_account_id="account-1",
                conversion_goal_ids="35371875, 344527023",
            )
        )
        db.commit()

        job = run_client_sync(db, "client-goals", days=30)
        stat = db.query(DirectCampaignPeriodStat).filter_by(client_id="client-goals").one()

        assert job.status == "success"
        assert stat.conversions == 919
        assert stat.goal_conversions == 177
        assert stat.goal_ids == "35371875, 344527023"
        assert stat.conversion_source == "yandex_direct_goals"
        assert stat.goal_cpa == 100


def test_summary_prefers_direct_goal_conversions() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        db.add(
            ClientAccount(
                id="client-summary",
                name="Client Summary",
                segment="Test",
                conversion_goal_ids="35371875, 344527023",
            )
        )
        db.commit()
        db.add(
            DirectCampaignPeriodStat(
                client_id="client-summary",
                campaign_id="1",
                campaign_name="Search",
                period_from=PERIOD_FROM,
                period_to=PERIOD_TO,
                impressions=1000,
                clicks=100,
                cost=17700,
                ctr=10,
                avg_cpc=177,
                conversions=919,
                goal_ids="35371875, 344527023",
                goal_conversions=177,
                goal_cpa=100,
                conversion_source="yandex_direct_goals",
            )
        )
        db.commit()

        summary = build_performance_summary(db, "client-summary")

        assert summary["selectedGoalIds"] == ["35371875", "344527023"]
        assert summary["hasGoalData"] is True
        assert summary["totals"]["conversions"] == 177
        assert summary["goalConversionsTotal"] == 177
        assert summary["totalConversionsFallback"] == 919
        assert "35371875, 344527023" in summary["conversionsSourceMessage"]
        assert summary["campaigns"][0]["conversion_source"] == "yandex_direct_goals"


def test_summary_warns_when_goal_conversions_fallback_to_total() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        db.add(
            ClientAccount(
                id="client-fallback",
                name="Client Fallback",
                segment="Test",
                conversion_goal_ids="35371875, 344527023",
            )
        )
        db.commit()
        db.add(
            DirectCampaignPeriodStat(
                client_id="client-fallback",
                campaign_id="1",
                campaign_name="Search",
                period_from=PERIOD_FROM,
                period_to=PERIOD_TO,
                impressions=1000,
                clicks=100,
                cost=91900,
                ctr=10,
                avg_cpc=919,
                conversions=919,
                goal_ids="35371875, 344527023",
                goal_conversions=None,
                conversion_source="fallback_total_when_goal_unavailable",
                conversion_warning=DIRECT_GOAL_FALLBACK_MESSAGE,
            )
        )
        db.commit()

        summary = build_performance_summary(db, "client-fallback")

        assert summary["hasGoalData"] is False
        assert summary["totals"]["conversions"] == 919
        assert summary["goalConversionsTotal"] == 0
        assert summary["totalConversionsFallback"] == 919
        assert summary["conversionsSourceMessage"]
        assert summary["syncDiagnostics"]["dataQualityLevel"] == "warning"
        assert DIRECT_GOAL_FALLBACK_MESSAGE in summary["syncDiagnostics"]["warnings"]
