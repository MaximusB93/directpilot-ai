from fastapi import APIRouter, Request

router = APIRouter(prefix="/debug", tags=["debug"])


def _join_paths(prefix: str, path: str) -> str:
    return f"/{prefix.strip('/')}/{path.strip('/')}".replace("//", "/")


def _route_strings(route: object, prefix: str = "") -> list[str]:
    path = getattr(route, "path", None)
    methods = getattr(route, "methods", None)
    if path and methods:
        full_path = _join_paths(prefix, path)
        return [f"{method} {full_path}" for method in sorted(methods)]

    original_router = getattr(route, "original_router", None)
    include_context = getattr(route, "include_context", None)
    nested_prefix = getattr(include_context, "prefix", "") if include_context else ""
    if original_router and hasattr(original_router, "routes"):
        combined_prefix = _join_paths(prefix, nested_prefix) if nested_prefix else prefix
        nested_routes: list[str] = []
        for nested_route in original_router.routes:
            nested_routes.extend(_route_strings(nested_route, combined_prefix))
        return nested_routes

    return []


@router.get("/routes")
def list_routes(request: Request) -> dict[str, list[str]]:
    routes = []
    for route in request.app.routes:
        routes.extend(_route_strings(route))
    return {"routes": sorted(routes)}
