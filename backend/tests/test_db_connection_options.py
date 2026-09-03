from app.db import _database_engine_options


def test_postgres_engine_options_bound_connection_and_query_waits() -> None:
    options = _database_engine_options("postgresql://user:secret@example.test:5432/directpilot")

    assert options["pool_pre_ping"] is True
    assert options["pool_timeout"] == 10
    assert options["pool_recycle"] == 300
    assert options["connect_args"] == {
        "connect_timeout": 10,
        "options": "-c statement_timeout=20000 -c lock_timeout=5000",
    }


def test_sqlite_engine_options_do_not_receive_postgres_connect_args() -> None:
    options = _database_engine_options("sqlite+pysqlite:///:memory:")

    assert "connect_args" not in options
    assert options["pool_pre_ping"] is True
