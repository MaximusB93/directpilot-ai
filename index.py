from pathlib import Path
import sys

from fastapi import FastAPI

BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _diagnostic_app(error: Exception) -> FastAPI:
    diagnostic = FastAPI(title="DirectPilot AI API startup diagnostic")
    message = f"{type(error).__name__}: {error}"

    @diagnostic.get("/")
    @diagnostic.get("/health")
    def startup_error() -> dict[str, object]:
        return {
            "status": "startup_error",
            "service": "directpilot-ai-backend",
            "message": "Backend entrypoint loaded, but app.main could not be imported.",
            "error": message,
        }

    @diagnostic.get("/api/v1/debug/routes")
    def startup_debug_routes() -> dict[str, object]:
        return {
            "status": "startup_error",
            "routes": ["/", "/health", "/api/v1/debug/routes"],
            "error": message,
        }

    return diagnostic


try:
    from app.main import app  # noqa: E402
except Exception as exc:  # pragma: no cover - deployment diagnostic fallback.
    app = _diagnostic_app(exc)
