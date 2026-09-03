from app import db


def test_serverless_startup_does_not_run_schema_ddl(monkeypatch):
    monkeypatch.setattr(db, "engine", object())
    calls: list[str] = []
    monkeypatch.setattr(db, "check_db_connection", lambda: calls.append("check"))
    monkeypatch.setattr(db, "ensure_ai_audit_job_schema", lambda: calls.append("audit_schema"))
    monkeypatch.setattr(db, "ensure_direct_read_schema", lambda: calls.append("direct_schema"))

    db.init_db(run_schema_patch=False)

    assert calls == ["check"]
