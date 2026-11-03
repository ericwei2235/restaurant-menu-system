import sqlite3

import pytest

import app as app_module


# ---------- Which Stripe keys are accepted ----------

@pytest.mark.parametrize(
    "key",
    [
        None,                    # no key set at all
        "",                      # empty
        "sk_live_123",           # a live key: must never be used by this demo
        "pk_test_123",           # a publishable key, not a secret key
    ],
)
def test_payments_are_off_without_a_test_secret_key(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("STRIPE_SECRET_KEY", key)
    assert app_module.get_stripe_client() is None


def test_test_secret_key_creates_a_client(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    assert app_module.get_stripe_client() is not None


def test_orders_are_refused_when_payments_are_off(client, place_order, price_id, query, monkeypatch):
    monkeypatch.setattr(app_module, "get_stripe_client", lambda: None)
    response = place_order(items=[(price_id("002"), 1)])

    assert response.status_code == 503
    assert response.get_json() == {"error": "Online payment isn't set up right now, so orders can't be placed."}
    # Nothing is saved, so there are no orders that can never be paid for
    assert query("SELECT COUNT(*) FROM orders") == [(0,)]


# ---------- What gets sent to Stripe ----------

def test_checkout_uses_database_prices_in_cents(place_order, price_id, fake_stripe):
    place_order(items=[(price_id("002"), 2), (price_id("031", "Extra Large"), 1)])
    line_items = fake_stripe.created[0]["line_items"]

    assert line_items == [
        {"price_data": {"currency": "usd", "unit_amount": 375, "product_data": {"name": "Egg Rolls (2)"}}, "quantity": 2},
        {"price_data": {"currency": "usd", "unit_amount": 1595, "product_data": {"name": "Vegetable Fried Rice (Extra Large)"}}, "quantity": 1},
    ]


def test_prices_sent_by_the_browser_are_ignored(client, price_id, fake_stripe):
    # Someone adding their own prices to the request must not change what Stripe charges
    body = {
        "name": "Eric",
        "price_cents": 1,
        "items": [{"price_id": price_id("002"), "quantity": 1, "price_cents": 1, "unit_amount": 1}],
    }
    client.post("/api/orders", json=body)
    assert fake_stripe.created[0]["line_items"][0]["price_data"]["unit_amount"] == 375


def test_checkout_returns_customer_to_their_order_page(place_order, price_id, fake_stripe, latest_order):
    place_order(items=[(price_id("002"), 1)])
    params = fake_stripe.created[0]
    order = latest_order()

    assert params["mode"] == "payment"
    assert params["success_url"] == f"http://localhost/order/{order.token}"
    assert params["cancel_url"] == f"http://localhost/order/{order.token}"
    assert params["metadata"] == {"order_token": order.token}


def test_return_links_use_https_behind_render_proxy(client, price_id, fake_stripe):
    # On Render, the proxy marks the original request as HTTPS with this header
    body = {"name": "Eric", "items": [{"price_id": price_id("002"), "quantity": 1}]}
    client.post("/api/orders", json=body, headers={"X-Forwarded-Proto": "https"})
    assert fake_stripe.created[0]["success_url"].startswith("https://localhost/order/")


def test_stripe_session_is_saved_with_the_order(place_order, price_id, query):
    place_order(items=[(price_id("002"), 1)])
    assert query("SELECT stripe_session_id FROM orders") == [("cs_test_1",)]


def test_stripe_outage_when_creating_checkout_returns_502(place_order, price_id, query, fake_stripe):
    fake_stripe.fail_create = True
    response = place_order(items=[(price_id("002"), 1)])

    assert response.status_code == 502
    assert "error" in response.get_json()
    # The order is left unpaid with no checkout, so it never shows up for the kitchen
    assert query("SELECT status, stripe_session_id FROM orders") == [("awaiting_payment", None)]


# ---------- Checking payment when the order is looked up ----------

def test_paid_order_is_confirmed_and_sent_to_the_kitchen(client, place_order, price_id, fake_stripe, latest_order, query):
    place_order(name="Eric", items=[(price_id("002"), 1)])
    order = latest_order()
    fake_stripe.pay(order.session_id)
    data = client.get(order.link).get_json()

    assert data["payment_state"] == "paid"
    assert data["checkout_url"] is None
    assert query("SELECT status FROM orders") == [("pending",)]


def test_unpaid_order_offers_a_way_back_to_payment(client, place_order, price_id, fake_stripe, latest_order, query):
    # The customer clicked "back" on Stripe's page without paying
    place_order(items=[(price_id("002"), 1)])
    order = latest_order()
    data = client.get(order.link).get_json()

    assert data["payment_state"] == "open"
    assert data["checkout_url"] == f"https://checkout.stripe.test/{order.session_id}"
    assert query("SELECT status FROM orders") == [("awaiting_payment",)]


def test_expired_checkout_is_reported(client, place_order, price_id, fake_stripe, latest_order, query):
    place_order(items=[(price_id("002"), 1)])
    order = latest_order()
    fake_stripe.expire(order.session_id)
    data = client.get(order.link).get_json()

    assert data["payment_state"] == "expired"
    assert data["checkout_url"] is None
    assert query("SELECT status FROM orders") == [("awaiting_payment",)]


def test_stripe_outage_when_checking_payment_leaves_order_unpaid(client, place_order, price_id, fake_stripe, latest_order, query):
    place_order(items=[(price_id("002"), 1)])
    order = latest_order()
    fake_stripe.pay(order.session_id)
    fake_stripe.fail_retrieve = True
    response = client.get(order.link)

    assert response.status_code == 200
    assert response.get_json()["payment_state"] == "unknown"
    # Never assume an order is paid without Stripe saying so
    assert query("SELECT status FROM orders") == [("awaiting_payment",)]


def test_paid_order_is_not_rechecked_with_stripe(client, place_paid_order, price_id, fake_stripe):
    order = place_paid_order(items=[(price_id("002"), 1)])
    # Once the database says paid, the lookup shouldn't need Stripe at all
    fake_stripe.fail_retrieve = True

    assert client.get(order.link).get_json()["payment_state"] == "paid"


# ---------- Database rules ----------

def test_database_rejects_unknown_order_statuses(db_path):
    # The CHECK constraint in schema.sql only allows the three real statuses
    conn = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO orders (customer_name, public_token, status) VALUES ('X', 'abc', 'refunded')")
    conn.close()
