from flask import Flask, render_template, request, redirect, url_for
import os
import sqlite3


app = Flask(__name__)

# Build the database path from this file's location, not the terminal's current folder,
# so the app finds restaurant.db no matter where it's launched from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "restaurant.db")

# Limits for order form input, checked on the server since HTML limits can be bypassed
MAX_QUANTITY = 20
MAX_NAME_LENGTH = 100
MAX_PHONE_LENGTH = 30


def get_db_connection():
    # Open a connection with dictionary-style rows and foreign key enforcement turned on
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    # SQLite ignores FOREIGN KEY constraints unless this is set, and it only lasts for this connection
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def format_price(cents):
    # Convert an integer number of cents (e.g. 375) into a dollar string (e.g. "3.75")
    return f"{cents / 100:.2f}"


def get_menu():

    menu = {}

    conn = get_db_connection()
    # Join the menu_items with menu_item_prices
    cursor = conn.execute("SELECT m.name, m.description, m.category, p.id AS price_id, p.size_label, p.price FROM menu_items m JOIN menu_item_prices p ON p.menu_item_id = m.id ORDER BY m.category, m.id")
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        # Creates a category with value of empty list if it doesn't exist already
        if row["category"] not in menu:
            menu[row["category"]] = []

        price = {"id": row["price_id"], "label": row["size_label"], "price": format_price(row["price"])}

        # Checks if the last item has the same name as the current row's item
        if menu[row["category"]] and menu[row["category"]][-1]["name"] == row["name"]:
            # If yes, just append this row's size and price to the existing price list
            menu[row["category"]][-1]["prices"].append(price)
        else:
            # Otherwise, create a new menu item entry using this row's info
            entry = {"name": row["name"], "description": row["description"], "prices": [price]}
            menu[row["category"]].append(entry)

    return menu


def order_error(message):
    # Show a friendly error page with a 400 (Bad Request) status instead of a bare line of text
    return render_template("error.html", message=message, back_hint=True), 400


@app.route("/")
def home():
    menu = get_menu()
    return render_template("menu.html", menu=menu)


@app.route("/order", methods=["POST"])
def place_order():
    name = request.form.get("name", "").strip()

    if not name:
        return order_error("Please enter your name.")
    if len(name) > MAX_NAME_LENGTH:
        return order_error("That name is too long.")

    phone = request.form.get("phone", "").strip()

    if len(phone) > MAX_PHONE_LENGTH:
        return order_error("That phone number is too long.")

    items = []

    for key, value in request.form.items():
        # Skips if the current row is a name or phone number
        if not key.startswith("qty_"):
            continue

        try:
            price_id = int(key[4:])
            quantity = int(value)
        except ValueError:
            # Reject order if id is invalid or quantity isn't a valid number
            return order_error("Something was wrong with the order form. Please try again.")

        # Skip if order is 0 (they didn't order that item)
        if quantity < 1:
            continue
        if quantity > MAX_QUANTITY:
            return order_error(f"You can order at most {MAX_QUANTITY} of a single item.")

        items.append((price_id, quantity))

    if not items:
        return order_error("Please choose at least one item before placing your order.")

    conn = get_db_connection()

    try:
        # Wrap everything in one transaction, roll back if error occurs
        with conn:
            cursor = conn.execute(
                "INSERT INTO orders (customer_name, customer_phone) VALUES (?, ?)",  # status and created_at have default values, so not included here
                (name, phone),
            )

            order_id = cursor.lastrowid  # Points back to this specific order
            for price_id, quantity in items:
                conn.execute(
                    "INSERT INTO order_items (order_id, menu_item_price_id, quantity) VALUES (?, ?, ?)",
                    (order_id, price_id, quantity),
                )

    # Exit in case of foreign key violation (a price id that doesn't exist)
    except sqlite3.IntegrityError:
        conn.close()
        return order_error("One of the items you chose isn't on the menu.")

    conn.close()

    # Post/Redirect/Get: send the browser to the confirmation page so a refresh can't resubmit the order
    return redirect(url_for("confirmation", order_id=order_id))


@app.route("/order/<int:order_id>")
def confirmation(order_id):
    conn = get_db_connection()

    # Look up the order itself, using ? because order_id comes from the URL (user input)
    order = conn.execute(
        "SELECT id, customer_name, created_at FROM orders WHERE id = ?",
        (order_id,),
    ).fetchone()

    # No order with that id exists, so show a 404 (Not Found) page
    if order is None:
        conn.close()
        return render_template("error.html", message="We couldn't find that order."), 404

    # Get each line item's name, size, unit price, and quantity
    # order_items -> menu_item_prices (for size and price) -> menu_items (for the name)
    rows = conn.execute(
        """
        SELECT m.name, p.size_label, p.price, oi.quantity
        FROM order_items oi
        JOIN menu_item_prices p ON p.id = oi.menu_item_price_id
        JOIN menu_items m ON m.id = p.menu_item_id
        WHERE oi.order_id = ?
        ORDER BY oi.id
        """,
        (order_id,),
    ).fetchall()
    conn.close()

    lines = []
    total_cents = 0

    for row in rows:
        # Do all math in integer cents, then format to dollars only for display
        line_cents = row["price"] * row["quantity"]
        total_cents += line_cents
        lines.append({
            "name": row["name"],
            "size": row["size_label"],
            "quantity": row["quantity"],
            "unit_price": format_price(row["price"]),
            "line_total": format_price(line_cents),
        })

    return render_template("confirmation.html", order=order, lines=lines, total=format_price(total_cents))


if __name__ == "__main__":
    app.run(debug=True)
