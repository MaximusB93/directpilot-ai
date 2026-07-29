import asyncio
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.services.ai_audit_jobs as audit_jobs
from app.db import Base
from app.models import ClientAccount, DirectReportJob, Organization, User
from app.schemas import AiAuditCreateRequest, AuditDataRequest
from app.services.audit_evidence_reconciliation import (
    build_canonical_evidence_index,
    campaign_scope_key,
    canonical_coverage_projection,
    capability_candidates,
)
from app.services.audit_scheduler import (
    build_minimum_coverage_requests,
    execution_profile_for_scope,
    initialize_scheduler_state,
    partition_breadth_and_depth_requests,
    scheduler_deadline_state,
    scheduler_health,
)


def _db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    db.add_all([
        Organization(id="org-a", name="A"),
        User(id="user-a", organization_id="org-a", email="a@example.com", provider="email"),
        ClientAccount(id="client-a", organization_id="org-a", name="Client A"),
    ])
    db.commit()
    return db


def _job(db: Session):
    return audit_jobs.create_audit_job(
        db,
        AiAuditCreateRequest(
            client_id="client-a", model="qwen/qwen3-14b", ai_preset="balanced",
            max_tokens=2500, cache_policy="fresh",
        ),
        organization_id="org-a",
        user_id="user-a",
        user_email="a@example.com",
    )


def _request(request_id: str = "breadth_001") -> AuditDataRequest:
    return AuditDataRequest(
        request_id=request_id,
        hypothesis_id="breadth_001",
        campaign_name="Search A",
        campaign_family="search",
        campaign_subtype="search",
        dimension="search_queries",
        capability_id="search_queries",
        reason="Minimum coverage",
        filters={"campaign_name": "Search A"},
    )


def test_execution_profiles_persist_deadlines_and_finalization_reserve():
    started = datetime(2026, 7, 16, 10, 0, tzinfo=UTC)
    full_snapshot = {}
    full = initialize_scheduler_state(full_snapshot, scope="full_account", started_at=started)
    short_snapshot = {}
    short = initialize_scheduler_state(short_snapshot, scope="short_summary", started_at=started)

    assert execution_profile_for_scope(None).id == "full_account"
    assert full["softTargetAt"] == (started + timedelta(minutes=7)).isoformat()
    assert full["hardDeadlineAt"] == (started + timedelta(minutes=10)).isoformat()
    assert full["collectionDeadlineAt"] == (started + timedelta(minutes=8)).isoformat()
    assert short["softTargetAt"] == (started + timedelta(minutes=3)).isoformat()
    assert short["hardDeadlineAt"] == (started + timedelta(minutes=5)).isoformat()
    assert short["collectionDeadlineAt"] == (started + timedelta(seconds=225)).isoformat()
    assert short["maxDepthRounds"] == 1


def test_breadth_requests_cover_each_applicable_campaign_before_depth():
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-01", "dateTo": "2026-06-30", "days": 30},
        "campaignClassifications": [
            {"campaign_name": "Search A", "campaign_family": "search", "campaign_subtype": "search"},
            {"campaign_name": "YAN A", "campaign_family": "yan", "campaign_subtype": "yan_retargeting"},
        ],
    }
    breadth = build_minimum_coverage_requests(snapshot)
    by_campaign = {}
    for request in breadth:
        by_campaign.setdefault(request.campaign_name, set()).add(request.capability_id)

    assert {"Search A", "YAN A"} == set(by_campaign)
    assert {"ad_groups", "ads", "keywords", "search_queries", "goals"} <= by_campaign["Search A"]
    assert "search_queries" not in by_campaign["YAN A"]
    assert {"placements", "audience_targets", "retargeting_segments", "frequency"} <= by_campaign["YAN A"]

    depth = AuditDataRequest(
        request_id="depth_001", hypothesis_id="hyp_001", campaign_name="Search A",
        campaign_family="search", campaign_subtype="search", dimension="demographics",
        capability_id="demographics", reason="Deep investigation",
        filters={"campaign_name": "Search A"},
    )
    breadth_partition, depth_partition = partition_breadth_and_depth_requests(
        [depth, *breadth], breadth, profile=execution_profile_for_scope("full_account"),
    )
    assert {_request.campaign_name for _request in breadth_partition} == {"Search A", "YAN A"}
    assert [item.capability_id for item in depth_partition] == ["demographics"]


def test_scheduler_health_distinguishes_expected_wait_from_delay_and_recovery():
    now = datetime(2026, 7, 16, 10, 2, tzinfo=UTC)
    waiting = {"auditRuntime": {
        "lastProgressAt": (now - timedelta(minutes=3)).isoformat(),
        "waitingReason": "direct_report_queue",
        "nextRetryAt": (now + timedelta(seconds=30)).isoformat(),
    }}
    delayed = {"auditRuntime": {"lastProgressAt": (now - timedelta(seconds=70)).isoformat()}}
    recovering = {"auditRuntime": {"lastProgressAt": (now - timedelta(seconds=95)).isoformat()}}

    assert scheduler_health(waiting, now)["status"] == "waiting"
    assert scheduler_health(delayed, now)["status"] == "delayed"
    assert scheduler_health(recovering, now)["status"] == "recovering"


def test_canonical_campaign_matrix_distinguishes_collected_insufficient_and_not_requested():
    snapshot = {"minimumCoveragePlan": [
        {"campaignName": "Search A", "capabilityId": "search_queries", "applicable": True},
        {"campaignName": "YAN A", "capabilityId": "placements", "applicable": True},
        {"campaignName": "Search B", "capabilityId": "goals", "applicable": True},
    ]}
    index = {"entries": [
        {
            "scope": "campaign", "campaignName": "Search A", "capabilityId": "search_queries",
            "status": "collected", "rowsReceived": 12, "rowsAnalyzedByBackend": 12,
            "rowsSentToAi": 8, "source": "yandex_direct_live_report", "limitations": [],
        },
        {
            "scope": "campaign", "campaignName": "YAN A", "capabilityId": "placements",
            "status": "insufficient_data", "rowsReceived": 0, "rowsAnalyzedByBackend": 0,
            "rowsSentToAi": 0, "source": "yandex_direct_live_report", "limitations": ["low_data"],
        },
    ]}

    projection = canonical_coverage_projection(index, snapshot)
    statuses = {
        (item["campaignName"], item["capabilityId"]): item["status"]
        for item in projection["campaignMatrix"]
    }

    assert statuses[("Search A", "search_queries")] == "collected"
    assert statuses[("YAN A", "placements")] == "insufficient_data"
    assert statuses[("Search B", "goals")] == "not_requested"
    assert projection["summary"]["coveredCampaigns"] == 2
    assert projection["summary"]["applicableCampaigns"] == 3
    public_dump = json.dumps(projection)
    for forbidden in ("CampaignId", "AdGroupId", "request_hash", "raw_rows"):
        assert forbidden not in public_dump


def test_controlled_retargeting_data_alias_resolves_without_fuzzy_matching():
    assert "retargeting_segments" in capability_candidates("retargeting_segments_data")
    assert capability_candidates("retargeting_segment_typo") == ("retargeting_segment_typo",)


def test_collection_deadline_transitions_to_finalization_without_direct_call(monkeypatch):
    db = _db()
    job = _job(db)
    request = _request()
    now = datetime.now(UTC)
    snapshot = {
        "analysisPeriod": {},
        "auditRuntime": {
            "executionProfile": "full_account",
            "schedulerPhase": "breadth",
            "collectionDeadlineAt": (now - timedelta(seconds=1)).isoformat(),
            "hardDeadlineAt": (now + timedelta(minutes=1)).isoformat(),
            "lastProgressAt": (now - timedelta(seconds=10)).isoformat(),
        },
        "minimumCoveragePlan": [{
            "campaignName": "Search A", "capabilityId": "search_queries", "applicable": True,
        }],
        "evidenceCoverageRegistry": [{
            "requirementId": "req-search-a-search-queries",
            "campaignName": "Search A",
            "signal": "search_query_waste",
            "dimension": "search_queries",
            "status": "planned",
            "source": None,
            "reasonCode": None,
            "rowsAnalyzed": 0,
            "limitations": [],
            "requestIds": [request.request_id],
        }],
        "validatedDataRequests": [request.model_dump(mode="json")],
        "pendingDataRequests": [request.model_dump(mode="json")],
        "processingDataRequests": [],
        "deferredDepthDataRequests": [],
    }
    job.status = "context_ready"
    job.current_stage = "collect_live_data"
    job.started_at = now - timedelta(minutes=9)
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.commit()
    direct_calls = {"count": 0}

    def forbidden_direct(*args, **kwargs):
        direct_calls["count"] += 1
        raise AssertionError("Direct must not be called after the collection deadline")

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    advanced = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    persisted = audit_jobs._json_load(advanced.context_snapshot_json, {})

    assert direct_calls["count"] == 0
    assert advanced.status == "context_ready"
    assert advanced.current_stage == "generate_answer"
    assert persisted["auditRuntime"]["schedulerPhase"] == "finalization"
    assert persisted["auditRuntime"]["stopReason"] == "collection_deadline_reached"
    assert audit_jobs._load_full_drilldown_results(db, advanced)[0]["status"] == "skipped_budget_limit"

    persisted["auditRuntime"]["hardDeadlineAt"] = (now - timedelta(seconds=1)).isoformat()
    advanced.context_snapshot_json = audit_jobs._json_dump(persisted)
    db.commit()

    async def forbidden_provider(*args, **kwargs):
        raise AssertionError("Final provider must not be called after the hard deadline")

    monkeypatch.setattr(audit_jobs, "generate_openrouter_response", forbidden_provider)
    completed = asyncio.run(audit_jobs.advance_audit_job(db, advanced.id, organization_id="org-a"))
    result = audit_jobs._json_load(completed.result_json, {})

    assert completed.status == "completed"
    assert result["backendFallbackUsed"] is True
    assert result["auditCompletionState"] == "partial_coverage"


def test_processing_report_is_not_polled_before_next_retry(monkeypatch):
    db = _db()
    job = _job(db)
    request = _request()
    now = datetime.now(UTC)
    snapshot = {
        "auditRuntime": {
            "executionProfile": "full_account", "schedulerPhase": "breadth",
            "collectionDeadlineAt": (now + timedelta(minutes=5)).isoformat(),
            "hardDeadlineAt": (now + timedelta(minutes=7)).isoformat(),
            "lastProgressAt": now.isoformat(),
        },
        "pendingDataRequests": [],
        "processingDataRequests": [request.model_dump(mode="json")],
    }
    job.status = "context_ready"
    job.current_stage = "wait_for_offline_reports"
    job.started_at = now
    job.context_snapshot_json = audit_jobs._json_dump(snapshot)
    db.add(DirectReportJob(
        audit_job_id=job.id,
        client_id=job.client_id,
        capability_id="search_queries",
        request_hash="safe-test-hash",
        report_name="audit-test",
        report_spec_json="{}",
        status="waiting_for_report_queue",
        next_retry_at=now + timedelta(seconds=45),
    ))
    db.commit()
    direct_calls = {"count": 0}

    def forbidden_direct(*args, **kwargs):
        direct_calls["count"] += 1
        raise AssertionError("Direct must not be called before nextRetryAt")

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    waiting = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))
    runtime = audit_jobs._json_load(waiting.context_snapshot_json, {})["auditRuntime"]

    assert direct_calls["count"] == 0
    assert waiting.current_stage == "wait_for_offline_reports"
    assert runtime["waitingReason"] == "direct_report_queue"
    assert runtime["nextRetryAt"] is not None


def test_pending_report_blocks_direct_calls_even_without_snapshot_processing_request(monkeypatch):
    db = _db()
    job = _job(db)
    request = _request()
    now = datetime.now(UTC)
    job.status = "context_ready"
    job.current_stage = "collect_live_data"
    job.started_at = now
    job.context_snapshot_json = audit_jobs._json_dump({
        "auditRuntime": {
            "executionProfile": "full_account", "schedulerPhase": "breadth",
            "collectionDeadlineAt": (now + timedelta(minutes=5)).isoformat(),
            "hardDeadlineAt": (now + timedelta(minutes=7)).isoformat(),
            "lastProgressAt": now.isoformat(),
        },
        "pendingDataRequests": [request.model_dump(mode="json")],
        "processingDataRequests": [],
        "deferredDepthDataRequests": [],
    })
    db.add(DirectReportJob(
        audit_job_id=job.id,
        client_id=job.client_id,
        capability_id="search_queries",
        request_hash="safe-pending-report-hash",
        report_name="audit-test",
        report_spec_json="{}",
        status="processing",
        next_retry_at=now + timedelta(seconds=45),
    ))
    db.commit()

    def forbidden_direct(*args, **kwargs):
        raise AssertionError("Direct must not be called before nextRetryAt")

    monkeypatch.setattr(audit_jobs, "collect_audit_data_requests", forbidden_direct)
    waiting = asyncio.run(audit_jobs.advance_audit_job(db, job.id, organization_id="org-a"))

    assert waiting.current_stage == "wait_for_offline_reports"
    runtime = audit_jobs._json_load(waiting.context_snapshot_json, {})["auditRuntime"]
    assert runtime["nextRetryAt"] is not None


def test_fresh_baseline_evidence_counts_toward_campaign_coverage():
    db = _db()
    job = _job(db)
    baseline = [
        {
            "request_id": "baseline_campaigns", "campaign_name": "__all_campaigns__",
            "capability_id": "campaigns", "dimension": "campaigns", "status": "collected",
            "source": "yandex_direct_live_report", "rows_total": 1, "rows_analyzed": 1,
            "data": [{
                "campaign_scope_key": campaign_scope_key("direct-search-a"),
                "name": "Search A", "type": "TEXT_CAMPAIGN",
            }],
        },
        {
            "request_id": "baseline_campaign_performance", "campaign_name": "__all_campaigns__",
            "capability_id": "campaign_performance", "dimension": "campaign_performance",
            "status": "collected", "source": "yandex_direct_live_report", "rows_total": 1,
            "rows_analyzed": 1,
            "data": [{
                "campaign_scope_key": campaign_scope_key("direct-search-a"),
                "campaign_name": "Search A", "impressions": 1000, "clicks": 20, "cost": 500,
            }],
        },
    ]
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-01", "dateTo": "2026-06-30", "days": 30},
        "targetKpis": {"targetCpa": 500},
        "selectedGoals": {"ids": [], "hasGoalData": False},
        "minimumCoveragePlan": [
            {"campaignName": "Search A", "capabilityId": "campaign_settings", "applicable": True},
            {"campaignName": "Search A", "capabilityId": "campaign_performance", "applicable": True},
        ],
    }
    audit_jobs._apply_live_baseline(snapshot, baseline, allow_saved_fallback=False)
    audit_jobs._save_full_baseline_results(db, job, baseline)

    audit_jobs._refresh_scheduler_coverage(snapshot, audit_jobs._load_full_evidence_results(db, job))

    coverage = snapshot["canonicalEvidenceCoverage"]
    assert coverage["summary"]["coveredCampaigns"] == 1
    assert {(item["capabilityId"], item["status"]) for item in coverage["campaignMatrix"]} == {
        ("campaign_settings", "collected"),
        ("campaign_performance", "collected"),
    }


def test_performance_only_campaign_scope_keeps_no_data_follow_up_terminal():
    report_scope = campaign_scope_key("archived-rsy")
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-01", "dateTo": "2026-06-30", "days": 30},
        "targetKpis": {"targetCpa": 500},
        "minimumCoveragePlan": [
            {"campaignName": "Archived RSYA", "capabilityId": "campaign_settings", "applicable": True},
        ],
    }
    audit_jobs._apply_live_baseline(snapshot, [{
        "capability_id": "campaigns", "status": "collected", "data": [],
    }, {
        "capability_id": "campaign_performance", "status": "collected", "data": [{
            "campaign_scope_key": report_scope, "campaign_name": "Archived RSYA", "clicks": 4,
        }],
    }], allow_saved_fallback=False)

    coverage = canonical_coverage_projection(build_canonical_evidence_index(snapshot, [{
        "request_id": "archived-settings", "campaign_name": "Archived RSYA",
        "capability_id": "campaign_settings", "status": "insufficient_data",
        "source": "yandex_direct_live_service", "rows_total": 0, "rows_analyzed": 0, "data": [],
    }]), snapshot)

    assert snapshot["_trustedCampaignScopes"]["Archived RSYA"] == report_scope
    assert coverage["campaignMatrix"][0]["status"] == "insufficient_data"


def test_unnamed_performance_campaign_keeps_safe_scope_for_terminal_follow_up():
    report_scope = campaign_scope_key("unnamed-rsya")
    snapshot = {
        "analysisPeriod": {"dateFrom": "2026-06-01", "dateTo": "2026-06-30", "days": 30},
        "targetKpis": {"targetCpa": 500},
        "minimumCoveragePlan": [
            {"campaignName": "Campaign without name 1", "capabilityId": "campaign_settings", "applicable": True},
        ],
    }
    audit_jobs._apply_live_baseline(snapshot, [{
        "capability_id": "campaigns", "status": "collected", "data": [],
    }, {
        "capability_id": "campaign_performance", "status": "collected", "data": [{
            "campaign_scope_key": report_scope, "campaign_name": "", "clicks": 4,
        }],
    }], allow_saved_fallback=False)

    coverage = canonical_coverage_projection(build_canonical_evidence_index(snapshot, [{
        "request_id": "unnamed-settings", "campaign_name": "Campaign without name 1",
        "capability_id": "campaign_settings", "status": "insufficient_data",
        "source": "yandex_direct_live_service", "rows_total": 0, "rows_analyzed": 0, "data": [],
    }]), snapshot)

    assert snapshot["_trustedCampaignScopes"]["Campaign without name 1"] == report_scope
    assert coverage["summary"]["coveredCampaigns"] == 1
    assert coverage["campaignMatrix"][0]["status"] == "insufficient_data"


def test_missing_campaign_evidence_stays_pending_during_breadth_then_becomes_unavailable():
    snapshot = {
        "minimumCoveragePlan": [
            {"campaignName": "Campaign A", "capabilityId": "campaign_settings", "applicable": True},
        ],
        "auditRuntime": {"schedulerPhase": "breadth"},
    }

    pending = canonical_coverage_projection(build_canonical_evidence_index(snapshot, []), snapshot)
    assert pending["campaignMatrix"][0]["status"] == "not_requested"

    snapshot["auditRuntime"]["schedulerPhase"] = "finalization"
    terminal = canonical_coverage_projection(build_canonical_evidence_index(snapshot, []), snapshot)

    assert terminal["campaignMatrix"][0]["status"] == "unavailable"
    assert terminal["campaignMatrix"][0]["absenceReason"] == "missing_reconciled_evidence"
    assert terminal["summary"] == {
        "accountCapabilities": 0,
        "campaignCapabilities": 0,
        "rowsReceived": 0,
        "rowsAnalyzedByBackend": 0,
        "rowsSentToAi": 0,
        "applicableCampaigns": 1,
        "coveredCampaigns": 1,
        "campaignsWithCollectedData": [],
    }


def test_old_snapshot_without_scheduler_fields_remains_readable():
    snapshot = {"auditRuntime": {"requestsCount": 3}}
    runtime = audit_jobs._audit_runtime(snapshot)

    assert runtime["requestsCount"] == 3
    assert runtime["executionProfile"] == "full_account"
    assert scheduler_deadline_state(snapshot)["hardDeadlineReached"] is False
    assert scheduler_health(snapshot)["status"] == "working"
