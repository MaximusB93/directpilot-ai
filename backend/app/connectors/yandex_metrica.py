import httpx


class YandexMetricaConnector:
    """Lightweight read-only connector for Yandex Metrica goals."""

    goals_url = "https://api-metrica.yandex.net/management/v1/counter/{counter_id}/goals"

    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)

    def list_goals(self, counter_id: int) -> list[dict[str, str | int]]:
        if not self.is_configured:
            return []
        headers = {"Authorization": f"OAuth {self.access_token}"}
        response = httpx.get(self.goals_url.format(counter_id=counter_id), headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        goals = payload.get("goals", []) if isinstance(payload, dict) else []
        return [
            {
                "counter_id": counter_id,
                "goal_id": goal.get("id"),
                "name": goal.get("name") or "",
            }
            for goal in goals
        ]
