from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models_workflow import RecommendationImpactRecord
from app.schemas import RecommendationImpactEvent

_EVENTS: list[RecommendationImpactEvent] = []


def create_impact_event(
    recommendation_id: str,
    client_id: str,
    expected_impact: str,
    observed_impact: str,
    window_days: int,
    created_by: str,
    db: Session | None = None,
) -> RecommendationImpactEvent:
    event = RecommendationImpactEvent(
        id=f"impact_{len(_EVENTS)+1:04d}",
        recommendation_id=recommendation_id,
        client_id=client_id,
        expected_impact=expected_impact,
        observed_impact=observed_impact,
        window_days=window_days,
        created_by=created_by,
        created_at=datetime.now(UTC).isoformat(),
    )
    _EVENTS.append(event)
    if db is not None:
        db.merge(
            RecommendationImpactRecord(
                id=event.id,
                recommendation_id=event.recommendation_id,
                client_id=event.client_id,
                expected_impact=event.expected_impact,
                observed_impact=event.observed_impact,
                window_days=event.window_days,
                created_by=event.created_by,
            )
        )
        db.commit()
    return event


def list_impact_events(client_id: str | None = None, db: Session | None = None) -> list[RecommendationImpactEvent]:
    if db is None:
        if not client_id:
            return _EVENTS
        return [item for item in _EVENTS if item.client_id == client_id]
    stmt = select(RecommendationImpactRecord).order_by(RecommendationImpactRecord.created_at.desc())
    if client_id:
        stmt = stmt.where(RecommendationImpactRecord.client_id == client_id)
    rows = db.scalars(stmt).all()
    return [RecommendationImpactEvent(id=r.id, recommendation_id=r.recommendation_id, client_id=r.client_id, expected_impact=r.expected_impact, observed_impact=r.observed_impact, window_days=r.window_days, created_by=r.created_by, created_at=r.created_at.isoformat()) for r in rows]
