from dataclasses import dataclass


@dataclass(frozen=True)
class YandexDirectAccount:
    login: str
    agency_client_id: str | None = None


class YandexDirectConnector:
    """Placeholder connector for the future Yandex Direct API integration."""

    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)

    def list_campaigns(self, account: YandexDirectAccount) -> list[dict[str, str]]:
        if not self.is_configured:
            return []
        return [
            {
                "account": account.login,
                "name": "Mock campaign from Yandex Direct connector",
                "status": "DRAFT",
            }
        ]
