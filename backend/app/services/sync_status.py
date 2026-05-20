from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import ClientAccount


def mark_sync_success(db: Session, client_id: str) -> None:
    client = db.get(ClientAccount, client_id)
    if not client:
        return
    client.sync_status = "ok"
    client.sync_error = None
    client.last_synced_at = datetime.now(UTC)
    client.sync_version = (client.sync_version or 0) + 1
    db.commit()


def mark_sync_failed(db: Session, client_id: str, error: str) -> None:
    client = db.get(ClientAccount, client_id)
    if not client:
        return
    client.sync_status = "error"
    client.sync_error = error[:500]
    client.last_synced_at = datetime.now(UTC)
    client.sync_version = (client.sync_version or 0) + 1
    db.commit()
