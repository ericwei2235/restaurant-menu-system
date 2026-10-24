import hashlib
import hmac
import json
import time

import pytest

WEBHOOK_SECRET = "whsec_test_secret"


@pytest.fixture
def send_webhook(client, monkeypatch):
    # Send a message to the webhook signed the same way Stripe signs real ones:
    # an HMAC-SHA256 of "timestamp.body" using the webhook secret
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)

    def send(event_type, session_id, payment_status="paid", secret=WEBHOOK_SECRET, timestamp=None, tamper=False):
        body = json.dumps({
            "id": "evt_test",
            "object": "event",
            "type": event_type,
            "data": {"object": {"id": session_id, "object": "checkout.session", "payment_status": payment_status}},
        })
        timestamp = int(time.time()) if timestamp is None else timestamp
        signature = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()

        # Changing the body after signing it, like an attacker editing a real message
        if tamper:
            body = body.replace('"paid"', '"paid" ')

        return client.post(
            "/stripe/webhook",
            data=body,
            headers={"Stripe-Signature": f"t={timestamp},v1={signature}", "Content-Type": "application/json"},
        )
    return send


@pytest.fixture
def unpaid_order(place_order, price_id, latest_order):
    # An order that went to Stripe but whose customer never came back to the confirmation page
    place_order(name="Closed The Tab", **{f"qty_{price_id('002')}": "1"})
    return latest_order()


def order_status(query):
    return query("SELECT status FROM orders")[0][0]


# ---------- Real payments ----------

def test_paid_checkout_marks_the_order_paid(send_webhook, unpaid_order, query):
    response = send_webhook("checkout.session.completed", unpaid_order.session_id)

    assert response.status_code == 200
    assert order_status(query) == "pending"


def test_webhook_paid_order_shows_up_for_the_kitchen(client, admin_auth, send_webhook, unpaid_order):
    send_webhook("checkout.session.completed", unpaid_order.session_id)
    html = client.get("/admin", auth=admin_auth).get_data(as_text=True)

    assert "Closed The Tab" in html


def test_delayed_payment_success_marks_the_order_paid(send_webhook, unpaid_order, query):
    send_webhook("checkout.session.async_payment_succeeded", unpaid_order.session_id)
    assert order_status(query) == "pending"


def test_duplicate_messages_are_harmless(send_webhook, unpaid_order, query):
    first = send_webhook("checkout.session.completed", unpaid_order.session_id)
    second = send_webhook("checkout.session.completed", unpaid_order.session_id)

    assert (first.status_code, second.status_code) == (200, 200)
    assert order_status(query) == "pending"


def test_webhook_does_not_undo_a_completed_order(client, admin_auth, send_webhook, unpaid_order, query):
    send_webhook("checkout.session.completed", unpaid_order.session_id)
    client.post("/admin/orders/1/complete", auth=admin_auth, headers={"Origin": "http://localhost"})
    send_webhook("checkout.session.completed", unpaid_order.session_id)

    assert order_status(query) == "completed"


# ---------- Messages that must not mark anything paid ----------

def test_completed_checkout_that_is_not_paid_is_ignored(send_webhook, unpaid_order, query):
    response = send_webhook("checkout.session.completed", unpaid_order.session_id, payment_status="unpaid")

    assert response.status_code == 200
    assert order_status(query) == "awaiting_payment"


def test_unrelated_event_types_are_ignored(send_webhook, unpaid_order, query):
    response = send_webhook("checkout.session.expired", unpaid_order.session_id)

    assert response.status_code == 200
    assert order_status(query) == "awaiting_payment"


def test_unknown_checkout_session_is_ignored(send_webhook, unpaid_order, query):
    response = send_webhook("checkout.session.completed", "cs_test_someone_else")

    assert response.status_code == 200
    assert order_status(query) == "awaiting_payment"


# ---------- Fake or broken messages ----------

def test_message_signed_with_the_wrong_secret_is_rejected(send_webhook, unpaid_order, query):
    response = send_webhook("checkout.session.completed", unpaid_order.session_id, secret="whsec_attacker_guess")

    assert response.status_code == 400
    assert order_status(query) == "awaiting_payment"


def test_edited_message_is_rejected(send_webhook, unpaid_order, query):
    response = send_webhook("checkout.session.completed", unpaid_order.session_id, tamper=True)

    assert response.status_code == 400
    assert order_status(query) == "awaiting_payment"


def test_old_replayed_message_is_rejected(send_webhook, unpaid_order, query):
    # A genuinely signed message from 10 minutes ago, resent by an attacker who captured it
    response = send_webhook("checkout.session.completed", unpaid_order.session_id, timestamp=int(time.time()) - 600)

    assert response.status_code == 400
    assert order_status(query) == "awaiting_payment"


def test_message_without_a_signature_is_rejected(client, send_webhook, unpaid_order, query):
    response = client.post("/stripe/webhook", data="{}", headers={"Content-Type": "application/json"})

    assert response.status_code == 400
    assert order_status(query) == "awaiting_payment"


def test_webhook_is_off_without_a_signing_secret(client, unpaid_order, query, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    response = client.post("/stripe/webhook", data="{}", headers={"Stripe-Signature": "t=1,v1=abc"})

    assert response.status_code == 503
    assert order_status(query) == "awaiting_payment"


def test_webhook_only_accepts_post(client):
    assert client.get("/stripe/webhook").status_code == 405
