import pytest

import app as app_module


@pytest.fixture
def built_frontend(tmp_path, monkeypatch):
    # A tiny stand-in for frontend/dist, so these tests don't need "npm run build" first
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id='root'></div><!-- the React app -->")
    (dist / "assets" / "index-abc123.js").write_text("console.log('app')")
    (dist / "favicon.svg").write_text("<svg></svg>")
    monkeypatch.setattr(app_module, "FRONTEND_DIST", str(dist))
    return dist


# ---------- Pages get the React app ----------

@pytest.mark.parametrize("path", ["/", "/order/k3J9xQ_m2vLpA8rT0bZcWe", "/admin", "/some/page/that/does-not-exist"])
def test_page_addresses_get_index_html(client, built_frontend, path):
    response = client.get(path)

    assert response.status_code == 200
    assert "the React app" in response.get_data(as_text=True)
    # Browsers re-check index.html each visit, so a new deploy shows up right away
    assert response.headers["Cache-Control"] == "no-cache"


def test_built_files_are_served(client, built_frontend):
    assert client.get("/favicon.svg").get_data(as_text=True) == "<svg></svg>"


def test_fingerprinted_assets_are_cached_for_a_year(client, built_frontend):
    response = client.get("/assets/index-abc123.js")

    assert response.get_data(as_text=True) == "console.log('app')"
    assert "max-age=31536000" in response.headers["Cache-Control"]


def test_missing_asset_falls_back_to_the_app(client, built_frontend):
    # An unknown file isn't an error page from Flask; React shows its own "not found" page
    assert "the React app" in client.get("/assets/old-deleted-file.js").get_data(as_text=True)


@pytest.mark.parametrize("path", ["/../app.py", "/..%2Fapp.py", "/assets/..%2F..%2Fapp.py"])
def test_files_outside_the_build_folder_are_never_served(client, built_frontend, path):
    body = client.get(path).get_data(as_text=True)
    assert "import stripe" not in body


def test_missing_build_gives_a_clear_message(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "FRONTEND_DIST", str(tmp_path / "not-built"))
    response = client.get("/")

    assert response.status_code == 503
    assert "npm run build" in response.get_data(as_text=True)


# ---------- Backend addresses are left alone ----------

def test_api_still_works_with_the_frontend_built(client, built_frontend):
    response = client.get("/api/menu")
    assert response.status_code == 200
    assert response.is_json


def test_unknown_api_address_is_a_json_404_not_the_app(client, built_frontend):
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Not found."}


def test_wrong_method_on_api_is_still_405_not_the_app(client, built_frontend):
    # GET to a POST-only address must not be answered with the React page
    assert client.get("/api/orders").status_code == 405
    assert client.get("/api/admin/logout").status_code == 405


def test_webhook_is_still_post_only(client, built_frontend):
    assert client.get("/stripe/webhook").status_code == 405
