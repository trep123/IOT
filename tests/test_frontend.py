import pytest
from django.test import override_settings


@pytest.mark.django_db
def test_spa_routes_return_index(client, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<div id=app></div>", encoding="utf-8")
    with override_settings(FRONTEND_DIST=dist):
        for path in ["/", "/dashboard", "/tasks/12", "/devices/dev-001"]:
            r = client.get(path)
            assert r.status_code == 200
            assert b"id=app" in r.content


@pytest.mark.django_db
def test_spa_without_build_shows_hint(client, tmp_path):
    with override_settings(FRONTEND_DIST=tmp_path / "missing"):
        r = client.get("/dashboard")
        assert r.status_code == 503
        assert "npm run build" in r.content.decode()


@pytest.mark.django_db
def test_api_paths_not_swallowed_by_spa(client):
    assert client.get("/api/devices/").status_code in (401, 403)
