from datetime import UTC, datetime

from app.schemas import RecommendationImpactEvent

_EVENTS: list[RecommendationImpactEvent] = []


def create_impact_event(
    recommendation_id: str,
    client_id: str,
    expected_impact: str,
    observed_impact: str,
    window_days: int,
    created_by: str,
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
    return event


def list_impact_events(client_id: str | None = None) -> list[RecommendationImpactEvent]:
    if not client_id:
        return _EVENTS
    return [item for item in _EVENTS if item.client_id == client_id]
