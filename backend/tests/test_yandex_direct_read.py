from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector, YandexDirectReadError
from app.db import Base
from app.models import ClientAccount, ConnectedAccount, DirectCampaignPeriodStat, DirectReadCache, DirectReportJob, Organization
from app.schemas import AuditDataRequest
from app.services.audit_data_tools import collect_audit_data_requests, validate_audit_data_requests
from app.services import yandex_direct_read as direct_read
from app.services.yandex_direct_read_capabilities import (
    YANDEX_DIRECT_READ_CAPABILITIES,
    validate_capability_definition,
)


def _response(status: int, *, text: str = "", headers: dict[str, str] | None = None, json_body=None):
    request = httpx.Request("POST", "https://api.direct.yandex.com/json/v5/reports")
    if json_body is not None:
        return httpx.Response(status, request=request, headers=headers, json=json_body)
    return httpx.Response(status, request=request, headers=headers, text=text)


def _db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    db.add(Organization(id="org-a", name="A"))
    db.add(ConnectedAccount(
        id="account-a",
        organization_id="org-a",
        provider="yandex",
        external_user_id="user-a",
        status="connected",
    ))
    db.add(ClientAccount(
        id="client-a",
        organization_id="org-a",
        name="Клиент",
        direct_login="safe-login",
        yandex_account_id="account-a",
        conversion_goal_ids="123,456",
    ))
    db.add(DirectCampaignPeriodStat(
        client_id="client-a",
        campaign_id="101",
        campaign_name="Поиск Бренд",
        period_from=datetime(2026, 6, 10, tzinfo=UTC),
        period_to=datetime(2026, 7, 9, tzinfo=UTC),
        impressions=100,
        clicks=10,
        cost=500,
        ctr=10,
        avg_cpc=50,
        conversions=3,
        goal_ids="123,456",
        goal_conversions=2,
        goal_cpa=250,
    ))
    db.commit()
    return db


def test_live_read_rejects_account_from_another_organization(monkeypatch):
    db = _db()
    db.add(Organization(id="org-b", name="B"))
    db.add(ConnectedAccount(
        id="account-b",
        organization_id="org-b",
        provider="yandex",
        external_user_id="user-b",
        status="connected",
    ))
    client = db.get(ClientAccount, "client-a")
    client.yandex_account_id = "account-b"
    db.commit()
    monkeypatch.setattr(direct_read, "get_yandex_access_token_for_account", lambda *args: "secret")

    with pytest.raises(YandexDirectReadError) as exc:
        direct_read.execute_direct_read(db, "client-a", _request())

    assert exc.value.code == "direct_permission_denied"


def _request(
    dimension: str = "devices",
    *,
    request_id: str = "req-1",
    hypothesis_id: str = "hyp-1",
    family: str = "search",
    subtype: str = "brand_search",
    preference: str = "live_required",
) -> AuditDataRequest:
    return AuditDataRequest(
        request_id=request_id,
        hypothesis_id=hypothesis_id,
        campaign_name="Поиск Бренд",
        campaign_family=family,
        campaign_subtype=subtype,
        dimension=dimension,
        reason="Проверить гипотезу",
        period={"date_from": "2026-06-10", "date_to": "2026-07-09", "days": 30},
        metrics=["impressions", "clicks", "cost", "conversions"],
        priority="high",
        required_for_conclusion=True,
        data_preference=preference,
    )


def test_object_get_is_allowlisted_forces_get_and_paginates(monkeypatch):
    payloads = []

    def fake_post(url, *, json, headers, timeout):
        payloads.append((url, json, headers))
        offset = json["params"]["Page"]["Offset"]
        body = {
            "result": {
                "Campaigns": [{"Id": offset + 1, "Name": f"Campaign {offset + 1}"}],
                "LimitedBy": 1 if offset == 0 else None,
            }
        }
        return _response(200, json_body=body)

    monkeypatch.setattr("app.connectors.yandex_direct.httpx.post", fake_post)
    connector = YandexDirectConnector(access_token="secret", client_login="login")
    rows = connector.paginate_service_get(
        "campaigns", {"SelectionCriteria": {}, "FieldNames": ["Id", "Name"]}, maximum_rows=2, page_size=1,
    )

    assert len(rows) == 2
    assert [item[1]["method"] for item in payloads] == ["get", "get"]
    assert all(item[0] == "https://api.direct.yandex.com/json/v5/campaigns" for item in payloads)
    assert all(item[2]["Authorization"] == "Bearer secret" for item in payloads)
    with pytest.raises(YandexDirectReadError, match="allowlisted"):
        connector.request_service_get("https://attacker.invalid", {})


def test_report_handles_processing_success_and_rate_limit(monkeypatch):
    responses = iter([
        _response(202, headers={"retryIn": "7", "reportsInQueue": "1"}),
        _response(200, text="CampaignId\tClicks\n101\t4\n"),
        _response(429, json_body={"error": {"error_string": "rate limit"}}),
    ])
    monkeypatch.setattr("app.connectors.yandex_direct.httpx.post", lambda *args, **kwargs: next(responses))
    connector = YandexDirectConnector(access_token="secret")

    processing = connector.request_report({"ReportName": "stable"})
    completed = connector.request_report({"ReportName": "stable"})

    assert processing["status"] == "processing"
    assert processing["retry_after_seconds"] == 7
    assert completed["rows"] == [{"CampaignId": "101", "Clicks": "4"}]
    with pytest.raises(YandexDirectReadError) as exc:
        connector.request_report({"ReportName": "stable"})
    assert exc.value.code == "direct_rate_limited"
    assert exc.value.retryable is True


def test_offline_report_persists_and_reuses_exact_spec_then_caches(monkeypatch):
    db = _db()
    monkeypatch.setattr(direct_read, "get_yandex_access_token_for_account", lambda *args: "secret")
    specs = []
    responses = iter([
        {"status": "processing", "rows": [], "retry_after_seconds": 3},
        {
            "status": "completed",
            "rows": [{
                "CampaignId": "101",
                "CampaignName": "Поиск Бренд",
                "AdGroupId": "201",
                "Device": "DESKTOP",
                "Clicks": "4",
                "Debug": {"access_token": "secret", "api_key": "secret", "password": "secret"},
            }],
            "retry_after_seconds": 0,
        },
        {
            "status": "completed",
            "rows": [{"CampaignId": "101", "CampaignName": "Поиск Бренд", "Device": "MOBILE", "Clicks": "5"}],
            "retry_after_seconds": 0,
        },
    ])

    def fake_report(self, spec, *, processing_mode="auto"):
        specs.append(spec)
        return next(responses)

    monkeypatch.setattr(YandexDirectConnector, "request_report", fake_report)
    request = _request()
    first = direct_read.execute_direct_read(db, "client-a", request, audit_job_id="audit-a")
    report_job = db.scalar(select(DirectReportJob))

    assert first.result.status == "processing"
    assert first.result.error_code == "direct_report_processing"
    assert report_job.status == "processing"
    assert report_job.report_name == specs[0]["ReportName"]
    assert specs[0]["SelectionCriteria"]["Filter"][0]["Values"] == ["101"]
    assert specs[0]["Goals"] == [123, 456]
    assert specs[0]["AttributionModels"] == ["AUTO"]

    report_job.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    second = direct_read.execute_direct_read(db, "client-a", request, audit_job_id="audit-a")

    assert second.result.status == "collected"
    assert specs[1] == specs[0]
    assert second.result.data[0]["campaign_name"] == "Поиск Бренд"
    assert "campaign_id" not in second.result.data[0]
    assert "ad_group_id" not in second.result.data[0]
    assert second.result.data[0]["debug"] == {}
    assert db.scalar(select(DirectReadCache)).rows_count == 1

    third = direct_read.execute_direct_read(db, "client-a", request, audit_job_id="audit-a")
    assert third.result.status == "cached"
    assert third.result.source == "yandex_direct_cached_live"
    assert len(specs) == 2

    cache = db.scalar(select(DirectReadCache))
    report_job = db.scalar(select(DirectReportJob))
    cache.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    report_job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    refreshed = direct_read.execute_direct_read(db, "client-a", request, audit_job_id="audit-a")

    assert refreshed.result.status == "collected"
    assert refreshed.result.data[0]["device"] == "MOBILE"
    assert len(specs) == 3


def test_duplicate_semantic_requests_make_one_live_call(monkeypatch):
    db = _db()
    monkeypatch.setattr(direct_read, "get_yandex_access_token_for_account", lambda *args: "secret")
    calls = {"count": 0}

    def fake_get(self, service, params, *, maximum_rows, page_size):
        calls["count"] += 1
        assert service == "campaigns"
        return [{"Id": 101, "Name": "Поиск Бренд", "Status": "ACCEPTED", "Type": "TEXT_CAMPAIGN"}]

    monkeypatch.setattr(YandexDirectConnector, "paginate_service_get", fake_get)
    requests = [
        _request("campaigns", request_id="req-1", hypothesis_id="hyp-1"),
        _request("campaigns", request_id="req-2", hypothesis_id="hyp-2"),
    ]
    accepted, rejected = validate_audit_data_requests(requests)
    results, direct_calls = collect_audit_data_requests(db, "client-a", accepted, audit_job_id="audit-a")

    assert rejected == []
    assert calls["count"] == 1
    assert direct_calls == 1
    assert [item.request_id for item in results] == ["req-1", "req-2"]
    assert all(item.status == "collected" for item in results)
    assert all(item.live_attempted for item in results)


def test_live_required_never_silently_uses_saved_rows():
    db = _db()
    request = _request("goals", preference="live_required")
    accepted, _ = validate_audit_data_requests([request])
    results, _ = collect_audit_data_requests(db, "client-a", accepted)

    assert results[0].source != "directpilot_saved_stats"
    assert results[0].status in {"failed", "unavailable"}
    assert results[0].live_attempted is True


def test_live_preferred_saved_fallback_preserves_safe_live_diagnostics(monkeypatch):
    db = _db()
    request = _request("goals", preference="live_preferred")
    accepted, _ = validate_audit_data_requests([request])

    def failed_live(*args, **kwargs):
        raise YandexDirectReadError("direct_rate_limited", "rate limited", retryable=True)

    monkeypatch.setattr("app.services.audit_data_tools.execute_direct_read", failed_live)
    results, direct_calls = collect_audit_data_requests(db, "client-a", accepted)

    assert direct_calls == 0
    assert results[0].source == "directpilot_saved_stats"
    assert results[0].status == "collected"
    assert results[0].live_attempted is True
    assert results[0].live_error_code == "direct_rate_limited"
    assert results[0].saved_fallback is True


def test_capability_validation_rejects_unknown_report_type_and_incompatible_fields():
    base = YANDEX_DIRECT_READ_CAPABILITIES["campaign_performance"]
    with pytest.raises(ValueError, match="Unsupported Yandex Direct report type"):
        validate_capability_definition(replace(base, report_type="UNSAFE_REPORT"))

    incompatible = replace(
        base,
        incompatible_fields=(("CampaignId", "CampaignName"),),
    )
    with pytest.raises(ValueError, match="Incompatible report fields"):
        validate_capability_definition(incompatible)

    criteria = YANDEX_DIRECT_READ_CAPABILITIES["criteria_performance"]
    assert "CriterionId" in criteria.api_fields
    assert "CriteriaId" not in criteria.api_fields
    with pytest.raises(ValueError, match="Incompatible report fields"):
        validate_capability_definition(replace(
            criteria,
            api_fields=criteria.api_fields + ("CriteriaId",),
        ))


def test_goal_ids_are_split_into_valid_report_batches():
    batches = direct_read.split_report_goal_ids([str(index) for index in range(1, 24)])

    assert [len(batch) for batch in batches] == [10, 10, 3]
    assert all(len(batch) <= direct_read.MAX_REPORT_GOALS for batch in batches)


def test_report_pagination_persists_500_500_200_rows(monkeypatch):
    db = _db()
    monkeypatch.setattr(direct_read, "get_yandex_access_token_for_account", lambda *args: "secret")
    specs = []

    def fake_report(self, spec, *, processing_mode="auto"):
        specs.append(spec)
        offset = int(spec["Page"]["Offset"])
        count = 500 if offset < 1000 else 200
        return {
            "status": "completed",
            "rows": [
                {
                    "CampaignId": "101",
                    "CampaignName": "Search Brand",
                    "AdGroupId": "201",
                    "AdGroupName": "Group",
                    "Query": f"query-{index}",
                    "Clicks": "1",
                    "Cost": "10",
                }
                for index in range(offset, offset + count)
            ],
            "limited_by": offset + count if offset < 1000 else None,
        }

    monkeypatch.setattr(YandexDirectConnector, "request_report", fake_report)
    request = _request("search_queries", family="search", subtype="search")

    first = direct_read.execute_direct_read(db, "client-a", request, audit_job_id="audit-a", cache_policy="fresh")
    job = db.scalar(select(DirectReportJob))
    assert first.result.status == "processing"
    assert (job.rows_collected, job.next_offset, job.pages_completed, job.limited_by) == (500, 500, 1, 500)

    job.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    second = direct_read.execute_direct_read(db, "client-a", request, audit_job_id="audit-a", cache_policy="fresh")
    db.flush()
    db.refresh(job)
    assert second.result.status == "processing"
    assert (job.rows_collected, job.next_offset, job.pages_completed, job.limited_by) == (1000, 1000, 2, 1000)

    job.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    third = direct_read.execute_direct_read(db, "client-a", request, audit_job_id="audit-a", cache_policy="fresh")
    db.flush()
    db.refresh(job)
    assert third.result.status == "collected"
    assert len(third.result.data) == 1200
    assert (job.rows_collected, job.pages_completed, job.limited_by) == (1200, 3, 1000)
    assert [spec["Page"]["Offset"] for spec in specs] == [0, 500, 1000]


def test_report_queue_limit_is_shared_by_clients_of_connected_account(monkeypatch):
    db = _db()
    db.add(ClientAccount(
        id="client-b",
        organization_id="org-a",
        name="Second client",
        direct_login="safe-login",
        yandex_account_id="account-a",
        conversion_goal_ids="123",
    ))
    db.add(DirectCampaignPeriodStat(
        client_id="client-b",
        campaign_id="101",
        campaign_name="Search Brand",
        period_from=datetime(2026, 6, 10, tzinfo=UTC),
        period_to=datetime(2026, 7, 9, tzinfo=UTC),
        impressions=100,
        clicks=10,
        cost=500,
    ))
    for index in range(direct_read.MAX_PROCESSING_REPORTS_PER_ACCOUNT):
        db.add(DirectReportJob(
            client_id="client-a",
            capability_id="devices",
            request_hash=f"active-{index}",
            report_name=f"active-{index}",
            report_spec_json="{}",
            status="processing",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        ))
    db.commit()
    monkeypatch.setattr(direct_read, "get_yandex_access_token_for_account", lambda *args: "secret")

    def forbidden_report(*args, **kwargs):
        raise AssertionError("Shared account queue guard must run before Direct API")

    monkeypatch.setattr(YandexDirectConnector, "request_report", forbidden_report)
    request = AuditDataRequest(
        **{
            **_request("devices").model_dump(mode="json"),
            "campaign_name": "Search Brand",
            "filters": {"campaign_name": "Search Brand"},
        }
    )
    outcome = direct_read.execute_direct_read(db, "client-b", request, audit_job_id="audit-b", cache_policy="fresh")

    assert outcome.result.status == "processing"
    assert outcome.result.error_code == "direct_report_queue_full"


def test_prefer_cache_reuses_valid_cache_and_fresh_bypasses_it(monkeypatch):
    db = _db()
    monkeypatch.setattr(direct_read, "get_yandex_access_token_for_account", lambda *args: "secret")
    calls = {"count": 0}

    def fake_get(self, service, params, *, maximum_rows, page_size):
        calls["count"] += 1
        return [{"Id": 101, "Name": "Поиск Бренд", "Status": "ACCEPTED", "Type": "TEXT_CAMPAIGN"}]

    monkeypatch.setattr(YandexDirectConnector, "paginate_service_get", fake_get)
    request = _request("campaigns")

    first = direct_read.execute_direct_read(db, "client-a", request, cache_policy="prefer_cache")
    cached = direct_read.execute_direct_read(db, "client-a", request, cache_policy="prefer_cache")
    fresh = direct_read.execute_direct_read(db, "client-a", request, cache_policy="fresh")

    assert first.result.status == "collected"
    assert cached.result.status == "cached"
    assert fresh.result.status == "collected"
    assert fresh.result.freshness == "live"
    assert calls["count"] == 2


def test_empty_live_result_stays_insufficient_in_negative_cache(monkeypatch):
    db = _db()
    monkeypatch.setattr(direct_read, "get_yandex_access_token_for_account", lambda *args: "secret")
    calls = {"count": 0}

    def fake_get(self, service, params, *, maximum_rows, page_size):
        calls["count"] += 1
        return []

    monkeypatch.setattr(YandexDirectConnector, "paginate_service_get", fake_get)
    request = _request("campaigns")

    first = direct_read.execute_direct_read(db, "client-a", request, cache_policy="prefer_cache")
    cached = direct_read.execute_direct_read(db, "client-a", request, cache_policy="prefer_cache")

    assert first.result.status == "insufficient_data"
    assert cached.result.status == "insufficient_data"
    assert cached.result.cached is True
    assert calls["count"] == 1


def test_cache_hash_changes_with_capability_and_knowledge_versions():
    db = _db()
    client = db.get(ClientAccount, "client-a")
    request = _request("campaigns")
    capability = YANDEX_DIRECT_READ_CAPABILITIES["campaigns"]
    original = direct_read._trusted_spec(client, capability, request, ["101"])
    changed_capability = replace(
        capability,
        knowledge_version="v-next",
        capability_schema_version="v-next",
    )
    changed = direct_read._trusted_spec(client, changed_capability, request, ["101"])

    assert direct_read._request_hash(original) != direct_read._request_hash(changed)
