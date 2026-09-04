import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import CurrentUser, get_current_session_user
from app.core.config import settings as base_settings
from app.db import Base, get_optional_db
from app.models import ClientAccount, DirectCampaignDailyStat, MorningDigest, Organization, User
from app.services.morning_digest import (
    ACTION_TEMPLATES,
    DIGEST_MAX_FINDINGS,
    SCOPE_ACCOUNT,
    SCOPE_CAMPAIGN,
    SIGNAL_CAMPAIGN_STOPPED,
    SIGNAL_CPA_GROWTH,
    SIGNAL_SPEND_SPIKE,
    STATUS_NO_DATA,
    STATUS_OK,
    DigestFinding,
    build_digest_findings,
    run_client_digest,
    run_digests,
    select_findings,
)

DIGEST_DATE = date(2026, 9, 2)
SAME_WEEKDAY_PREV_WEEK = DIGEST_DATE - timedelta(days=7)


def _session():
    # TestClient runs the app in another thread, and an in-memory SQLite
    # connection is bound to the thread that created it.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _client(db, client_id: str = "client-1", *, target_cpa: int | None = None, organization_id: str | None = None):
    client = ClientAccount(
        id=client_id,
        name="Digest Client",
        segment="Test",
        target_cpa=target_cpa,
        organization_id=organization_id,
    )
    db.add(client)
    db.commit()
    return client


def _row(
    db,
    stat_date: date,
    *,
    client_id: str = "client-1",
    campaign_id: str = "1",
    campaign_name: str = "Поиск | Бренд",
    cost: float = 1000.0,
    clicks: int = 100,
    impressions: int = 1000,
    conversions: float | None = 10.0,
) -> None:
    db.add(
        DirectCampaignDailyStat(
            client_id=client_id,
            stat_date=stat_date,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            impressions=impressions,
            clicks=clicks,
            cost=cost,
            ctr=(clicks / impressions * 100) if impressions else 0.0,
            avg_cpc=(cost / clicks) if clicks else 0.0,
            goal_conversions=conversions,
        )
    )
    db.commit()


def _fill_week(db, **kwargs) -> None:
    """Both weekly windows, so weekly confirmation has something to read."""
    for offset in range(14):
        _row(db, DIGEST_DATE - timedelta(days=offset), **kwargs)


# ---------------------------------------------------------------------------
# 1, 2. A calm day and a day with no data are different results
# ---------------------------------------------------------------------------


def test_calm_day_gives_an_empty_digest_with_status_ok() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)
        _fill_week(db)

        findings, status = build_digest_findings(db, client, DIGEST_DATE)

        assert status == STATUS_OK
        assert findings == []


def test_missing_daily_data_gives_status_no_data() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)

        findings, status = build_digest_findings(db, client, DIGEST_DATE)

        assert status == STATUS_NO_DATA
        assert findings == []


def test_empty_digest_is_stored_like_any_other() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        _client(db)
        _fill_week(db)

        digest = run_client_digest(db, "client-1", DIGEST_DATE)

        assert digest.status == STATUS_OK
        assert digest.findings_count == 0
        assert json.loads(digest.findings_json) == []


# ---------------------------------------------------------------------------
# 3. Spend materiality
# ---------------------------------------------------------------------------


def test_material_spend_spike_reaches_the_digest() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)
        _fill_week(db)
        # Yesterday's spend jumps by an amount that is both large and material.
        db.query(DirectCampaignDailyStat).filter_by(stat_date=DIGEST_DATE).update({"cost": 20000.0})
        db.commit()

        findings, status = build_digest_findings(db, client, DIGEST_DATE)

        assert status == STATUS_OK
        spikes = [item for item in findings if item.signal == SIGNAL_SPEND_SPIKE]
        assert spikes
        assert spikes[0].money_at_stake is not None and spikes[0].money_at_stake > 0


def test_tiny_absolute_spend_change_does_not_reach_the_digest() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)
        _fill_week(db, cost=50.0, clicks=1, impressions=10, conversions=None)
        db.query(DirectCampaignDailyStat).filter_by(stat_date=DIGEST_DATE).update({"cost": 150.0})
        db.commit()

        findings, _ = build_digest_findings(db, client, DIGEST_DATE)

        assert [item for item in findings if item.signal == SIGNAL_SPEND_SPIKE] == []


# ---------------------------------------------------------------------------
# 4. CPA growth is decomposed into a lever
# ---------------------------------------------------------------------------


def test_cpa_growth_with_unchanged_cr_points_at_cpc() -> None:
    """CR held constant, so the whole CPA rise belongs to the price of a click.

    Conversions have to move as well, because metrics_core makes a CPA verdict
    inherit the significance of the conversion count (TZ-01 section 4): a CPA
    conclusion drawn on an unmoved conversion count is not trusted. Clicks and
    conversions are scaled together here, which keeps CR at 10% while CPC triples.
    """
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)
        _fill_week(db, cost=6000.0, clicks=600, impressions=6000, conversions=60.0)
        db.query(DirectCampaignDailyStat).filter_by(stat_date=DIGEST_DATE).update(
            {"clicks": 200, "goal_conversions": 20.0}
        )
        db.commit()

        findings, _ = build_digest_findings(db, client, DIGEST_DATE)

        growth = [item for item in findings if item.signal == SIGNAL_CPA_GROWTH]
        assert growth
        assert growth[0].lever == "cpc"
        assert growth[0].evidence["cr_contribution"] == 0


def test_cpa_growth_with_unchanged_cpc_points_at_cr() -> None:
    """Cost per click held constant, so the rise belongs to conversion rate."""
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)
        _fill_week(db, cost=6000.0, clicks=600, impressions=6000, conversions=60.0)
        # Same cost and same clicks, far fewer conversions.
        db.query(DirectCampaignDailyStat).filter_by(stat_date=DIGEST_DATE).update({"goal_conversions": 20.0})
        db.commit()

        findings, _ = build_digest_findings(db, client, DIGEST_DATE)

        growth = [item for item in findings if item.signal == SIGNAL_CPA_GROWTH]
        assert growth
        assert growth[0].lever == "cr"
        assert growth[0].evidence["cpc_contribution"] == 0


# ---------------------------------------------------------------------------
# 5, 6. Selection rules
# ---------------------------------------------------------------------------


def _finding(signal: str, money: float | None, *, scope: str = SCOPE_CAMPAIGN, campaign_id: str | None = "1") -> DigestFinding:
    return DigestFinding(
        signal=signal,
        scope=scope,
        campaign_id=campaign_id,
        campaign_name="Кампания",
        lever="unknown",
        evidence={},
        money_at_stake=money,
        confidence="medium",
        confirmed_by_week=True,
        action=ACTION_TEMPLATES[(signal, "unknown")],
    )


def test_finding_without_money_is_dropped() -> None:
    selected = select_findings(
        [_finding(SIGNAL_SPEND_SPIKE, None), _finding(SIGNAL_CAMPAIGN_STOPPED, 100.0)],
        already_seen=set(),
    )
    assert [item.signal for item in selected] == [SIGNAL_CAMPAIGN_STOPPED]


def test_digest_keeps_at_most_five_sorted_by_money() -> None:
    findings = [
        _finding(SIGNAL_SPEND_SPIKE, money, campaign_id=str(money)) for money in (10.0, 90.0, 50.0, 70.0, 30.0, 20.0, 80.0)
    ]
    selected = select_findings(findings, already_seen=set())

    assert len(selected) == DIGEST_MAX_FINDINGS
    money = [item.money_at_stake for item in selected]
    assert money == sorted(money, reverse=True)
    assert money[0] == 90.0


def test_account_scope_wins_ties_against_a_campaign() -> None:
    account = _finding(SIGNAL_SPEND_SPIKE, 100.0, scope=SCOPE_ACCOUNT, campaign_id=None)
    campaign = _finding(SIGNAL_SPEND_SPIKE, 100.0, scope=SCOPE_CAMPAIGN, campaign_id="1")
    selected = select_findings([campaign, account], already_seen=set())
    assert selected[0].scope == SCOPE_ACCOUNT


# ---------------------------------------------------------------------------
# 7, 8. Repeat suppression
# ---------------------------------------------------------------------------


def test_repeat_is_marked_and_yields_its_place_to_a_new_finding() -> None:
    seen = {("1", SIGNAL_SPEND_SPIKE)}
    old = _finding(SIGNAL_SPEND_SPIKE, 1000.0, campaign_id="1")
    new = _finding(SIGNAL_CAMPAIGN_STOPPED, 10.0, campaign_id="2")

    selected = select_findings([old, new], already_seen=seen)

    # Despite being worth far more money, the repeat comes second.
    assert [item.signal for item in selected] == [SIGNAL_CAMPAIGN_STOPPED, SIGNAL_SPEND_SPIKE]
    assert selected[0].repeated is False
    assert selected[1].repeated is True


def test_repeats_are_still_shown_when_there_is_nothing_new() -> None:
    seen = {("1", SIGNAL_SPEND_SPIKE)}
    selected = select_findings([_finding(SIGNAL_SPEND_SPIKE, 1000.0, campaign_id="1")], already_seen=seen)

    assert len(selected) == 1
    assert selected[0].repeated is True


def test_repeat_is_detected_from_a_stored_digest(monkeypatch) -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)
        _fill_week(db)
        db.query(DirectCampaignDailyStat).filter_by(stat_date=DIGEST_DATE).update({"cost": 20000.0})
        db.commit()

        yesterdays = [
            {
                "signal": SIGNAL_SPEND_SPIKE,
                "campaign_id": None,
                "scope": SCOPE_ACCOUNT,
            }
        ]
        db.add(
            MorningDigest(
                client_id="client-1",
                digest_date=DIGEST_DATE - timedelta(days=1),
                findings_json=json.dumps(yesterdays),
                findings_count=1,
                status=STATUS_OK,
            )
        )
        db.commit()

        findings, _ = build_digest_findings(db, client, DIGEST_DATE)

        account_spike = [
            item for item in findings if item.signal == SIGNAL_SPEND_SPIKE and item.scope == SCOPE_ACCOUNT
        ]
        assert account_spike
        assert account_spike[0].repeated is True


# ---------------------------------------------------------------------------
# 9. A daily signal the week does not confirm loses confidence
# ---------------------------------------------------------------------------


def test_unconfirmed_daily_signal_has_lower_confidence() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)
        _fill_week(db, cost=6000.0, clicks=600, impressions=6000, conversions=60.0)
        # Yesterday's spend doubles: +100% against the same weekday last week,
        # but only +14% across the week, which the weekly test does not call
        # material. Exactly the one-day blip that must not be reported loudly.
        db.query(DirectCampaignDailyStat).filter_by(stat_date=DIGEST_DATE).update({"cost": 12000.0})
        db.commit()

        findings, _ = build_digest_findings(db, client, DIGEST_DATE)

        spikes = [item for item in findings if item.signal == SIGNAL_SPEND_SPIKE]
        assert spikes
        unconfirmed = [item for item in spikes if not item.confirmed_by_week]
        assert unconfirmed
        # Clicks are 600, which on its own would read "medium"; without weekly
        # confirmation the finding is reported one step lower.
        assert unconfirmed[0].confidence == "low"


# ---------------------------------------------------------------------------
# 10. A campaign that disappeared
# ---------------------------------------------------------------------------


def test_campaign_stopped_is_detected() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)
        _fill_week(db)
        # A second campaign that ran until yesterday and then went silent.
        for offset in range(1, 14):
            _row(db, DIGEST_DATE - timedelta(days=offset), campaign_id="2", campaign_name="РСЯ", cost=3000.0)

        findings, _ = build_digest_findings(db, client, DIGEST_DATE)

        stopped = [item for item in findings if item.signal == SIGNAL_CAMPAIGN_STOPPED]
        assert stopped
        assert stopped[0].campaign_id == "2"
        assert stopped[0].campaign_name == "РСЯ"
        assert stopped[0].money_at_stake is not None


# ---------------------------------------------------------------------------
# 11. Re-running the same day overwrites
# ---------------------------------------------------------------------------


def test_rerunning_the_same_day_overwrites_the_record() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        _client(db)
        _fill_week(db)

        first = run_client_digest(db, "client-1", DIGEST_DATE)
        first_id = first.id
        second = run_client_digest(db, "client-1", DIGEST_DATE)

        assert second.id == first_id
        assert db.query(MorningDigest).filter_by(client_id="client-1").count() == 1


# ---------------------------------------------------------------------------
# 14. Time budget
# ---------------------------------------------------------------------------


def test_time_budget_returns_a_partial_result_instead_of_raising() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        for index in range(4):
            _client(db, f"client-{index}")
            _fill_week(db, client_id=f"client-{index}")

        # A clock that jumps past the budget after the first client.
        ticks = iter([0.0, 100.0, 100.0, 100.0, 100.0])

        result = run_digests(db, digest_date=DIGEST_DATE, time_budget_seconds=45.0, monotonic=lambda: next(ticks))

        assert result["processed_count"] == 1
        assert result["remaining_count"] == 3
        assert result["complete"] is False


def test_full_run_reports_completion() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        for index in range(3):
            _client(db, f"client-{index}")
            _fill_week(db, client_id=f"client-{index}")

        result = run_digests(db, digest_date=DIGEST_DATE)

        assert result["processed_count"] == 3
        assert result["remaining_count"] == 0
        assert result["complete"] is True


# ---------------------------------------------------------------------------
# Fixed action templates
# ---------------------------------------------------------------------------


def test_every_action_comes_from_the_template_table() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)
        _fill_week(db, cost=6000.0, clicks=600, impressions=6000, conversions=60.0)
        db.query(DirectCampaignDailyStat).filter_by(stat_date=DIGEST_DATE).update(
            {"cost": 30000.0, "goal_conversions": 5.0}
        )
        db.commit()

        findings, _ = build_digest_findings(db, client, DIGEST_DATE)

        assert findings
        allowed = set(ACTION_TEMPLATES.values())
        for finding in findings:
            assert finding.action in allowed
            assert finding.action == ACTION_TEMPLATES[(finding.signal, finding.lever)]


def test_action_templates_cover_every_signal_and_lever_in_use() -> None:
    for (signal, lever), action in ACTION_TEMPLATES.items():
        assert signal and lever
        assert action.strip()
        # Every action must name a step, never ask for more data.
        assert "соберите" not in action.lower()
        assert "дополнительно" not in action.lower()


# ---------------------------------------------------------------------------
# 15. No network
# ---------------------------------------------------------------------------


def test_digest_module_does_not_import_yandex_connectors() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "services" / "morning_digest.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("yandex_direct", "YandexDirectConnector", "httpx", "requests"):
        assert forbidden not in source


def test_digest_runs_without_any_connector_patched() -> None:
    """No monkeypatching of the Yandex connector anywhere in this file.

    The whole suite runs offline; if the digest reached the network, these tests
    would hang or fail rather than pass.
    """
    SessionLocal = _session()
    with SessionLocal() as db:
        client = _client(db)
        _fill_week(db)
        findings, status = build_digest_findings(db, client, DIGEST_DATE)
        assert status == STATUS_OK
        assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# 12, 13. Endpoints
# ---------------------------------------------------------------------------


def _app_client(SessionLocal, *, current_user: CurrentUser | None = None):
    from app.main import app

    db = SessionLocal()

    def _override_db():
        yield db

    app.dependency_overrides[get_optional_db] = _override_db
    if current_user is not None:
        app.dependency_overrides[get_current_session_user] = lambda: current_user
    return TestClient(app), db


def _clear_overrides():
    from app.main import app

    app.dependency_overrides.clear()


def test_digest_run_without_secret_configured_returns_503(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routers.digests.settings", replace(base_settings, digest_cron_secret=None))
    SessionLocal = _session()
    client, db = _app_client(SessionLocal)
    try:
        response = client.post("/api/v1/digests/run", json={})
        assert response.status_code == 503
    finally:
        db.close()
        _clear_overrides()


def test_digest_run_without_authorization_returns_401(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routers.digests.settings", replace(base_settings, digest_cron_secret="secret"))
    SessionLocal = _session()
    client, db = _app_client(SessionLocal)
    try:
        assert client.post("/api/v1/digests/run", json={}).status_code == 401
        assert client.post(
            "/api/v1/digests/run", json={}, headers={"Authorization": "Bearer wrong"}
        ).status_code == 401
    finally:
        db.close()
        _clear_overrides()


def test_digest_run_with_the_right_secret_computes(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routers.digests.settings", replace(base_settings, digest_cron_secret="secret"))
    SessionLocal = _session()
    client, db = _app_client(SessionLocal)
    try:
        _client(db)
        _fill_week(db)
        response = client.post(
            "/api/v1/digests/run",
            json={"digest_date": DIGEST_DATE.isoformat()},
            headers={"Authorization": "Bearer secret"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["processed_count"] == 1
        assert body["complete"] is True
    finally:
        db.close()
        _clear_overrides()


def _org_user(db, org_id: str, email: str) -> CurrentUser:
    organization = Organization(id=org_id, name=org_id)
    user = User(id=f"user-{org_id}", organization_id=org_id, email=email)
    db.add_all([organization, user])
    db.commit()
    return CurrentUser(email=email, user=user, organization=organization)


def test_digest_of_another_organization_is_not_returned() -> None:
    SessionLocal = _session()
    db = SessionLocal()
    try:
        owner = _org_user(db, "org-owner", "owner@example.com")
        intruder = _org_user(db, "org-intruder", "intruder@example.com")
        _client(db, "client-owned", organization_id=owner.organization.id)
        db.add(
            MorningDigest(
                client_id="client-owned",
                digest_date=DIGEST_DATE,
                findings_json="[]",
                findings_count=0,
                status=STATUS_OK,
            )
        )
        db.commit()

        from app.main import app

        def _override_db():
            yield db

        app.dependency_overrides[get_optional_db] = _override_db

        app.dependency_overrides[get_current_session_user] = lambda: owner
        allowed = TestClient(app).get(
            f"/api/v1/clients/client-owned/digest?date={DIGEST_DATE.isoformat()}"
        )
        assert allowed.status_code == 200
        assert allowed.json()["client_id"] == "client-owned"

        app.dependency_overrides[get_current_session_user] = lambda: intruder
        denied = TestClient(app).get(
            f"/api/v1/clients/client-owned/digest?date={DIGEST_DATE.isoformat()}"
        )
        assert denied.status_code == 404
    finally:
        db.close()
        _clear_overrides()
