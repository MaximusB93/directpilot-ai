from __future__ import annotations

import hashlib
from typing import Any


def campaign_scope_key(value: Any) -> str | None:
    """Return an opaque backend-only campaign identity without exposing Direct IDs."""

    text = str(value or "").strip()
    if not text:
        return None
    return "campaign:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def ensure_trusted_campaign_scopes(snapshot: dict[str, Any]) -> dict[str, str]:
    scopes = snapshot.setdefault("_trustedCampaignScopes", {})
    if not isinstance(scopes, dict):
        scopes = {}
        snapshot["_trustedCampaignScopes"] = scopes
    ambiguous = {str(item) for item in (snapshot.get("_ambiguousCampaignNames") or [])}
    for item in snapshot.get("campaignClassifications") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("campaign_name") or item.get("campaignName") or "").strip()
        scope = str(item.get("campaign_scope_key") or item.get("campaignScopeKey") or "").strip()
        if name and scope and name not in ambiguous:
            scopes[name] = scope
    for name in ambiguous:
        scopes.pop(name, None)
    return {str(key): str(value) for key, value in scopes.items() if key and value}


def campaign_scope_for_name(snapshot: dict[str, Any], campaign_name: Any) -> str | None:
    name = str(campaign_name or "").strip()
    if name == "__all_campaigns__":
        return "account"
    return ensure_trusted_campaign_scopes(snapshot).get(name)


def trusted_scope_names(snapshot: dict[str, Any]) -> dict[str, str]:
    values = snapshot.get("_trustedCampaignScopeNames") or {}
    return {
        str(scope): str(name)
        for scope, name in values.items()
        if scope and name
    } if isinstance(values, dict) else {}
