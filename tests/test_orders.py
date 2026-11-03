import re

import pytest


# ---------- Placing a valid order ----------

def test_valid_order_returns_201_with_a_stripe_link(place_order, price_id, latest_order):
    response = place_order(items=[(price_id("002"), 2)])
    order = latest_order()

    assert response.status_code == 201
    assert response.get_json() == {
        "order_number": 1,
        "token": order.token,
        "checkout_url": f"https://checkout.stripe.test/{order.session_id}",
    }


def test_valid_order_is_saved_unpaid_with_its_items(place_order, price_id, query):
    egg_rolls = price_id("002")
    large_wonton = price_id("020", "Large")
    place_order(name="Eric", phone="630-555-1234", items=[(egg_rolls, 2), (large_wonton, 1)])

    assert query("SELECT customer_name, customer_phone, status FROM orders") == [("Eric", "630-555-1234", "awaiting_payment")]
    assert query("SELECT menu_item_price_id, quantity FROM order_items ORDER BY id") == [(egg_rolls, 2), (large_wonton, 1)]


def test_name_and_phone_are_trimmed(place_order, price_id, query):
    place_order(name="  Eric  ", phone="  630-555-1234 ", items=[(price_id("002"), 1)])
    assert query("SELECT customer_name, customer_phone FROM orders") == [("Eric", "630-555-1234")]


@pytest.mark.parametrize("phone", ["", None])
def test_phone_number_is_optional(client, price_id, phone):
    body = {"name": "Eric", "phone": phone, "items": [{"price_id": price_id("002"), "quantity": 1}]}
    assert client.post("/api/orders", json=body).status_code == 201


def test_phone_can_be_left_out_entirely(client, price_id):
    body = {"name": "Eric", "items": [{"price_id": price_id("002"), "quantity": 1}]}
    assert client.post("/api/orders", json=body).status_code == 201


# ---------- Looking up an order ----------

def test_order_lookup_shows_items_and_correct_total(client, place_paid_order, price_id):
    # 2 Egg Rolls at 375 cents = 750, plus 1 Large Wonton Soup at 675 = 1425
    order = place_paid_order(name="Eric", items=[(price_id("002"), 2), (price_id("020", "Large"), 1)])
    data = client.get(order.link).get_json()

    assert data == {
        "order_number": 1,
        "customer_name": "Eric",
        "payment_state": "paid",
        "checkout_url": None,
        "lines": [
            {"name": "Egg Rolls (2)", "size": None, "quantity": 2, "unit_price_cents": 375, "line_total_cents": 750},
            {"name": "Wonton Soup", "size": "Large", "quantity": 1, "unit_price_cents": 675, "line_total_cents": 675},
        ],
        "total_cents": 1425,
    }


def test_unknown_token_is_404(client):
    response = client.get("/api/orders/not-a-real-token")
    assert response.status_code == 404
    assert response.get_json() == {"error": "We couldn't find that order."}


def test_orders_endpoint_only_accepts_post(client):
    assert client.get("/api/orders").status_code == 405


# ---------- Unguessable order links ----------

def test_order_number_alone_does_not_open_the_order(client, place_order, price_id):
    # The guessable style, /api/orders/1, must not work
    place_order(items=[(price_id("002"), 1)])
    assert client.get("/api/orders/1").status_code == 404


def test_order_token_is_long_and_url_safe(place_order, price_id, query):
    place_order(items=[(price_id("002"), 1)])
    token = query("SELECT public_token FROM orders")[0][0]

    # 16 random bytes encode to 22 characters of letters, digits, - and _
    assert re.fullmatch(r"[A-Za-z0-9_-]{22}", token)


def test_every_order_gets_a_different_token(place_order, price_id, query):
    for _ in range(5):
        place_order(items=[(price_id("002"), 1)])
    tokens = [row[0] for row in query("SELECT public_token FROM orders")]

    assert len(set(tokens)) == 5


# ---------- Rejected orders ----------

def valid_items(price_id):
    return [{"price_id": price_id("002"), "quantity": 1}]


@pytest.mark.parametrize(
    "make_body",
    [
        lambda p: {"phone": "", "items": valid_items(p)},                                   # missing name
        lambda p: {"name": "", "items": valid_items(p)},                                    # empty name
        lambda p: {"name": "   ", "items": valid_items(p)},                                 # name is only spaces
        lambda p: {"name": 42, "items": valid_items(p)},                                    # name isn't text
        lambda p: {"name": "x" * 101, "items": valid_items(p)},                             # name too long
        lambda p: {"name": "Eric", "phone": "1" * 31, "items": valid_items(p)},             # phone too long
        lambda p: {"name": "Eric", "phone": 6305551234, "items": valid_items(p)},           # phone isn't text
        lambda p: {"name": "Eric"},                                                         # no items
        lambda p: {"name": "Eric", "items": []},                                            # empty items
        lambda p: {"name": "Eric", "items": "egg rolls"},                                   # items isn't a list
        lambda p: {"name": "Eric", "items": [5]},                                           # item isn't an object
        lambda p: {"name": "Eric", "items": [{"price_id": p("002")}]},                      # missing quantity
        lambda p: {"name": "Eric", "items": [{"price_id": p("002"), "quantity": 0}]},       # zero quantity
        lambda p: {"name": "Eric", "items": [{"price_id": p("002"), "quantity": -3}]},      # negative quantity
        lambda p: {"name": "Eric", "items": [{"price_id": p("002"), "quantity": 21}]},      # over the 20 limit
        lambda p: {"name": "Eric", "items": [{"price_id": p("002"), "quantity": 1.5}]},     # not a whole number
        lambda p: {"name": "Eric", "items": [{"price_id": p("002"), "quantity": "2"}]},     # number sent as text
        lambda p: {"name": "Eric", "items": [{"price_id": p("002"), "quantity": True}]},    # true/false isn't a number
        lambda p: {"name": "Eric", "items": [{"price_id": "abc", "quantity": 1}]},          # price id isn't a number
        lambda p: {"name": "Eric", "items": [{"price_id": 99999, "quantity": 1}]},          # price id doesn't exist
        lambda p: {"name": "Eric", "items": [{"price_id": p("002"), "quantity": 1},
                                             {"price_id": p("002"), "quantity": 2}]},       # same item listed twice
        lambda p: ["not", "an", "object"],                                                  # body is a list
    ],
)
def test_invalid_orders_are_rejected_and_not_saved(client, price_id, query, fake_stripe, make_body):
    response = client.post("/api/orders", json=make_body(price_id))

    assert response.status_code == 400
    assert "error" in response.get_json()
    assert query("SELECT COUNT(*) FROM orders") == [(0,)]
    assert query("SELECT COUNT(*) FROM order_items") == [(0,)]
    # A rejected order must never reach the payment step
    assert fake_stripe.created == []


def test_non_json_body_is_rejected_with_415(client, query):
    response = client.post("/api/orders", data={"name": "Eric"})

    assert response.status_code == 415
    assert query("SELECT COUNT(*) FROM orders") == [(0,)]


def test_broken_json_is_rejected(client, query):
    response = client.post("/api/orders", data="{not valid json", content_type="application/json")

    assert response.status_code == 400
    assert query("SELECT COUNT(*) FROM orders") == [(0,)]


def test_one_bad_item_rolls_back_the_whole_order(place_order, price_id, query, fake_stripe):
    # A valid item plus a nonexistent one: the transaction must undo the order row too
    response = place_order(items=[(price_id("002"), 1), (99999, 1)])

    assert response.status_code == 400
    assert query("SELECT COUNT(*) FROM orders") == [(0,)]
    assert query("SELECT COUNT(*) FROM order_items") == [(0,)]
    assert fake_stripe.created == []


def test_sql_injection_in_name_is_stored_as_plain_text(place_order, price_id, query):
    attack = "x'); DROP TABLE orders; --"
    response = place_order(name=attack, items=[(price_id("002"), 1)])

    assert response.status_code == 201
    # The orders table still exists and holds the text exactly as typed
    assert query("SELECT customer_name FROM orders") == [(attack,)]
