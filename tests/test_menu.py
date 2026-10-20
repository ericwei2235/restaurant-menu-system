import app as app_module


# ---------- Helper functions ----------

def test_format_price_converts_cents_to_dollars():
    assert app_module.format_price(375) == "3.75"
    assert app_module.format_price(1000) == "10.00"
    assert app_module.format_price(5) == "0.05"


def test_format_order_time_converts_utc_to_central_daylight_time():
    # October is daylight saving time, so Chicago is UTC-5
    assert app_module.format_order_time("2026-10-08 05:27:03") == "Oct 08, 12:27 AM"


def test_format_order_time_converts_utc_to_central_standard_time():
    # January is standard time, so Chicago is UTC-6
    assert app_module.format_order_time("2026-01-15 18:00:00") == "Jan 15, 12:00 PM"


# ---------- get_menu() grouping ----------

def test_get_menu_groups_items_by_category(db_path):
    menu = app_module.get_menu()
    assert set(menu.keys()) == {"Appetizers", "Beef", "Fried Rice", "Poultry", "Soup"}
    assert len(menu["Soup"]) == 3


def test_get_menu_groups_each_items_sizes_together(db_path):
    menu = app_module.get_menu()
    wonton = next(item for item in menu["Soup"] if item["name"] == "Wonton Soup")
    assert [(p["label"], p["price"]) for p in wonton["prices"]] == [("Small", "4.25"), ("Large", "6.75")]


def test_get_menu_lists_each_item_once(db_path):
    menu = app_module.get_menu()
    names = [item["name"] for items in menu.values() for item in items]
    assert len(names) == 18
    assert len(set(names)) == 18


def test_every_price_option_has_a_unique_id(db_path):
    menu = app_module.get_menu()
    ids = [p["id"] for items in menu.values() for item in items for p in item["prices"]]
    assert len(ids) == 35
    assert len(set(ids)) == 35


# ---------- Menu page ----------

def test_menu_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Egg Rolls (2)" in html
    assert "$3.75" in html


def test_menu_page_has_one_quantity_box_per_price_option(client):
    html = client.get("/").get_data(as_text=True)
    assert html.count('name="qty_') == 35


def test_menu_page_shows_demo_warning(client):
    html = client.get("/").get_data(as_text=True)
    assert "not sent to the restaurant" in html
