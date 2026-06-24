from datetime import date
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models_wordstat import WordstatDynamicsPoint, WordstatQueryBatch
from app.services.wordstat_dynamics import WordstatDynamicsService, normalize_phrase


class FakeWordstatConnector:
    is_configured = True

    def __init__(self) -> None:
        self.calls = 0

    def get_dynamics(self, **kwargs: Any) -> list[dict[str, str]]:
        self.calls += 1
        return [
            {"date": "2025-01-01T00:00:00Z", "count": "100", "share": "0.001"},
            {"date": "2025-02-01T00:00:00Z", "count": "150", "share": "0.0015"},
            {"date": "2026-01-01T00:00:00Z", "count": "200", "share": "0.002"},
            {"date": "2026-02-01T00:00:00Z", "count": "300", "share": "0.003"},
        ]


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_wordstat_batch_loads_and_enriches_dynamics() -> None:
    SessionLocal = _session()
    connector = FakeWordstatConnector()
    with SessionLocal() as db:
        result = WordstatDynamicsService(db, connector).get_batch_dynamics(
            phrases=["Купить диван", "купить  диван", "Угловой диван"],
            period="MONTHLY",
            from_date=date(2025, 1, 1),
            to_date=date(2026, 2, 28),
            regions=["225"],
            devices=["DEVICE_ALL"],
            organization_id="org-1",
            client_id="client-1",
        )

        assert result["status"] == "completed"
        assert result["meta"]["totalPhrases"] == 2
        assert connector.calls == 2
        assert db.query(WordstatQueryBatch).count() == 1
        assert db.query(WordstatDynamicsPoint).count() == 8

        first_series = result["series"][0]
        assert first_series["phraseNormalized"] == normalize_phrase("Купить диван")
        assert first_series["points"][0]["index"] == 100
        assert first_series["points"][1]["mom"] == 50
        assert first_series["points"][2]["yoy"] == 100
        assert result["summary"]["maxCountPhrase"] == "Купить диван"


def test_wordstat_batch_uses_cache_without_second_api_call() -> None:
    SessionLocal = _session()
    connector = FakeWordstatConnector()
    with SessionLocal() as db:
        service = WordstatDynamicsService(db, connector)
        service.get_batch_dynamics(
            phrases=["купить диван"],
            period="MONTHLY",
            from_date=date(2025, 1, 1),
            to_date=date(2026, 2, 28),
            regions=[],
            devices=["DEVICE_ALL"],
        )
        second = service.get_batch_dynamics(
            phrases=["купить диван"],
            period="MONTHLY",
            from_date=date(2025, 1, 1),
            to_date=date(2026, 2, 28),
            regions=[],
            devices=["DEVICE_ALL"],
        )

        assert connector.calls == 1
        assert second["series"][0]["source"] == "cache"
