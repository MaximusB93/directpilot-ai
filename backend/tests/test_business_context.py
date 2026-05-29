from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ClientAccount, ClientBusinessContext
from app.services.ai_recommendations import build_client_ai_context_from_db
from app.services.performance_summary import build_performance_summary


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_business_context_status_and_ai_context() -> None:
    SessionLocal = _session_factory()

    with SessionLocal() as db:
        client = ClientAccount(
            id="client-business",
            organization_id="org-1",
            name="Hotel Green Flow",
            segment="Клиент",
            direct_login="hotel-login",
            metrica_counter="123",
        )
        db.add(client)
        db.add(
            ClientBusinessContext(
                client_id=client.id,
                brand_name="Hotel Green Flow",
                business_niche="Отель",
                main_offers="Бронирование номеров и SPA",
                negative_topics="работа, вакансии, бесплатно",
                memory_notes="Не минусовать брендовые запросы.",
            )
        )
        db.commit()

        summary = build_performance_summary(db, client.id)
        context = build_client_ai_context_from_db(db, client.id)

    assert summary["businessContextStatus"]["status"] == "partial"
    assert summary["businessContextStatus"]["hasBrand"] is True
    assert context["business_context"]["fields"]["brand_name"] == "Hotel Green Flow"
    assert "negative_topics" in context["business_context"]["fields"]


def test_empty_business_context_is_limitation_not_failure() -> None:
    SessionLocal = _session_factory()

    with SessionLocal() as db:
        client = ClientAccount(
            id="client-empty-context",
            organization_id="org-1",
            name="Empty Context",
            segment="Клиент",
        )
        db.add(client)
        db.commit()

        summary = build_performance_summary(db, client.id)

    assert summary["businessContextStatus"]["status"] == "empty"
    assert "Контекст бизнеса не заполнен" in summary["businessContextStatus"]["message"]
    limitations = summary["yandexDirectAudit"]["limitations"]
    assert any(item["id"] == "YD00" for item in limitations)
