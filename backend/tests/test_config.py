from app.core import config


def test_schema_patch_is_disabled_by_default_on_vercel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    assert config._database_schema_patch_default() == "false"


def test_schema_patch_remains_enabled_for_local_development(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")

    assert config._database_schema_patch_default() == "true"


def test_schema_patch_is_disabled_in_production_without_vercel(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert config._database_schema_patch_default() == "false"
