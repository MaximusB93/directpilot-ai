from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.connected_accounts as connected_accounts
from app.db import Base
from app.models import ConnectedAccount, OAuthToken, Organization


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_latest_yandex_token_can_be_scoped_by_organization(monkeypatch) -> None:
    monkeypatch.setattr(connected_accounts, "decrypt_secret", lambda value: value)
    SessionLocal = _session_factory()

    with SessionLocal() as db:
        org_a = Organization(name="Workspace A")
        org_b = Organization(name="Workspace B")
        db.add_all([org_a, org_b])
        db.flush()

        account_a = ConnectedAccount(organization_id=org_a.id, provider="yandex", status="connected")
        account_b = ConnectedAccount(organization_id=org_b.id, provider="yandex", status="connected")
        db.add_all([account_a, account_b])
        db.flush()

        now = datetime.now(UTC)
        db.add_all(
            [
                OAuthToken(
                    account_id=account_a.id,
                    token_type="bearer",
                    access_token_encrypted="token-a",
                    created_at=now,
                ),
                OAuthToken(
                    account_id=account_b.id,
                    token_type="bearer",
                    access_token_encrypted="token-b",
                    created_at=now + timedelta(seconds=1),
                ),
            ]
        )
        db.commit()

        assert connected_accounts.get_latest_yandex_access_token(db, organization_id=org_a.id) == "token-a"
        assert connected_accounts.get_latest_yandex_access_token(db, organization_id=org_b.id) == "token-b"
        assert connected_accounts.get_latest_yandex_access_token(db) == "token-b"

