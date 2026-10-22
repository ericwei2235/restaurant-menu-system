import pytest

SAME_SITE = {"Origin": "http://localhost"}


@pytest.fixture
def two_orders(place_paid_order, price_id):
    # Two paid orders; order #1 is placed before order #2
    place_paid_order(name="First Customer", **{f"qty_{price_id('002')}": "1"})
    place_paid_order(name="Second Customer", **{f"qty_{price_id('020', 'Small')}": "2"})


# ---------- Logging in ----------

def test_admin_is_disabled_when_no_password_is_set(client, monkeypatch, admin_auth):
    monkeypatch.delenv("ADMIN_PASSWORD")
    assert client.get("/admin", auth=admin_auth).status_code == 503


def test_admin_asks_for_login(client):
    response = client.get("/admin")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == 'Basic realm="China Chef Admin"'


@pytest.mark.parametrize(
    "username, password",
    [
        ("admin", "wrong-password"),
        ("someone", "test-password"),
        ("admin", ""),
        ("admin", "pässwörd"),  # non-English characters must be rejected, not crash
    ],
)
def test_admin_rejects_wrong_credentials(client, username, password):
    assert client.get("/admin", auth=(username, password)).status_code == 401


def test_admin_page_loads_with_correct_login(client, admin_auth):
    assert client.get("/admin", auth=admin_auth).status_code == 200


# ---------- Order list ----------

def test_admin_lists_pending_orders_oldest_first(client, admin_auth, two_orders):
    html = client.get("/admin", auth=admin_auth).get_data(as_text=True)
    pending_section = html.split("Recently completed")[0]

    assert pending_section.index("First Customer") < pending_section.index("Second Customer")


def test_admin_shows_order_totals(client, admin_auth, two_orders):
    html = client.get("/admin", auth=admin_auth).get_data(as_text=True)
    # Order #2 is 2 Small Wonton Soups at $4.25
    assert "Total: $8.50" in html


# ---------- Marking orders complete ----------

def test_marking_complete_updates_status(client, admin_auth, two_orders, query):
    response = client.post("/admin/orders/1/complete", auth=admin_auth, headers=SAME_SITE)

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin"
    assert query("SELECT id, status FROM orders ORDER BY id") == [(1, "completed"), (2, "pending")]


def test_completed_order_moves_to_completed_section(client, admin_auth, two_orders):
    client.post("/admin/orders/1/complete", auth=admin_auth, headers=SAME_SITE)
    html = client.get("/admin", auth=admin_auth).get_data(as_text=True)
    completed_section = html.split("Recently completed")[1]

    assert "First Customer" in completed_section
    assert "Second Customer" not in completed_section


def test_marking_complete_twice_is_harmless(client, admin_auth, two_orders, query):
    client.post("/admin/orders/1/complete", auth=admin_auth, headers=SAME_SITE)
    response = client.post("/admin/orders/1/complete", auth=admin_auth, headers=SAME_SITE)

    assert response.status_code == 302
    assert query("SELECT status FROM orders WHERE id = 1") == [("completed",)]


def test_referer_header_is_accepted_when_origin_is_missing(client, admin_auth, two_orders, query):
    client.post("/admin/orders/1/complete", auth=admin_auth, headers={"Referer": "http://localhost/admin"})
    assert query("SELECT status FROM orders WHERE id = 1") == [("completed",)]


# ---------- Blocked requests ----------

def test_marking_complete_requires_login(client, two_orders, query):
    assert client.post("/admin/orders/1/complete", headers=SAME_SITE).status_code == 401
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
def test_cross_site_requests_are_blocked(client, admin_auth, two_orders, query, headers):
    response = client.post("/admin/orders/1/complete", auth=admin_auth, headers=headers)

    assert response.status_code == 403
    assert query("SELECT status FROM orders WHERE id = 1") == [("pending",)]


def test_marking_complete_only_accepts_post(client, admin_auth, two_orders):
    assert client.get("/admin/orders/1/complete", auth=admin_auth).status_code == 405
