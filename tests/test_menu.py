import app as app_module


# ---------- get_menu() grouping ----------

def test_get_menu_groups_items_by_category_in_order(db_path):
    categories = app_module.get_menu()
    assert [c["name"] for c in categories] == ["Appetizers", "Beef", "Fried Rice", "Poultry", "Soup"]


def test_get_menu_groups_each_items_sizes_together(db_path):
    soup = next(c for c in app_module.get_menu() if c["name"] == "Soup")
    wonton = next(item for item in soup["items"] if item["name"] == "Wonton Soup")
    assert [(p["label"], p["price_cents"]) for p in wonton["prices"]] == [("Small", 425), ("Large", 675)]


def test_get_menu_lists_each_item_once(db_path):
    names = [item["name"] for c in app_module.get_menu() for item in c["items"]]
    assert len(names) == 18
    assert len(set(names)) == 18


def test_every_price_option_has_a_unique_id(db_path):
    ids = [p["id"] for c in app_module.get_menu() for item in c["items"] for p in item["prices"]]
    assert len(ids) == 35
    assert len(set(ids)) == 35


# ---------- GET /api/menu ----------

def test_menu_endpoint_returns_json(client):
    response = client.get("/api/menu")
    assert response.status_code == 200
    assert response.is_json


def test_menu_endpoint_matches_the_documented_shape(client):
    # The exact first item of the first category, as described in API.md
    first_category = client.get("/api/menu").get_json()["categories"][0]
    assert first_category["name"] == "Appetizers"
    assert first_category["items"][0] == {
        "name": "Egg Rolls (2)",
        "description": "Crispy fried rolls with cabbage and pork",
        "prices": [{"id": first_category["items"][0]["prices"][0]["id"], "label": None, "price_cents": 375}],
    }


def test_menu_prices_are_whole_cents_not_formatted_strings(client):
    categories = client.get("/api/menu").get_json()["categories"]
    prices = [p["price_cents"] for c in categories for item in c["items"] for p in item["prices"]]
    assert all(type(p) is int for p in prices)


# ---------- API errors are JSON ----------

def test_unknown_api_address_returns_json_404(client):
    response = client.get("/api/nothing-here")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Not found."}


def test_wrong_method_on_api_returns_json_405(client):
    response = client.post("/api/menu")
    assert response.status_code == 405
    assert response.get_json() == {"error": "That method isn't allowed here."}
    assert response.headers["Allow"]
