import pytest

import app as app_module
from conftest import SAME_SITE


@pytest.fixture
def two_orders(place_paid_order, price_id):
    # Two paid orders; order #1 is placed before order #2
    place_paid_order(name="First Customer", items=[(price_id("002"), 1)])
    place_paid_order(name="Second Customer", items=[(price_id("020", "Small"), 2)])


def complete(client, order_number, headers=SAME_SITE):
    return client.post(f"/api/admin/orders/{order_number}/complete", headers=headers)


# ---------- Logging in ----------

def test_login_with_correct_credentials(login):
    response = login()
    assert response.status_code == 200
    assert response.get_json() == {"username": "admin"}


@pytest.mark.parametrize(
    "username, password",
    [
        ("admin", "wrong-password"),
        ("someone", "test-password"),
        ("admin", ""),
        ("admin", "pässwörd"),  # non-English characters must be rejected, not crash
    ],
)
def test_login_rejects_wrong_credentials_with_one_message(login, username, password):
    response = login(username=username, password=password)

    assert response.status_code == 401
    # Same message whether the username or password was wrong, so usernames can't be discovered
    assert response.get_json() == {"error": "Incorrect username or password."}


@pytest.mark.parametrize("body", [{"username": "admin"}, {"username": "admin", "password": 123}, ["admin"]])
def test_login_rejects_malformed_requests(client, body):
    assert client.post("/api/admin/login", json=body, headers=SAME_SITE).status_code == 400


def test_login_from_another_site_is_blocked(login):
    # Stops another website from silently logging a visitor into (or out of) the admin
    assert login(headers={"Origin": "https://evil.example"}).status_code == 403


def test_failed_login_does_not_log_in(client, login):
    login(password="wrong-password")
    assert client.get("/api/admin/session").get_json() == {"logged_in": False}


# ---------- Session cookie ----------

def test_session_reports_logged_in_state(client, login):
    assert client.get("/api/admin/session").get_json() == {"logged_in": False}
    login()
    assert client.get("/api/admin/session").get_json() == {"logged_in": True, "username": "admin"}


def test_session_cookie_has_safety_flags(client, login, monkeypatch):
    # In production the cookie must be HttpOnly, SameSite=Lax, and Secure (HTTPS only)
    monkeypatch.setitem(app_module.app.config, "SESSION_COOKIE_SECURE", True)
    cookie = login().headers["Set-Cookie"]

    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Secure" in cookie
    # A lasting login (12 hours) rather than one that ends when the browser closes
    assert "Expires=" in cookie


def test_tampered_session_cookie_is_rejected(client, login):
    login()
    # Change the signed cookie's value: the signature no longer matches, so the server ignores it
    cookie = client.get_cookie("session")
    client.set_cookie("session", cookie.value[:-4] + "AAAA")

    assert client.get("/api/admin/session").get_json() == {"logged_in": False}
    assert client.get("/api/admin/orders").status_code == 401


def test_cookie_signed_with_a_different_key_is_rejected(client, login, monkeypatch):
    # A cookie made with someone else's key can't log in here
    login()
    monkeypatch.setitem(app_module.app.config, "SECRET_KEY", "a-completely-different-secret-key-of-32-plus-chars")

    assert client.get("/api/admin/orders").status_code == 401


# ---------- Logging out ----------

def test_logout_ends_the_session(client, logged_in):
    response = client.post("/api/admin/logout", headers=SAME_SITE)

    assert response.status_code == 204
    assert client.get("/api/admin/session").get_json() == {"logged_in": False}
    assert client.get("/api/admin/orders").status_code == 401


def test_logout_from_another_site_is_blocked(client, logged_in):
    assert client.post("/api/admin/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/admin/session").get_json()["logged_in"] is True


# ---------- Fail closed when not configured ----------

def test_admin_is_off_without_a_password(client, logged_in, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD")
    assert client.get("/api/admin/orders").status_code == 503
    assert client.get("/api/admin/session").get_json() == {"logged_in": False}


@pytest.mark.parametrize("key", [None, "", "too-short-to-be-safe"])
def test_admin_is_off_without_a_strong_secret_key(client, login, monkeypatch, key):
    monkeypatch.setitem(app_module.app.config, "SECRET_KEY", key)
    assert login().status_code == 503


# ---------- Order list ----------

def test_orders_require_login(client, two_orders):
    response = client.get("/api/admin/orders")
    assert response.status_code == 401
    assert response.get_json() == {"error": "Please log in."}


def test_orders_match_the_documented_shape(client, logged_in, two_orders):
    data = client.get("/api/admin/orders").get_json()
    second = data["pending"][1]

    assert data["completed"] == []
    assert second["order_number"] == 2
    assert second["customer_name"] == "Second Customer"
    assert second["customer_phone"] == "630-555-1234"
    assert second["status"] == "pending"
    assert second["lines"] == [
        {"name": "Wonton Soup", "size": "Small", "quantity": 2, "unit_price_cents": 425, "line_total_cents": 850},
    ]
    assert second["total_cents"] == 850


def test_order_times_are_utc_iso_8601(client, logged_in, two_orders):
    created_at = client.get("/api/admin/orders").get_json()["pending"][0]["created_at"]
    # e.g. "2026-10-08T05:27:03Z"
    assert len(created_at) == 20 and created_at[10] == "T" and created_at.endswith("Z")


def test_pending_orders_are_oldest_first(client, logged_in, two_orders):
    pending = client.get("/api/admin/orders").get_json()["pending"]
    assert [o["customer_name"] for o in pending] == ["First Customer", "Second Customer"]


def test_unpaid_orders_are_hidden(client, logged_in, place_order, place_paid_order, price_id):
    place_order(name="Never Paid", items=[(price_id("002"), 1)])
    place_paid_order(name="Paid Customer", items=[(price_id("002"), 1)])
    pending = client.get("/api/admin/orders").get_json()["pending"]

    assert [o["customer_name"] for o in pending] == ["Paid Customer"]


# ---------- Marking orders complete ----------

def test_marking_complete_updates_status(client, logged_in, two_orders, query):
    response = complete(client, 1)

    assert response.status_code == 200
    assert response.get_json() == {"order_number": 1, "status": "completed"}
    assert query("SELECT id, status FROM orders ORDER BY id") == [(1, "completed"), (2, "pending")]


def test_completed_order_moves_to_completed_list(client, logged_in, two_orders):
    complete(client, 1)
    data = client.get("/api/admin/orders").get_json()

    assert [o["customer_name"] for o in data["pending"]] == ["Second Customer"]
    assert [o["customer_name"] for o in data["completed"]] == ["First Customer"]


def test_completed_orders_are_newest_first(client, logged_in, two_orders):
    complete(client, 1)
    complete(client, 2)
    completed = client.get("/api/admin/orders").get_json()["completed"]

    assert [o["order_number"] for o in completed] == [2, 1]


def test_marking_complete_twice_is_harmless(client, logged_in, two_orders, query):
    complete(client, 1)
    response = complete(client, 1)

    assert response.status_code == 200
    assert query("SELECT status FROM orders WHERE id = 1") == [("completed",)]


def test_unpaid_order_cannot_be_completed(client, logged_in, place_order, price_id, query):
    place_order(items=[(price_id("002"), 1)])
    response = complete(client, 1)

    assert response.status_code == 409
    assert query("SELECT status FROM orders") == [("awaiting_payment",)]


def test_completing_a_missing_order_is_404(client, logged_in):
    assert complete(client, 999).status_code == 404


def test_referer_header_is_accepted_when_origin_is_missing(client, logged_in, two_orders, query):
    complete(client, 1, headers={"Referer": "http://localhost/admin"})
    assert query("SELECT status FROM orders WHERE id = 1") == [("completed",)]


# ---------- Blocked requests ----------

def test_marking_complete_requires_login(client, two_orders, query):
    assert complete(client, 1).status_code == 401
    assert query("SELECT status FROM orders WHERE id = 1") == [("pending",)]


@pytest.mark.parametrize(
    "headers",
    [
        {},                                              # no Origin or Referer at all
        {"Origin": "https://evil.example"},              # another website
        {"Referer": "https://evil.example/attack"},      # another website, via Referer
        {"Origin": "null"},                              # sandboxed or privacy-stripped origin
    ],
)
def test_cross_site_requests_are_blocked(client, logged_in, two_orders, query, headers):
    response = complete(client, 1, headers=headers)

    assert response.status_code == 403
    assert query("SELECT status FROM orders WHERE id = 1") == [("pending",)]


def test_marking_complete_only_accepts_post(client, logged_in, two_orders):
    assert client.get("/api/admin/orders/1/complete").status_code == 405
