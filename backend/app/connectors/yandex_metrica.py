class YandexMetricaConnector:
    """Placeholder connector for the future Yandex Metrica API integration."""

    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)

    def list_goals(self, counter_id: int) -> list[dict[str, str | int]]:
        if not self.is_configured:
            return []
        return [
            {
                "counter_id": counter_id,
                "goal_id": 1,
                "name": "Mock lead goal",
            }
        ]
