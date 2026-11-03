import os
import sqlite3
from types import SimpleNamespace

import pytest
import stripe

import app as app_module

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_PASSWORD = "test-password"
SECRET_KEY = "test-secret-key-that-is-at-least-32-characters-long"

# Admin POSTs must say they came from this site; the test client's site is http://localhost
SAME_SITE = {"Origin": "http://localhost"}


class FakeStripe:
    # Stands in for stripe.StripeClient in tests, so no test ever contacts the real Stripe.
    # It mimics the one part the app uses: client.v1.checkout.sessions.create(...) and .retrieve(...)

    def __init__(self):
        self.sessions = {}
        self.created = []       # the params of every checkout session the app asked for
        self.fail_create = False
        self.fail_retrieve = False
        self.v1 = SimpleNamespace(checkout=SimpleNamespace(sessions=self))

    def create(self, params):
        if self.fail_create:
            raise stripe.APIConnectionError("Pretend Stripe is unreachable")
        self.created.append(params)
        session_id = f"cs_test_{len(self.created)}"
        session = SimpleNamespace(
            id=session_id,
            url=f"https://checkout.stripe.test/{session_id}",
            payment_status="unpaid",
            status="open",
        )
        self.sessions[session_id] = session
        return session

    def retrieve(self, session_id):
        if self.fail_retrieve:
            raise stripe.APIConnectionError("Pretend Stripe is unreachable")
        return self.sessions[session_id]

    # Helpers that play the customer's part on Stripe's page
    def pay(self, session_id):
        self.sessions[session_id].payment_status = "paid"
        self.sessions[session_id].status = "complete"

    def expire(self, session_id):
        self.sessions[session_id].status = "expired"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    # Build a brand-new database in a temporary folder for each test,
    # so tests never touch the real restaurant.db and can't affect each other
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    with open(os.path.join(PROJECT_DIR, "schema.sql")) as f:
        conn.executescript(f.read())
    with open(os.path.join(PROJECT_DIR, "seed.sql")) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

    # Point the app at the temporary database for the length of this test
    monkeypatch.setattr(app_module, "DATABASE", str(path))
    return path


@pytest.fixture
def fake_stripe(monkeypatch):
    # Every test that uses the app gets a fresh fake Stripe in place of the real client
    fake = FakeStripe()
    monkeypatch.setattr(app_module, "get_stripe_client", lambda: fake)
    return fake


@pytest.fixture
def client(db_path, fake_stripe, monkeypatch):
    # A fake browser that sends requests straight to the app, without running a server.
    # Like a real browser, it keeps cookies between requests, so a login stays logged in
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setitem(app_module.app.config, "SECRET_KEY", SECRET_KEY)
    # The test client talks plain http://, so Secure-only cookies would never be sent back
    monkeypatch.setitem(app_module.app.config, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setitem(app_module.app.config, "TESTING", True)
    return app_module.app.test_client()


@pytest.fixture
def login(client):
    # Log the test client in as admin (or try to, with other credentials)
    def submit(username="admin", password=ADMIN_PASSWORD, headers=SAME_SITE):
        return client.post("/api/admin/login", json={"username": username, "password": password}, headers=headers)
    return submit


@pytest.fixture
def logged_in(login):
    # For tests that just need to be logged in already
    response = login()
    assert response.status_code == 200


@pytest.fixture
def query(db_path):
    # Run a SQL query against the test database, to check what the app actually saved
    def run(sql, params=()):
        conn = sqlite3.connect(db_path)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows
    return run


@pytest.fixture
def price_id(query):
    # Look up a price option's id by item number and size, instead of hard-coding ids
    def find(item_number, size_label=None):
        rows = query(
            """
            SELECT p.id FROM menu_item_prices p
            JOIN menu_items m ON m.id = p.menu_item_id
            WHERE m.item_number = ? AND p.size_label IS ?
            """,
            (item_number, size_label),
        )
        assert len(rows) == 1, f"expected one price for {item_number} {size_label}, found {len(rows)}"
        return rows[0][0]
    return find


@pytest.fixture
def place_order(client):
    # Send an order to the API the way the React app will, e.g. items=[(price_id, quantity), ...]
    def submit(name="Test Customer", phone="630-555-1234", items=()):
        body = {
            "name": name,
            "phone": phone,
            "items": [{"price_id": price, "quantity": quantity} for price, quantity in items],
        }
        return client.post("/api/orders", json=body)
    return submit


@pytest.fixture
def latest_order(query):
    # The most recently placed order's token and Stripe session id
    def find():
        token, session_id = query("SELECT public_token, stripe_session_id FROM orders ORDER BY id DESC LIMIT 1")[0]
        return SimpleNamespace(token=token, session_id=session_id, link=f"/api/orders/{token}")
    return find


@pytest.fixture
def place_paid_order(client, place_order, fake_stripe, latest_order):
    # Place an order, pay for it on (fake) Stripe, then load the order like the confirmation page does,
    # which is when the app checks with Stripe and marks the order paid
    def submit(**kwargs):
        place_order(**kwargs)
        order = latest_order()
        fake_stripe.pay(order.session_id)
        client.get(order.link)
        return order
    return submit
