from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.knowledge.yandex_direct_api import DIRECT_API_KNOWLEDGE_VERSION
from app.services.yandex_direct_read_capabilities import (
    YANDEX_DIRECT_READ_CAPABILITIES,
    get_direct_read_capabilities,
)

_KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge" / "yandex_direct_api"


@lru_cache(maxsize=8)
def _load(name: str) -> dict[str, Any]:
    path = _KNOWLEDGE_DIR / name
    if not path.is_file():
        return {"schema_version": DIRECT_API_KNOWLEDGE_VERSION}
    return json.loads(path.read_text(encoding="utf-8"))


def list_direct_capabilities(
    *, campaign_family: str | None = None, campaign_subtype: str | None = None,
    investigation_goal: str | None = None,
) -> dict[str, Any]:
    del investigation_goal
    applicable = get_direct_read_capabilities(
        campaign_family=campaign_family, campaign_subtype=campaign_subtype,
    )
    allowed = [item.id for item in applicable if item.live_supported and item.read_only]
    forbidden = [
        item.id for item in YANDEX_DIRECT_READ_CAPABILITIES.values()
        if item.id not in allowed and (
            campaign_family in item.supported_families if campaign_family else True
        )
    ]
    return {
        "knowledge_version": DIRECT_API_KNOWLEDGE_VERSION,
        "available_capabilities": allowed,
        "forbidden_capabilities": sorted(forbidden),
        "capabilities": [
            {
                "id": item.id,
                "metrics": list(item.allowed_metrics),
                "source_type": item.source_type,
                "limitations": [item.source_required] if item.source_required else [],
                "supported_now": item.live_supported,
            }
            for item in applicable
        ],
    }


def describe_direct_capability(capability_id: str) -> dict[str, Any]:
    capability = YANDEX_DIRECT_READ_CAPABILITIES.get(capability_id)
    docs = next(
        (item for item in _load("capabilities.json").get("capabilities", []) if item.get("capability_id") == capability_id),
        None,
    )
    if capability is None:
        return {
            "capability_id": capability_id,
            "supported_now": False,
            "requires_backend_implementation": True,
            "documentation": docs,
        }
    return {
        "capability_id": capability.id,
        "title": capability.title,
        "purpose": (docs or {}).get("purpose"),
        "campaign_families": sorted(capability.supported_families),
        "campaign_subtypes": sorted(capability.supported_subtypes),
        "semantic_metrics": list(capability.allowed_metrics),
        "source_type": capability.source_type,
        "read_only": capability.read_only,
        "supported_now": capability.live_supported,
        "prerequisites": [capability.source_required] if capability.source_required else [],
        "limitations": [] if capability.live_supported else ["requires_backend_implementation"],
        "knowledge_version": DIRECT_API_KNOWLEDGE_VERSION,
    }


def search_direct_api_docs(question: str) -> dict[str, Any]:
    terms = {term for term in question.lower().replace("_", " ").split() if len(term) > 2}
    matches = []
    for item in _load("capabilities.json").get("capabilities", []):
        haystack = " ".join(str(value) for value in item.values()).lower()
        if terms and not any(term in haystack for term in terms):
            continue
        capability_id = str(item.get("capability_id") or "")
        executable = capability_id in YANDEX_DIRECT_READ_CAPABILITIES and YANDEX_DIRECT_READ_CAPABILITIES[capability_id].live_supported
        matches.append({
            "capability_id": capability_id,
            "purpose": item.get("purpose"),
            "supported_now": executable,
            "capability_candidate": not executable,
            "requires_backend_implementation": not executable,
        })
    return {
        "knowledge_version": DIRECT_API_KNOWLEDGE_VERSION,
        "matches": matches[:10],
        "executable": False,
    }
