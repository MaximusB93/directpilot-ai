from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors.yandex_direct import _build_search_query_report_payload
from app.db import Base
from app.models import ClientAccount, DirectSearchQueryPeriodStat
from app.services.client_sync import _direct_goal_conversion_value
from app.services.performance_summary import build_performance_summary, build_search_query_insights


PERIOD_FROM = datetime(2026, 5, 1, tzinfo=UTC)
PERIOD_TO = datetime(2026, 5, 30, tzinfo=UTC)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_search_query_report_payload_includes_goals() -> None:
    payload = _build_search_query_report_payload(
        selection_criteria={"DateFrom": "2026-05-01", "DateTo": "2026-05-30"},
        report_period="2026-05-01 2026-05-30",
        date_range_type="CUSTOM_DATE",
        limit=1000,
        goal_ids=["35371875", "344527023"],
    )

    params = payload["params"]
    assert params["ReportType"] == "SEARCH_QUERY_PERFORMANCE_REPORT"
    assert params["Goals"] == [35371875, 344527023]
    assert "Query" in params["FieldNames"]
    assert "Conversions" in params["FieldNames"]


def test_goal_specific_search_query_conversions_are_parsed() -> None:
    row = {
        "Query": "irrelevant traffic",
        "Conversions_35371875_LSC": "2",
        "Conversions_344527023_LSC": "3",
        "Conversions": "5",
        "_TotalConversions": "20",
    }

    assert _direct_goal_conversion_value(row, ["35371875", "344527023"]) == 5


def test_search_query_insights_recommend_negative_for_costly_zero_goal_query() -> None:
    rows = [
        DirectSearchQueryPeriodStat(
            client_id="client-1",
            campaign_id="campaign-1",
            campaign_name="Search",
            ad_group_id="adgroup-1",
            ad_group_name="Core",
            query="free unrelated request",
            period_from=PERIOD_FROM,
            period_to=PERIOD_TO,
            impressions=1000,
            clicks=12,
            cost=600,
            ctr=1.2,
            avg_cpc=50,
            conversions=0,
            goal_conversions=0,
            conversion_source="yandex_direct_goals",
            issue_flags="candidate_negative_keyword,costly_no_goal_conversion",
            recommended_negative_keyword="free unrelated request",
            recommendation_reason="Запрос получил расход без конверсий.",
        )
    ]

    insights = build_search_query_insights(rows)

    assert insights["candidateNegativeKeywords"] == 1
    assert insights["totalWasteCost"] == 600
    assert insights["insights"][0]["recommendedNegativeKeyword"] == "free unrelated request"


def test_search_query_with_conversions_is_not_negative_candidate() -> None:
    rows = [
        DirectSearchQueryPeriodStat(
            client_id="client-1",
            campaign_id="campaign-1",
            campaign_name="Search",
            ad_group_id="adgroup-1",
            ad_group_name="Core",
            query="brand buy",
            period_from=PERIOD_FROM,
            period_to=PERIOD_TO,
            impressions=1000,
            clicks=30,
            cost=900,
            ctr=3.0,
            avg_cpc=30,
            conversions=5,
            goal_conversions=2,
            conversion_source="yandex_direct_goals",
            issue_flags=None,
            recommended_negative_keyword=None,
            recommendation_reason=None,
        )
    ]

    insights = build_search_query_insights(rows)

    assert insights["candidateNegativeKeywords"] == 0
    assert insights["insights"][0]["recommendedNegativeKeyword"] is None


def test_performance_summary_includes_search_query_insights() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        db.add(ClientAccount(id="client-summary", name="Client Summary", segment="Test", conversion_goal_ids="35371875"))
        db.add(
            DirectSearchQueryPeriodStat(
                client_id="client-summary",
                campaign_id="campaign-1",
                campaign_name="Search",
                ad_group_id="adgroup-1",
                ad_group_name="Core",
                query="cheap irrelevant lead",
                period_from=PERIOD_FROM,
                period_to=PERIOD_TO,
                impressions=900,
                clicks=15,
                cost=750,
                ctr=1.6,
                avg_cpc=50,
                conversions=0,
                goal_conversions=0,
                conversion_source="yandex_direct_goals",
                issue_flags="candidate_negative_keyword,costly_no_goal_conversion",
                recommended_negative_keyword="cheap irrelevant lead",
                recommendation_reason="Запрос получил расход без конверсий.",
            )
        )
        db.commit()

        summary = build_performance_summary(db, "client-summary")

        assert summary["searchQueryInsights"]["totalQueries"] == 1
        assert summary["searchQueryInsights"]["candidateNegativeKeywords"] == 1
