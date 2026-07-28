from pathlib import Path

from app import main


def test_frontend_file_is_served_from_bundled_directory(tmp_path, monkeypatch):
    asset = tmp_path / "src" / "main.js"
    asset.parent.mkdir()
    asset.write_text("export {}", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIRECTORY", tmp_path)

    response = main._frontend_file("src/main.js")

    assert response is not None
    assert Path(response.path) == asset


def test_frontend_file_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FRONTEND_DIRECTORY", tmp_path)

    assert main._frontend_file("../secret.txt") is None
