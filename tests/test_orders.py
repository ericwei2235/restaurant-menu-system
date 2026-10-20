import pytest


# ---------- Placing a valid order ----------

def test_valid_order_redirects_to_confirmation(place_order, price_id):
    response = place_order(**{f"qty_{price_id('002')}": "2"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/order/1"


def test_valid_order_is_saved_with_its_items(place_order, price_id, query):
    egg_rolls = price_id("002")
    large_wonton = price_id("020", "Large")
    place_order(name="Eric", phone="630-555-1234", **{f"qty_{egg_rolls}": "2", f"qty_{large_wonton}": "1"})

    assert query("SELECT customer_name, customer_phone, status FROM orders") == [("Eric", "630-555-1234", "pending")]
    assert query("SELECT menu_item_price_id, quantity FROM order_items ORDER BY id") == [(egg_rolls, 2), (large_wonton, 1)]


def test_zero_quantities_are_not_saved(place_order, price_id, query):
    place_order(**{f"qty_{price_id('002')}": "1", f"qty_{price_id('005')}": "0"})
    assert query("SELECT COUNT(*) FROM order_items") == [(1,)]


def test_phone_number_is_optional(place_order, price_id):
    response = place_order(phone="", **{f"qty_{price_id('002')}": "1"})
    assert response.status_code == 302


# ---------- Confirmation page ----------

def test_confirmation_shows_items_and_correct_total(client, place_order, price_id):
    # 2 Egg Rolls at $3.75 = $7.50, plus 1 Large Wonton Soup at $6.75 = $14.25
    place_order(name="Eric", **{f"qty_{price_id('002')}": "2", f"qty_{price_id('020', 'Large')}": "1"})
    html = client.get("/order/1").get_data(as_text=True)

    assert "Thanks, Eric!" in html
    assert "Wonton Soup (Large)" in html
    assert "$7.50" in html
    assert "$14.25" in html


def test_confirmation_for_missing_order_is_404(client):
    assert client.get("/order/999").status_code == 404


def test_order_page_only_accepts_post(client):
    assert client.get("/order").status_code == 405


# ---------- Rejected orders ----------

@pytest.mark.parametrize(
    "name, phone, quantity_key, quantity",
    [
        ("", "", "valid", "1"),               # missing name
        ("   ", "", "valid", "1"),            # name is only spaces
        ("x" * 101, "", "valid", "1"),        # name too long
        ("Eric", "1" * 31, "valid", "1"),     # phone too long
        ("Eric", "", "valid", "0"),           # nothing ordered
        ("Eric", "", "valid", "-3"),          # negative quantity counts as nothing ordered
        ("Eric", "", "valid", "21"),          # over the 20-per-item limit
        ("Eric", "", "valid", "abc"),         # quantity isn't a number
        ("Eric", "", "qty_abc", "1"),         # price id isn't a number
        ("Eric", "", "qty_99999", "1"),       # price id doesn't exist
    ],
)
def test_invalid_orders_are_rejected_and_not_saved(place_order, price_id, query, name, phone, quantity_key, quantity):
    key = f"qty_{price_id('002')}" if quantity_key == "valid" else quantity_key
    response = place_order(name=name, phone=phone, **{key: quantity})

    assert response.status_code == 400
    assert query("SELECT COUNT(*) FROM orders") == [(0,)]
    assert query("SELECT COUNT(*) FROM order_items") == [(0,)]


def test_one_bad_item_rolls_back_the_whole_order(place_order, price_id, query):
    # A valid item plus a nonexistent one: the transaction must undo the order row too
    response = place_order(**{f"qty_{price_id('002')}": "1", "qty_99999": "1"})

    assert response.status_code == 400
    assert query("SELECT COUNT(*) FROM orders") == [(0,)]
    assert query("SELECT COUNT(*) FROM order_items") == [(0,)]


def test_sql_injection_in_name_is_stored_as_plain_text(place_order, price_id, query):
    attack = "x'); DROP TABLE orders; --"
    response = place_order(name=attack, **{f"qty_{price_id('002')}": "1"})

    assert response.status_code == 302
    # The orders table still exists and holds the text exactly as typed
    assert query("SELECT customer_name FROM orders") == [(attack,)]
