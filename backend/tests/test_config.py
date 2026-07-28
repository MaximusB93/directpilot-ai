import re

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


def test_frontend_preview_is_an_allowed_browser_origin():
    assert "https://directpilot-ai-frontend-preview-directpilot-ai1.vercel.app" in config.Settings().allowed_origins


def test_frontend_preview_deployment_urls_match_the_cors_pattern():
    settings = config.Settings()
    assert settings.allowed_origin_regex
    assert re.fullmatch(
        settings.allowed_origin_regex,
        "https://directpilot-ai-frontend-preview-f1febhv14-directpilot-ai1.vercel.app",
    )
