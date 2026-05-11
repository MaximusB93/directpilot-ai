from typing import Any

from app.services.mock_data import AUDIT_ISSUES, CAMPAIGNS, CLIENTS, INTEGRATIONS, RECOMMENDATIONS

JsonObject = dict[str, Any]


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_dump(item) for item in value]
    return value


def _find_client(client_id: str) -> Any:
    for client in CLIENTS:
        if client.id == client_id:
            return client
    raise ValueError(f"Client '{client_id}' was not found")


def _find_recommendation(recommendation_id: str) -> Any:
    for recommendation in RECOMMENDATIONS:
        if recommendation.id == recommendation_id:
            return recommendation
    raise ValueError(f"Recommendation '{recommendation_id}' was not found")


TOOLS: list[JsonObject] = [
    {
        "name": "list_clients",
        "description": "List agency clients available in DirectPilot AI.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_client",
        "description": "Get one client profile by client_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"client_id": {"type": "string", "description": "Client identifier, e.g. furniture"}},
            "required": ["client_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_campaigns",
        "description": "List campaigns for a client. The current version returns mock campaigns.",
        "inputSchema": {
            "type": "object",
            "properties": {"client_id": {"type": "string", "description": "Client identifier"}},
            "required": ["client_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_audit_issues",
        "description": "List AI audit issues detected for a client.",
        "inputSchema": {
            "type": "object",
            "properties": {"client_id": {"type": "string", "description": "Client identifier"}},
            "required": ["client_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_recommendations",
        "description": "List DirectPilot AI optimization recommendations.",
        "inputSchema": {
            "type": "object",
            "properties": {"client_id": {"type": "string", "description": "Client identifier"}},
            "required": ["client_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_recommendation",
        "description": "Get a detailed recommendation with evidence, affected objects and preview diff.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "recommendation_id": {
                    "type": "string",
                    "description": "Recommendation identifier, e.g. pause-wasted-keywords",
                }
            },
            "required": ["recommendation_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_integrations",
        "description": "List planned and connected integrations such as Yandex Direct, Metrica and CRM.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def call_tool(name: str, arguments: JsonObject | None = None) -> Any:
    args = arguments or {}

    if name == "list_clients":
        return _dump(CLIENTS)
    if name == "get_client":
        return _dump(_find_client(args["client_id"]))
    if name == "list_campaigns":
        _find_client(args["client_id"])
        return _dump(CAMPAIGNS)
    if name == "list_audit_issues":
        _find_client(args["client_id"])
        return _dump(AUDIT_ISSUES)
    if name == "list_recommendations":
        _find_client(args["client_id"])
        return _dump(RECOMMENDATIONS)
    if name == "get_recommendation":
        return _dump(_find_recommendation(args["recommendation_id"]))
    if name == "list_integrations":
        return _dump(INTEGRATIONS)

    raise ValueError(f"Unknown MCP tool '{name}'")
