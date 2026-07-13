from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import DirectCampaignPeriodStat, DirectSearchQueryPeriodStat
from app.schemas import AuditDataRequest
from app.services.audit_data_tools import (
    collect_audit_data_requests,
    public_audit_tool_manifest,
    validate_audit_data_requests,
)


def _db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    period_from = datetime(2026, 6, 10, tzinfo=UTC)
    period_to = datetime(2026, 7, 9, tzinfo=UTC)
    db.add_all([
        DirectSearchQueryPeriodStat(
            client_id="client-a", campaign_id="secret-id", campaign_name="Поиск Бренд",
            ad_group_id="group-id", ad_group_name="Бренд", query="купить бренд", period_from=period_from,
            period_to=period_to, impressions=100, clicks=10, cost=500, ctr=10, avg_cpc=50,
            conversions=2, goal_ids="123", goal_conversions=2, goal_cpa=250,
        ),
        DirectCampaignPeriodStat(
            client_id="client-a", campaign_id="secret-id", campaign_name="Поиск Бренд",
            period_from=period_from, period_to=period_to, impressions=100, clicks=10, cost=500,
            ctr=10, avg_cpc=50, conversions=3, goal_ids="123", goal_conversions=2, goal_cpa=250,
        ),
    ])
    db.commit()
    return db


def _request(*, family="search", subtype="brand_search", dimension="search_queries", request_id="req-1") -> AuditDataRequest:
    return AuditDataRequest(
        request_id=request_id,
        hypothesis_id="hyp-1",
        campaign_name="Поиск Бренд",
        campaign_family=family,
        campaign_subtype=subtype,
        dimension=dimension,
        reason="Проверить гипотезу",
        period={"date_from": "2026-06-10", "date_to": "2026-07-09", "days": 30},
        filters={"campaign_name": "Поиск Бренд"},
        metrics=["query", "clicks", "cost", "conversions", "cpa", "unsafe_field"],
        priority="high",
        required_for_conclusion=True,
    )


def test_search_query_adapter_collects_saved_rows_without_internal_ids():
    db = _db()
    accepted, rejected = validate_audit_data_requests([_request()])
    results, direct_calls = collect_audit_data_requests(db, "client-a", accepted)

    assert rejected == []
    assert direct_calls == 0
    assert results[0].status == "collected"
    assert results[0].rows_analyzed == 1
    assert results[0].data[0]["query"] == "купить бренд"
    assert "campaign_id" not in str(results[0].data)
    assert "group-id" not in str(results[0].data)
    assert "unsafe_field" not in accepted[0].metrics


def test_search_queries_are_not_applicable_to_yan_retargeting():
    accepted, rejected = validate_audit_data_requests([
        _request(family="yan", subtype="yan_retargeting", dimension="search_queries")
    ])

    assert accepted == []
    assert rejected[0].status == "not_applicable"
    assert rejected[0].error_code == "dimension_not_applicable"


def test_unknown_campaign_type_cannot_request_specialized_dimension():
    accepted, rejected = validate_audit_data_requests([
        _request(family="unknown", subtype="unknown", dimension="retargeting_segments")
    ])

    assert accepted == []
    assert rejected[0].status == "unsupported"
    assert rejected[0].error_code == "unsupported_campaign_type"


def test_live_capability_without_trusted_client_returns_unavailable():
    request = _request(family="yan", subtype="yan_retargeting", dimension="placements")
    accepted, rejected = validate_audit_data_requests([request])
    results, _ = collect_audit_data_requests(_db(), "client-a", accepted)

    assert rejected == []
    assert results[0].status == "unavailable"
    assert results[0].error_code == "direct_no_data"


def test_registry_is_read_only_and_does_not_expose_endpoints_or_credentials():
    manifest = public_audit_tool_manifest()

    assert manifest
    assert all(item["read_only"] is True for item in manifest)
    assert "token" not in str(manifest).lower()
    assert "authorization" not in str(manifest).lower()
    assert "endpoint" not in str(manifest).lower()


def test_data_request_forbids_extra_fields():
    payload = _request().model_dump()
    payload["campaign_id"] = "must-not-be-trusted"
    with pytest.raises(ValidationError):
        AuditDataRequest.model_validate(payload)
