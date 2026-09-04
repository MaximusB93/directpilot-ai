from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.connectors.yandex_direct import YandexDirectConnector
from app.db import (
    DAILY_STATS_DEDUPLICATE_SQL,
    DAILY_STATS_UNIQUE_INDEX_SQL,
    Base,
)
from app.models import ClientAccount, DirectCampaignDailyStat
from app.services.client_sync import (
    DAILY_RESTATEMENT_WINDOW_DAYS,
    HISTORY_CHUNK_DAYS,
    INITIAL_HISTORY_DAYS,
    _store_daily_campaign_rows,
    run_client_sync,
    sync_campaign_daily_stats,
)

YESTERDAY = datetime.now(UTC).date() - timedelta(days=1)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _client(db, client_id: str = "client-history", *, bound: bool = True) -> None:
    db.add(
        ClientAccount(
            id=client_id,
            name="History Client",
            segment="Test",
            yandex_account_id="account-1" if bound else None,
            conversion_goal_ids="1",
        )
    )
    db.commit()


def _daily_row(stat_date: date, *, campaign_id: str = "1", conversions: str = "3", clicks: str = "100"):
    return {
        "Date": stat_date.isoformat(),
        "CampaignId": campaign_id,
        "CampaignName": f"Campaign {campaign_id}",
        "Impressions": "1000",
        "Clicks": clicks,
        "Cost": "5000",
        "Ctr": "10",
        "AvgCpc": "50",
        "Conversions": conversions,
        "_TotalConversions": conversions,
    }


def _store(db, client_id: str, stat_date: date, *, campaign_id: str = "1", conversions: float | None = 3.0) -> None:
    """Put one row straight into the database, bypassing the sync."""
    db.add(
        DirectCampaignDailyStat(
            client_id=client_id,
            stat_date=stat_date,
            campaign_id=campaign_id,
            campaign_name=f"Campaign {campaign_id}",
            impressions=1000,
            clicks=100,
            cost=5000,
            ctr=10,
            avg_cpc=50,
            goal_conversions=conversions,
        )
    )
    db.commit()


class _RecordingConnector:
    """Records every range Direct was asked for and answers with fixed rows."""

    def __init__(self, rows_for_range=None, fail_on_call: int | None = None):
        self.requested: list[tuple[date, date]] = []
        self._rows_for_range = rows_for_range or (lambda date_from, date_to: [])
        self._fail_on_call = fail_on_call

    def install(self, monkeypatch):
        connector = self

        def fake_report(self, *, date_from, date_to, goal_ids=None, **kwargs):
            connector.requested.append((date_from, date_to))
            if connector._fail_on_call is not None and len(connector.requested) == connector._fail_on_call:
                raise RuntimeError("Direct report failed")
            return connector._rows_for_range(date_from, date_to)

        monkeypatch.setattr("app.services.client_sync.get_yandex_access_token_for_account", lambda db, account_id: "token")
        monkeypatch.setattr(YandexDirectConnector, "get_campaign_daily_range_report", fake_report)
        return connector


# ---------------------------------------------------------------------------
# 1. A connection problem must not destroy history
# ---------------------------------------------------------------------------


def test_sync_without_bound_account_keeps_daily_history() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        _client(db, "client-unbound", bound=False)
        _store(db, "client-unbound", YESTERDAY)

        job = run_client_sync(db, "client-unbound", days=14)

        assert job.status == "failed"
        assert db.query(DirectCampaignDailyStat).filter_by(client_id="client-unbound").count() == 1


def test_sync_without_token_keeps_daily_history(monkeypatch) -> None:
    SessionLocal = _session()
    monkeypatch.setattr("app.services.client_sync.get_yandex_access_token_for_account", lambda db, account_id: None)
    with SessionLocal() as db:
        _client(db, "client-no-token")
        _store(db, "client-no-token", YESTERDAY)

        job = run_client_sync(db, "client-no-token", days=14)

        assert job.status == "failed"
        assert "Yandex OAuth token is not connected" in (job.error or "")
        assert db.query(DirectCampaignDailyStat).filter_by(client_id="client-no-token").count() == 1


# ---------------------------------------------------------------------------
# 2, 3, 7. Upsert updates in place and leaves untouched rows alone
# ---------------------------------------------------------------------------


def test_upsert_updates_existing_row_instead_of_duplicating() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        _client(db)
        day = YESTERDAY

        _store_daily_campaign_rows(
            db, client_id="client-history", rows=[_daily_row(day, conversions="3")], goal_ids=["1"], goal_ids_text="1"
        )
        db.commit()
        _store_daily_campaign_rows(
            db, client_id="client-history", rows=[_daily_row(day, conversions="7")], goal_ids=["1"], goal_ids_text="1"
        )
        db.commit()

        stats = db.query(DirectCampaignDailyStat).filter_by(client_id="client-history").all()
        assert len(stats) == 1
        assert stats[0].goal_conversions == 7


def test_upsert_refreshes_loaded_at() -> None:
    """loaded_at says when Direct last confirmed the row, so it moves on update."""
    SessionLocal = _session()
    with SessionLocal() as db:
        _client(db)
        day = YESTERDAY
        _store(db, "client-history", day)
        stale = datetime(2020, 1, 1, tzinfo=UTC)
        db.query(DirectCampaignDailyStat).filter_by(client_id="client-history").update({"loaded_at": stale})
        db.commit()

        _store_daily_campaign_rows(
            db, client_id="client-history", rows=[_daily_row(day, conversions="7")], goal_ids=["1"], goal_ids_text="1"
        )
        db.commit()

        row = db.query(DirectCampaignDailyStat).filter_by(client_id="client-history").one()
        assert row.loaded_at.replace(tzinfo=UTC) > stale


def test_row_missing_from_the_new_report_is_not_deleted() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        _client(db)
        day = YESTERDAY
        _store(db, "client-history", day, campaign_id="1")
        _store(db, "client-history", day, campaign_id="2")

        # The new report mentions campaign 1 only.
        _store_daily_campaign_rows(
            db,
            client_id="client-history",
            rows=[_daily_row(day, campaign_id="1", conversions="9")],
            goal_ids=["1"],
            goal_ids_text="1",
        )
        db.commit()

        stats = {item.campaign_id: item for item in db.query(DirectCampaignDailyStat).filter_by(client_id="client-history")}
        assert set(stats) == {"1", "2"}
        assert stats["1"].goal_conversions == 9
        assert stats["2"].goal_conversions == 3


def test_restatement_window_updates_conversions(monkeypatch) -> None:
    SessionLocal = _session()
    day = YESTERDAY - timedelta(days=2)
    connector = _RecordingConnector(
        rows_for_range=lambda date_from, date_to: [_daily_row(day, conversions="7")]
    ).install(monkeypatch)

    with SessionLocal() as db:
        _client(db)
        # A full history, so the sync runs in incremental mode.
        for offset in range(INITIAL_HISTORY_DAYS):
            _store(db, "client-history", YESTERDAY - timedelta(days=offset), conversions=3.0)

        sync_campaign_daily_stats(db, "client-history")

        row = db.query(DirectCampaignDailyStat).filter_by(client_id="client-history", stat_date=day).one()
        assert row.goal_conversions == 7
        assert connector.requested


# ---------------------------------------------------------------------------
# 4. First sync backfills in chunks, and an abort keeps what was stored
# ---------------------------------------------------------------------------


def test_initial_load_requests_history_in_chunks(monkeypatch) -> None:
    SessionLocal = _session()
    connector = _RecordingConnector(
        rows_for_range=lambda date_from, date_to: [_daily_row(date_from)]
    ).install(monkeypatch)

    with SessionLocal() as db:
        _client(db)
        result = sync_campaign_daily_stats(db, "client-history")

        assert result["mode"] == "initial"
        # Newest chunk first, none longer than the chunk size, no gaps, and the
        # whole initial window is covered.
        assert connector.requested[0][1] == YESTERDAY
        assert all((to - frm).days + 1 <= HISTORY_CHUNK_DAYS for frm, to in connector.requested)
        assert len(connector.requested) > 1
        for newer, older in zip(connector.requested, connector.requested[1:]):
            assert older[1] == newer[0] - timedelta(days=1)
        assert connector.requested[-1][0] == YESTERDAY - timedelta(days=INITIAL_HISTORY_DAYS - 1)


def test_initial_load_keeps_chunks_stored_before_a_failure(monkeypatch) -> None:
    SessionLocal = _session()
    _RecordingConnector(
        rows_for_range=lambda date_from, date_to: [_daily_row(date_to)],
        fail_on_call=2,
    ).install(monkeypatch)

    with SessionLocal() as db:
        _client(db)
        with pytest.raises(RuntimeError):
            sync_campaign_daily_stats(db, "client-history")

        # The first chunk was committed on its own and survived the abort.
        assert db.query(DirectCampaignDailyStat).filter_by(client_id="client-history").count() == 1


# ---------------------------------------------------------------------------
# 5, 6. Incremental syncs read the restatement window and any missing days
# ---------------------------------------------------------------------------


def test_incremental_sync_reads_only_the_restatement_window(monkeypatch) -> None:
    SessionLocal = _session()
    connector = _RecordingConnector(rows_for_range=lambda date_from, date_to: []).install(monkeypatch)

    with SessionLocal() as db:
        _client(db)
        for offset in range(INITIAL_HISTORY_DAYS):
            _store(db, "client-history", YESTERDAY - timedelta(days=offset))

        result = sync_campaign_daily_stats(db, "client-history")

        assert result["mode"] == "incremental"
        assert connector.requested == [
            (YESTERDAY - timedelta(days=DAILY_RESTATEMENT_WINDOW_DAYS - 1), YESTERDAY)
        ]


def test_missing_days_after_a_long_gap_are_backfilled(monkeypatch) -> None:
    SessionLocal = _session()
    connector = _RecordingConnector(rows_for_range=lambda date_from, date_to: []).install(monkeypatch)
    gap_days = 40

    with SessionLocal() as db:
        _client(db)
        # History that stops 40 days ago.
        for offset in range(gap_days, gap_days + 30):
            _store(db, "client-history", YESTERDAY - timedelta(days=offset))

        sync_campaign_daily_stats(db, "client-history")

        requested_days = set()
        for range_from, range_to in connector.requested:
            requested_days |= {
                range_from + timedelta(days=offset) for offset in range((range_to - range_from).days + 1)
            }

        # Every day from the last stored one up to yesterday is asked for.
        expected = {YESTERDAY - timedelta(days=offset) for offset in range(gap_days)}
        assert expected <= requested_days
        # Days that are already stored and final are not asked for again.
        assert YESTERDAY - timedelta(days=gap_days + 10) not in requested_days


def test_old_interior_hole_is_left_alone(monkeypatch) -> None:
    """Pins the scope of the catch-up, which is deliberately bounded.

    Specification section 5 asks for the restatement window plus the days
    between MAX(stat_date) and yesterday. A hole older than both is not
    re-requested, so every sync stays cheap and days already stored are treated
    as final. The cost is that such a hole is never repaired on its own.
    """
    SessionLocal = _session()
    connector = _RecordingConnector(rows_for_range=lambda date_from, date_to: []).install(monkeypatch)
    hole = YESTERDAY - timedelta(days=DAILY_RESTATEMENT_WINDOW_DAYS + 5)

    with SessionLocal() as db:
        _client(db)
        for offset in range(INITIAL_HISTORY_DAYS):
            day = YESTERDAY - timedelta(days=offset)
            if day != hole:
                _store(db, "client-history", day)

        sync_campaign_daily_stats(db, "client-history")

        requested_days = set()
        for range_from, range_to in connector.requested:
            requested_days |= {
                range_from + timedelta(days=offset) for offset in range((range_to - range_from).days + 1)
            }
        assert hole not in requested_days
        assert requested_days == {
            YESTERDAY - timedelta(days=offset) for offset in range(DAILY_RESTATEMENT_WINDOW_DAYS)
        }


# ---------------------------------------------------------------------------
# 8. The unique constraint
# ---------------------------------------------------------------------------


def test_duplicate_daily_row_is_rejected_by_the_unique_constraint() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        _client(db)
        day = YESTERDAY
        _store(db, "client-history", day)

        db.add(
            DirectCampaignDailyStat(
                client_id="client-history",
                stat_date=day,
                campaign_id="1",
                campaign_name="Campaign 1",
                impressions=1,
                clicks=1,
                cost=1,
                ctr=1,
                avg_cpc=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        assert db.query(DirectCampaignDailyStat).filter_by(client_id="client-history").count() == 1


def test_one_report_carrying_a_day_twice_stores_one_row() -> None:
    SessionLocal = _session()
    with SessionLocal() as db:
        _client(db)
        day = YESTERDAY
        _store_daily_campaign_rows(
            db,
            client_id="client-history",
            rows=[_daily_row(day, conversions="3"), _daily_row(day, conversions="8")],
            goal_ids=["1"],
            goal_ids_text="1",
        )
        db.commit()

        stats = db.query(DirectCampaignDailyStat).filter_by(client_id="client-history").all()
        assert len(stats) == 1
        assert stats[0].goal_conversions == 8


# ---------------------------------------------------------------------------
# 9. Duplicate clean-up before the unique index is created
# ---------------------------------------------------------------------------


_LEGACY_TABLE_SQL = """
CREATE TABLE direct_campaign_daily_stats (
    id VARCHAR(36) PRIMARY KEY,
    client_id VARCHAR(64) NOT NULL,
    stat_date DATE NOT NULL,
    campaign_id VARCHAR(64) NOT NULL,
    campaign_name VARCHAR(255) NOT NULL,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    cost FLOAT NOT NULL DEFAULT 0,
    ctr FLOAT NOT NULL DEFAULT 0,
    avg_cpc FLOAT NOT NULL DEFAULT 0,
    goal_ids TEXT,
    goal_conversions FLOAT,
    goal_cpa FLOAT,
    conversion_rate FLOAT,
    issue_flags TEXT,
    loaded_at TIMESTAMP NOT NULL
)
"""


def test_deduplicate_keeps_the_newest_row_and_lets_the_index_be_created() -> None:
    """Mirrors an existing database that predates the unique constraint."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(_LEGACY_TABLE_SQL))
        for row_id, conversions, loaded_at in (
            ("a", 1.0, "2026-01-01 10:00:00"),
            ("b", 5.0, "2026-01-03 10:00:00"),
            ("c", 3.0, "2026-01-02 10:00:00"),
        ):
            connection.execute(
                text(
                    "INSERT INTO direct_campaign_daily_stats"
                    " (id, client_id, stat_date, campaign_id, campaign_name, goal_conversions, loaded_at)"
                    " VALUES (:id, 'c1', '2026-01-01', 'camp-1', 'Campaign', :conversions, :loaded_at)"
                ),
                {"id": row_id, "conversions": conversions, "loaded_at": loaded_at},
            )
        # A different key must survive untouched.
        connection.execute(
            text(
                "INSERT INTO direct_campaign_daily_stats"
                " (id, client_id, stat_date, campaign_id, campaign_name, goal_conversions, loaded_at)"
                " VALUES ('d', 'c1', '2026-01-02', 'camp-1', 'Campaign', 2.0, '2026-01-02 10:00:00')"
            )
        )

    with engine.begin() as connection:
        connection.execute(text(DAILY_STATS_DEDUPLICATE_SQL))
        # The index can only be created once the duplicates are gone.
        connection.execute(text(DAILY_STATS_UNIQUE_INDEX_SQL))

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id, goal_conversions FROM direct_campaign_daily_stats ORDER BY id")
        ).all()

    assert [item[0] for item in rows] == ["b", "d"]
    assert rows[0][1] == 5.0


# ---------------------------------------------------------------------------
# 10. The days parameter is honoured
# ---------------------------------------------------------------------------


def test_days_parameter_sets_the_refreshed_window(monkeypatch) -> None:
    SessionLocal = _session()
    connector = _RecordingConnector(rows_for_range=lambda date_from, date_to: []).install(monkeypatch)

    with SessionLocal() as db:
        _client(db)
        for offset in range(INITIAL_HISTORY_DAYS):
            _store(db, "client-history", YESTERDAY - timedelta(days=offset))

        sync_campaign_daily_stats(db, "client-history", days=60)

        requested_days = set()
        for range_from, range_to in connector.requested:
            requested_days |= {
                range_from + timedelta(days=offset) for offset in range((range_to - range_from).days + 1)
            }
        assert len(requested_days) == 60
        assert min(requested_days) == YESTERDAY - timedelta(days=59)
        assert max(requested_days) == YESTERDAY


def test_days_parameter_beyond_the_chunk_size_is_split(monkeypatch) -> None:
    SessionLocal = _session()
    connector = _RecordingConnector(rows_for_range=lambda date_from, date_to: []).install(monkeypatch)

    with SessionLocal() as db:
        _client(db)
        for offset in range(INITIAL_HISTORY_DAYS):
            _store(db, "client-history", YESTERDAY - timedelta(days=offset))

        sync_campaign_daily_stats(db, "client-history", days=HISTORY_CHUNK_DAYS + 30)

        assert len(connector.requested) == 2
        assert all((to - frm).days + 1 <= HISTORY_CHUNK_DAYS for frm, to in connector.requested)
