from typing import Any

from mcp.server.fastmcp import FastMCP

from app.mcp.tools import call_tool

mcp = FastMCP("directpilot-yandex-direct")


@mcp.tool()
def list_clients() -> list[dict[str, Any]]:
    """List agency clients available in DirectPilot AI."""
    return call_tool("list_clients")


@mcp.tool()
def get_client(client_id: str) -> dict[str, Any]:
    """Get one client profile by client_id."""
    return call_tool("get_client", {"client_id": client_id})


@mcp.tool()
def list_campaigns(client_id: str) -> list[dict[str, Any]]:
    """List campaigns for a client. The current version returns mock campaigns."""
    return call_tool("list_campaigns", {"client_id": client_id})


@mcp.tool()
def list_audit_issues(client_id: str) -> list[dict[str, Any]]:
    """List AI audit issues detected for a client."""
    return call_tool("list_audit_issues", {"client_id": client_id})


@mcp.tool()
def list_recommendations(client_id: str) -> list[dict[str, Any]]:
    """List DirectPilot AI optimization recommendations."""
    return call_tool("list_recommendations", {"client_id": client_id})


@mcp.tool()
def get_recommendation(recommendation_id: str) -> dict[str, Any]:
    """Get a detailed recommendation with evidence, affected objects and preview diff."""
    return call_tool("get_recommendation", {"recommendation_id": recommendation_id})


@mcp.tool()
def list_integrations() -> list[dict[str, Any]]:
    """List planned and connected integrations such as Yandex Direct, Metrica and CRM."""
    return call_tool("list_integrations")


@mcp.tool()
def preview_recommendation(recommendation_id: str, client_id: str = "furniture") -> dict[str, Any]:
    """Create a dry-run preview for a recommendation without applying changes."""
    return call_tool("preview_recommendation", {"recommendation_id": recommendation_id, "client_id": client_id})


@mcp.tool()
def list_audit_log() -> list[dict[str, Any]]:
    """List backend audit log events created by previews and approval actions."""
    return call_tool("list_audit_log")


if __name__ == "__main__":
    mcp.run()
