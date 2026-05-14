from fastapi import APIRouter, Request

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/routes")
def list_routes(request: Request) -> dict[str, list[str]]:
    routes = []
    for route in request.app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            for method in sorted(methods):
                routes.append(f"{method} {path}")
    return {"routes": sorted(routes)}
