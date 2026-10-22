from flask import Flask, Response, render_template, request, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import os
import secrets
import sqlite3

import stripe


app = Flask(__name__)

# On Render, a proxy handles HTTPS and passes requests to the app over plain HTTP.
# This trusts the proxy's X-Forwarded-Proto header, so links the app builds for Stripe start with https://
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)

# Build the database path from this file's location, not the terminal's current folder,
# so the app finds restaurant.db no matter where it's launched from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "restaurant.db")

# Limits for order form input, checked on the server since HTML limits can be bypassed
MAX_QUANTITY = 20
MAX_NAME_LENGTH = 100
MAX_PHONE_LENGTH = 30

# The restaurant is in Aurora, IL, so admin times are shown in Central time
RESTAURANT_TIMEZONE = ZoneInfo("America/Chicago")

# Random bytes in each order's confirmation-link token (16 bytes = 128 bits, about 22 characters)
ORDER_TOKEN_BYTES = 16

# How many recently completed orders the admin page shows
COMPLETED_ORDERS_SHOWN = 20

# Stripe amounts are in the smallest currency unit, which for dollars is cents, the same as our database
CURRENCY = "usd"


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


def format_order_time(created_at):
    # SQLite's CURRENT_TIMESTAMP is stored as UTC text like "2026-10-08 18:30:00"
    utc_time = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    # Convert to the restaurant's local time, e.g. "Oct 08, 01:30 PM"
    return utc_time.astimezone(RESTAURANT_TIMEZONE).strftime("%b %d, %I:%M %p")


def build_line(row):
    # Turn one ordered item (name, size_label, price, quantity) into a display-ready line
    # Returns the line and its total in cents, so callers can add up the order total exactly
    line_cents = row["price"] * row["quantity"]
    line = {
        "name": row["name"],
        "size": row["size_label"],
        "quantity": row["quantity"],
        "unit_price": format_price(row["price"]),
        "line_total": format_price(line_cents),
    }
    return line, line_cents


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


def get_order_lines(conn, order_id):
    # Get each line item's name, size, unit price, and quantity for one order
    # order_items -> menu_item_prices (for size and price) -> menu_items (for the name)
    return conn.execute(
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


def order_error(message):
    # Show a friendly error page with a 400 (Bad Request) status instead of a bare line of text
    return render_template("error.html", message=message, back_hint=True), 400


# ---------- Stripe ----------

def get_stripe_client():
    # The Stripe secret key lives in an environment variable, like the admin password
    key = os.environ.get("STRIPE_SECRET_KEY", "")

    # Only test-mode keys are accepted, so this demo can never charge a real card.
    # A missing key or a live key (sk_live_...) both mean payments are switched off
    if not key.startswith("sk_test_"):
        return None

    return stripe.StripeClient(key)


def get_checkout_session(session_id):
    # Ask Stripe directly about a checkout session. Returns None if Stripe can't be reached
    client = get_stripe_client()
    if client is None or session_id is None:
        return None

    try:
        return client.v1.checkout.sessions.retrieve(session_id)
    except stripe.StripeError:
        return None


def mark_order_paid(conn, order_id):
    # Move an order from awaiting payment into the kitchen's pending queue.
    # "AND status = 'awaiting_payment'" makes this safe to run more than once
    with conn:
        conn.execute(
            "UPDATE orders SET status = 'pending' WHERE id = ? AND status = 'awaiting_payment'",
            (order_id,),
        )


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

    # Check that payments are set up before saving anything, so no order is created that can't be paid for
    client = get_stripe_client()
    if client is None:
        return render_template("error.html", message="Online payment isn't set up right now, so orders can't be placed."), 503

    # A long random string that identifies this order in its confirmation link.
    # Order ids count up 1, 2, 3..., so using them in links would let anyone view other people's orders
    public_token = secrets.token_urlsafe(ORDER_TOKEN_BYTES)

    conn = get_db_connection()

    try:
        # Wrap everything in one transaction, roll back if error occurs
        with conn:
            cursor = conn.execute(
                "INSERT INTO orders (customer_name, customer_phone, public_token) VALUES (?, ?, ?)",  # status defaults to 'awaiting_payment', created_at to the current time
                (name, phone, public_token),
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

    # Build Stripe's line items from the database, never from the form, so prices can't be tampered with
    line_items = []
    for row in get_order_lines(conn, order_id):
        label = f"{row['name']} ({row['size_label']})" if row["size_label"] else row["name"]
        line_items.append({
            "price_data": {
                "currency": CURRENCY,
                "unit_amount": row["price"],  # already in cents
                "product_data": {"name": label},
            },
            "quantity": row["quantity"],
        })

    # Stripe sends the customer back to their confirmation page whether they pay or cancel.
    # That page then asks Stripe which one happened, rather than trusting where the browser came from
    order_link = url_for("confirmation", token=public_token, _external=True)

    try:
        session = client.v1.checkout.sessions.create(params={
            "mode": "payment",
            "line_items": line_items,
            "success_url": order_link,
            "cancel_url": order_link,
            # Links the Stripe payment back to this order, for the dashboard and for the webhook later
            "client_reference_id": str(order_id),
            "metadata": {"order_token": public_token},
        })
    except stripe.StripeError:
        # The order stays saved as unpaid, which hides it from the admin page
        conn.close()
        return render_template("error.html", message="We couldn't reach the payment service. Please try again in a moment."), 502

    # Remember which Stripe checkout belongs to this order, so its payment can be checked later
    with conn:
        conn.execute("UPDATE orders SET stripe_session_id = ? WHERE id = ?", (session.id, order_id))
    conn.close()

    # Send the customer to Stripe's payment page.
    # 303 tells the browser to follow up with a GET, the standard redirect after a form POST
    return redirect(session.url, code=303)


@app.route("/order/<token>")
def confirmation(token):
    conn = get_db_connection()

    # Look up the order by its random token, using ? because the token comes from the URL (user input)
    order = conn.execute(
        "SELECT id, customer_name, status, stripe_session_id FROM orders WHERE public_token = ?",
        (token,),
    ).fetchone()

    # No order has that token, so show a 404 (Not Found) page
    if order is None:
        conn.close()
        return render_template("error.html", message="We couldn't find that order."), 404

    # Work out where payment stands: "paid", "open" (not paid yet), "expired", or "unknown"
    checkout_url = None

    if order["status"] != "awaiting_payment":
        # Already confirmed as paid earlier
        payment_state = "paid"
    else:
        # Ask Stripe directly. The browser landing here proves nothing, since anyone can open this link
        session = get_checkout_session(order["stripe_session_id"])

        if session is not None and session.payment_status == "paid":
            mark_order_paid(conn, order["id"])
            payment_state = "paid"
        elif session is not None and session.status == "open":
            # Not paid yet, but the Stripe page still works, so offer a link back to it
            payment_state = "open"
            checkout_url = session.url
        elif session is not None and session.status == "expired":
            payment_state = "expired"
        else:
            # Stripe couldn't be reached, or the payment is still processing
            payment_state = "unknown"

    rows = get_order_lines(conn, order["id"])
    conn.close()

    lines = []
    total_cents = 0

    for row in rows:
        # Do all math in integer cents, then format to dollars only for display
        line, line_cents = build_line(row)
        lines.append(line)
        total_cents += line_cents

    return render_template(
        "confirmation.html",
        order=order,
        lines=lines,
        total=format_price(total_cents),
        payment_state=payment_state,
        checkout_url=checkout_url,
    )


# ---------- Admin ----------

def admin_credentials_valid(auth):
    # The password lives in an environment variable, never in the code
    expected_password = os.environ.get("ADMIN_PASSWORD")
    expected_username = os.environ.get("ADMIN_USERNAME", "admin")

    # No login info sent, or no password configured on the server
    if auth is None or not expected_password:
        return False

    # compare_digest takes the same time whether the first or last character is wrong,
    # so an attacker can't guess the password one character at a time by timing responses
    username_ok = secrets.compare_digest((auth.username or "").encode(), expected_username.encode())
    password_ok = secrets.compare_digest((auth.password or "").encode(), expected_password.encode())
    return username_ok and password_ok


def require_admin(view):
    # A decorator: wraps a route so the login check runs before the route's own code
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        # Fail closed: if no password is configured, the admin page is off rather than open to everyone
        if not os.environ.get("ADMIN_PASSWORD"):
            return render_template("error.html", message="The admin page is disabled because no admin password is set."), 503

        if not admin_credentials_valid(request.authorization):
            # 401 plus this header makes the browser show its built-in username/password popup
            return Response("Login required.", 401, {"WWW-Authenticate": 'Basic realm="China Chef Admin"'})

        return view(*args, **kwargs)

    return wrapped_view


def is_same_origin_request():
    # Browsers send the admin password automatically, even on requests another website triggers.
    # Checking where the request came from blocks other sites from submitting forms to our admin routes
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source:
        return False
    return urlparse(source).netloc == request.host


@app.route("/admin")
@require_admin
def admin():
    conn = get_db_connection()

    # One query for every paid order and its items, newest orders first, items in the order they were added.
    # Unpaid orders (abandoned checkouts) are left out, since the kitchen shouldn't make them
    rows = conn.execute(
        """
        SELECT o.id AS order_id, o.customer_name, o.customer_phone, o.created_at, o.status,
               m.name, p.size_label, p.price, oi.quantity
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN menu_item_prices p ON p.id = oi.menu_item_price_id
        JOIN menu_items m ON m.id = p.menu_item_id
        WHERE o.status IN ('pending', 'completed')
        ORDER BY o.id DESC, oi.id
        """
    ).fetchall()
    conn.close()

    orders = []

    for row in rows:
        line, line_cents = build_line(row)

        # Same grouping idea as get_menu(): rows for one order are next to each other thanks to ORDER BY
        if orders and orders[-1]["id"] == row["order_id"]:
            # Same order as the last row, so just add this item to it
            orders[-1]["lines"].append(line)
            orders[-1]["total_cents"] += line_cents
        else:
            # First row of a new order
            orders.append({
                "id": row["order_id"],
                "customer_name": row["customer_name"],
                "customer_phone": row["customer_phone"],
                "time": format_order_time(row["created_at"]),
                "status": row["status"],
                "lines": [line],
                "total_cents": line_cents,
            })

    # Convert each order total to dollars once all its items have been added
    for order in orders:
        order["total"] = format_price(order["total_cents"])

    # Pending orders oldest first, like a queue; completed orders newest first, only the most recent few
    pending = [order for order in orders if order["status"] == "pending"]
    pending.reverse()
    completed = [order for order in orders if order["status"] == "completed"][:COMPLETED_ORDERS_SHOWN]

    return render_template("admin.html", pending=pending, completed=completed)


@app.route("/admin/orders/<int:order_id>/complete", methods=["POST"])
@require_admin
def complete_order(order_id):
    # Reject the request if it was submitted from some other website
    if not is_same_origin_request():
        return render_template("error.html", message="That request came from somewhere unexpected and was blocked."), 403

    conn = get_db_connection()
    with conn:
        # Only pending orders can be completed; completing one twice does nothing
        conn.execute(
            "UPDATE orders SET status = 'completed' WHERE id = ? AND status = 'pending'",
            (order_id,),
        )
    conn.close()

    # Post/Redirect/Get again, so refreshing the admin page doesn't resend the button press
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True)
