"""Production serving of an already-built React application."""

from pathlib import Path

from fastapi.testclient import TestClient

from core.config import Settings
from main import create_app


def test_frontend_dist_is_served_with_spa_fallback(tmp_path: Path) -> None:
    dist = tmp_path / "frontend-dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<main>MyLabData</main>", encoding="utf-8")
    (assets / "app.js").write_text("console.info('MyLabData');", encoding="utf-8")
    settings = Settings(
        data_root=tmp_path / "DryData",
        frontend_dist_directory=dist,
    )

    with TestClient(create_app(settings)) as client:
        assert client.get("/").text == "<main>MyLabData</main>"
        assert client.get("/molecules/42").text == "<main>MyLabData</main>"
        assert client.get("/assets/app.js").text == "console.info('MyLabData');"
        assert client.get("/api/v1/does-not-exist").status_code == 404
