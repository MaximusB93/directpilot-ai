"""Vercel FastAPI entrypoint.

Vercel auto-detects FastAPI apps exported as ``app`` from root-level
``index.py``. The actual backend package lives in ``backend/app`` and uses
absolute imports such as ``from app...``, so we add ``backend`` to
``sys.path`` before importing the ASGI application.
"""

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402
