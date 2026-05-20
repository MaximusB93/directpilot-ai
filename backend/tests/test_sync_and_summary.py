from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ClientAccount, DirectCampaignPeriodStat
from app.services.ai_recommendations import build_client_ai_context
from app.services.client_sync import run_client_sync
from app.services.performance_summary import build_performance_summary


def test_sync_without_token_creates_no_stats_and_zero_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        db.add(ClientAccount(id="client-1", name="Client 1", segment="Test"))
        db.commit()

        job = run_client_sync(db, "client-1", days=14)
        assert job.status == "failed"
        assert job.rows_loaded == 0
        assert "Yandex account is not bound to this client" in (job.error or "")
        count = db.query(DirectCampaignPeriodStat).filter(DirectCampaignPeriodStat.client_id == "client-1").count()
        assert count == 0


def test_performance_summary_without_stats_returns_empty() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        db.add(ClientAccount(id="client-2", name="Client 2", segment="Test"))
        db.commit()
        summary = build_performance_summary(db, "client-2")
        assert summary["totals"]["cost"] == 0.0
        assert summary["campaigns"] == []
        assert "Нет сохранённых данных Яндекс.Директа" in summary["message"]


def test_ai_context_without_stats_has_no_campaign_metrics() -> None:
    context = build_client_ai_context("unknown-client", client_context={"id": "c-empty", "name": "Empty"})
    assert context["campaigns"] == []
