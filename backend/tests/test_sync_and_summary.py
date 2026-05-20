from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import ClientAccount
from app.services.client_sync import run_client_sync
from app.services.performance_summary import build_performance_summary


def test_demo_sync_and_summary_totals() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        db.add(ClientAccount(id="client-1", name="Client 1", segment="Test"))
        db.commit()

        job = run_client_sync(db, "client-1", days=14)
        assert job.status == "success"
        assert job.rows_loaded > 0

        summary = build_performance_summary(db, "client-1")
        assert summary["totals"]["cost"] > 0
        assert summary["totals"]["impressions"] > 0
        assert len(summary["campaigns"]) > 0
