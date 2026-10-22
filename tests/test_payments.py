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
    response = place_order(**{f"qty_{price_id('002')}": "1"})

    assert response.status_code == 503
    # Nothing is saved, so there are no orders that can never be paid for
    assert query("SELECT COUNT(*) FROM orders") == [(0,)]


# ---------- What gets sent to Stripe ----------

def test_checkout_uses_database_prices_in_cents(place_order, price_id, fake_stripe):
    place_order(**{f"qty_{price_id('002')}": "2", f"qty_{price_id('031', 'Extra Large')}": "1"})
    line_items = fake_stripe.created[0]["line_items"]

    assert line_items == [
        {"price_data": {"currency": "usd", "unit_amount": 375, "product_data": {"name": "Egg Rolls (2)"}}, "quantity": 2},
        {"price_data": {"currency": "usd", "unit_amount": 1595, "product_data": {"name": "Vegetable Fried Rice (Extra Large)"}}, "quantity": 1},
    ]


def test_price_fields_in_the_form_are_ignored(place_order, price_id, fake_stripe):
    # Someone editing the form to add their own price must not change what Stripe charges
    place_order(**{f"qty_{price_id('002')}": "1", "price": "1", "unit_amount": "1"})
    assert fake_stripe.created[0]["line_items"][0]["price_data"]["unit_amount"] == 375


def test_checkout_returns_customer_to_their_order_link(place_order, price_id, fake_stripe, latest_order):
    place_order(**{f"qty_{price_id('002')}": "1"})
    params = fake_stripe.created[0]
    order = latest_order()

    assert params["mode"] == "payment"
    assert params["success_url"] == f"http://localhost/order/{order.token}"
    assert params["cancel_url"] == f"http://localhost/order/{order.token}"
    assert params["metadata"] == {"order_token": order.token}


def test_stripe_session_is_saved_with_the_order(place_order, price_id, query):
    place_order(**{f"qty_{price_id('002')}": "1"})
    assert query("SELECT stripe_session_id FROM orders") == [("cs_test_1",)]


def test_stripe_outage_when_creating_checkout_shows_an_error(place_order, price_id, query, fake_stripe):
    fake_stripe.fail_create = True
    response = place_order(**{f"qty_{price_id('002')}": "1"})

    assert response.status_code == 502
    # The order is left unpaid with no checkout, so it never shows up for the kitchen
    assert query("SELECT status, stripe_session_id FROM orders") == [("awaiting_payment", None)]


# ---------- Coming back from Stripe ----------

def test_paid_order_is_confirmed_and_sent_to_the_kitchen(client, place_order, price_id, fake_stripe, latest_order, query):
    place_order(name="Eric", **{f"qty_{price_id('002')}": "1"})
    order = latest_order()
    fake_stripe.pay(order.session_id)
    html = client.get(order.link).get_data(as_text=True)

    assert "Thanks, Eric!" in html
    assert "Payment received" in html
    assert query("SELECT status FROM orders") == [("pending",)]


def test_unpaid_order_offers_a_way_back_to_payment(client, place_order, price_id, fake_stripe, latest_order, query):
    # The customer clicked "back" on Stripe's page without paying
    place_order(**{f"qty_{price_id('002')}": "1"})
    order = latest_order()
    html = client.get(order.link).get_data(as_text=True)

    assert "isn't paid yet" in html
    assert f"https://checkout.stripe.test/{order.session_id}" in html
    assert query("SELECT status FROM orders") == [("awaiting_payment",)]


def test_expired_checkout_says_the_order_was_not_placed(client, place_order, price_id, fake_stripe, latest_order, query):
    place_order(**{f"qty_{price_id('002')}": "1"})
    order = latest_order()
    fake_stripe.expire(order.session_id)
    html = client.get(order.link).get_data(as_text=True)

    assert "has expired" in html
    assert query("SELECT status FROM orders") == [("awaiting_payment",)]


def test_stripe_outage_when_checking_payment_leaves_order_unpaid(client, place_order, price_id, fake_stripe, latest_order, query):
    place_order(**{f"qty_{price_id('002')}": "1"})
    order = latest_order()
    fake_stripe.pay(order.session_id)
    fake_stripe.fail_retrieve = True
    response = client.get(order.link)

    assert response.status_code == 200
    assert "couldn't confirm the payment" in response.get_data(as_text=True)
    # Never assume an order is paid without Stripe saying so
    assert query("SELECT status FROM orders") == [("awaiting_payment",)]


def test_paid_order_is_not_rechecked_with_stripe(client, place_paid_order, price_id, fake_stripe):
    order = place_paid_order(**{f"qty_{price_id('002')}": "1"})
    # Once the database says paid, the page shouldn't need Stripe at all
    fake_stripe.fail_retrieve = True
    html = client.get(order.link).get_data(as_text=True)

    assert "Payment received" in html


# ---------- Admin only sees paid orders ----------

def test_admin_hides_unpaid_orders(client, admin_auth, place_order, place_paid_order, price_id):
    place_order(name="Never Paid", **{f"qty_{price_id('002')}": "1"})
    place_paid_order(name="Paid Customer", **{f"qty_{price_id('002')}": "1"})
    html = client.get("/admin", auth=admin_auth).get_data(as_text=True)

    assert "Paid Customer" in html
    assert "Never Paid" not in html


def test_admin_cannot_complete_an_unpaid_order(client, admin_auth, place_order, price_id, query):
    place_order(**{f"qty_{price_id('002')}": "1"})
    client.post("/admin/orders/1/complete", auth=admin_auth, headers={"Origin": "http://localhost"})

    assert query("SELECT status FROM orders") == [("awaiting_payment",)]


def test_database_rejects_unknown_order_statuses(db_path):
    # The CHECK constraint in schema.sql only allows the three real statuses
    conn = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO orders (customer_name, public_token, status) VALUES ('X', 'abc', 'refunded')")
    conn.close()
