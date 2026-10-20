import os
import sqlite3

import pytest

import app as app_module

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_PASSWORD = "test-password"


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
def client(db_path, monkeypatch):
    # A fake browser that sends requests straight to the app, without running a server
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_PASSWORD)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def admin_auth():
    # Correct admin login, passed as auth=... on requests
    return ("admin", ADMIN_PASSWORD)


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
    # Submit the order form and return the response
    def submit(name="Test Customer", phone="630-555-1234", **quantities):
        data = {"name": name, "phone": phone}
        data.update(quantities)
        return client.post("/order", data=data)
    return submit
