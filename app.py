from flask import Flask, jsonify, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import timedelta
from functools import wraps
from urllib.parse import urlparse
import os
import secrets
import sqlite3

import stripe


app = Flask(__name__)

# On Render, a proxy handles HTTPS and passes requests to the app over plain HTTP.
# This trusts the proxy's X-Forwarded-Proto header, so links the app builds for Stripe start with https://
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)

# The admin login is remembered in a session cookie signed with SECRET_KEY, so it can't be forged.
# Like the other secrets, it comes from an environment variable and is never in the code
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

# Session cookie safety settings:
# HttpOnly: page scripts can't read the cookie, so even injected JavaScript couldn't steal the login
# SameSite=Lax: the browser doesn't attach the cookie to requests other websites send in the background
# Secure: the cookie is only ever sent over HTTPS (switched off below for local development)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = True

# How long an admin stays logged in, about one long restaurant shift
ADMIN_SESSION_LIFETIME = timedelta(hours=12)
app.config["PERMANENT_SESSION_LIFETIME"] = ADMIN_SESSION_LIFETIME

# A SECRET_KEY shorter than this is treated as missing, since short keys can be guessed
MIN_SECRET_KEY_LENGTH = 32

# Build the database path from this file's location, not the terminal's current folder,
# so the app finds restaurant.db no matter where it's launched from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "restaurant.db")

# Limits for order form input, checked on the server since HTML limits can be bypassed
MAX_QUANTITY = 20
MAX_NAME_LENGTH = 100
MAX_PHONE_LENGTH = 30

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


def line_to_json(row):
    # Turn one ordered item (name, size_label, price, quantity) into the API's line format.
    # All money stays in integer cents; the frontend formats it for display
    return {
        "name": row["name"],
        "size": row["size_label"],
        "quantity": row["quantity"],
        "unit_price_cents": row["price"],
        "line_total_cents": row["price"] * row["quantity"],
    }


def api_error(message, status):
    # Every API error has the same shape, so the frontend can show any of them the same way
    return jsonify({"error": message}), status


def is_whole_number(value):
    # True only for real integers. JSON true/false arrive in Python as True/False, which Python
    # counts as the integers 1 and 0, so check the exact type rather than using isinstance
    return type(value) is int


def get_menu():
    # Returns a list of categories, each with its items, each item with its price options

    categories = []

    conn = get_db_connection()
    # Join the menu_items with menu_item_prices
    cursor = conn.execute("SELECT m.name, m.description, m.category, p.id AS price_id, p.size_label, p.price FROM menu_items m JOIN menu_item_prices p ON p.menu_item_id = m.id ORDER BY m.category, m.id")
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        # Start a new category when this row's category differs from the last one
        # (ORDER BY m.category keeps each category's rows together)
        if not categories or categories[-1]["name"] != row["category"]:
            categories.append({"name": row["category"], "items": []})

        items = categories[-1]["items"]
        price = {"id": row["price_id"], "label": row["size_label"], "price_cents": row["price"]}

        # Checks if the last item has the same name as the current row's item
        if items and items[-1]["name"] == row["name"]:
            # If yes, just append this row's size and price to the existing price list
            items[-1]["prices"].append(price)
        else:
            # Otherwise, create a new menu item entry using this row's info
            items.append({"name": row["name"], "description": row["description"], "prices": [price]})

    return categories


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


def get_payment_state(conn, order):
    # Work out where an order's payment stands: "paid", "open" (not paid yet), "expired", or "unknown".
    # Returns the state and, for "open", the link back to Stripe's payment page
    if order["status"] != "awaiting_payment":
        # Already confirmed as paid earlier
        return "paid", None

    # Ask Stripe directly. A customer opening the order link proves nothing, since anyone can open it
    session = get_checkout_session(order["stripe_session_id"])

    if session is not None and session.payment_status == "paid":
        mark_order_paid(conn, order["id"])
        return "paid", None
    if session is not None and session.status == "open":
        # Not paid yet, but the Stripe page still works, so offer a link back to it
        return "open", session.url
    if session is not None and session.status == "expired":
        return "expired", None
    # Stripe couldn't be reached, or the payment is still processing
    return "unknown", None


# ---------- Public API ----------

@app.route("/api/menu")
def api_menu():
    return jsonify({"categories": get_menu()})


@app.route("/api/orders", methods=["POST"])
def api_create_order():
    # The order must arrive as JSON. 415 means "Unsupported Media Type": wrong kind of body
    if not request.is_json:
        return api_error("Send the order as JSON.", 415)

    # silent=True returns None for broken JSON instead of raising an error, so it can be rejected cleanly
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("The order couldn't be read.", 400)

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return api_error("Please enter your name.", 400)
    name = name.strip()
    if len(name) > MAX_NAME_LENGTH:
        return api_error("That name is too long.", 400)

    # Phone is optional, so a missing or null phone becomes an empty string
    phone = data.get("phone") or ""
    if not isinstance(phone, str):
        return api_error("That phone number couldn't be read.", 400)
    phone = phone.strip()
    if len(phone) > MAX_PHONE_LENGTH:
        return api_error("That phone number is too long.", 400)

    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return api_error("Please choose at least one item before placing your order.", 400)

    items = []
    seen_price_ids = set()

    for entry in raw_items:
        # Each item must look like {"price_id": 3, "quantity": 2}
        if not isinstance(entry, dict):
            return api_error("Something was wrong with the order. Please try again.", 400)

        price_id = entry.get("price_id")
        quantity = entry.get("quantity")

        if not is_whole_number(price_id) or not is_whole_number(quantity):
            return api_error("Something was wrong with the order. Please try again.", 400)
        if quantity < 1 or quantity > MAX_QUANTITY:
            return api_error(f"You can order between 1 and {MAX_QUANTITY} of a single item.", 400)

        # JSON allows listing the same item twice, which the old form couldn't; reject it to keep orders clean
        if price_id in seen_price_ids:
            return api_error("Each item can only be listed once.", 400)
        seen_price_ids.add(price_id)

        items.append((price_id, quantity))

    # Check that payments are set up before saving anything, so no order is created that can't be paid for
    client = get_stripe_client()
    if client is None:
        return api_error("Online payment isn't set up right now, so orders can't be placed.", 503)

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
        return api_error("One of the items you chose isn't on the menu.", 400)

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
    # That page then asks Stripe which one happened, rather than trusting where the browser came from.
    # request.host_url is this site's address (e.g. "https://china-chef-demo.onrender.com/");
    # /order/<token> is a page the React app shows
    order_link = f"{request.host_url}order/{public_token}"

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
        # The order stays saved as unpaid, which hides it from the admin page.
        # 502 means "Bad Gateway": a service this server depends on failed
        conn.close()
        return api_error("We couldn't reach the payment service. Please try again in a moment.", 502)

    # Remember which Stripe checkout belongs to this order, so its payment can be checked later
    with conn:
        conn.execute("UPDATE orders SET stripe_session_id = ? WHERE id = ?", (session.id, order_id))
    conn.close()

    # 201 means "Created". The frontend sends the browser to checkout_url itself,
    # instead of the server redirecting like the old HTML form did
    return jsonify({
        "order_number": order_id,
        "token": public_token,
        "checkout_url": session.url,
    }), 201


@app.route("/api/orders/<token>")
def api_get_order(token):
    conn = get_db_connection()

    # Look up the order by its random token, using ? because the token comes from the URL (user input)
    order = conn.execute(
        "SELECT id, customer_name, status, stripe_session_id FROM orders WHERE public_token = ?",
        (token,),
    ).fetchone()

    if order is None:
        conn.close()
        return api_error("We couldn't find that order.", 404)

    payment_state, checkout_url = get_payment_state(conn, order)

    lines = [line_to_json(row) for row in get_order_lines(conn, order["id"])]
    conn.close()

    return jsonify({
        "order_number": order["id"],
        "customer_name": order["customer_name"],
        "payment_state": payment_state,
        "checkout_url": checkout_url,
        "lines": lines,
        # Add up the order total in integer cents, so it's always exact
        "total_cents": sum(line["line_total_cents"] for line in lines),
    })


# ---------- API errors ----------

@app.errorhandler(404)
def not_found(error):
    # Unknown /api/... addresses get a JSON error like every other API response
    # Other addresses keep Flask's default page for now; they'll show the React app later
    if request.path.startswith("/api/"):
        return api_error("Not found.", 404)
    return error


@app.errorhandler(405)
def method_not_allowed(error):
    # e.g. sending GET to an address that only accepts POST.
    # Flask's own response is kept so it includes the "Allow" header listing the accepted methods
    if request.path.startswith("/api/"):
        response = error.get_response()
        response.data = jsonify({"error": "That method isn't allowed here."}).get_data()
        response.content_type = "application/json"
        return response
    return error


@app.errorhandler(500)
def server_error(error):
    # An unexpected crash. Keep the details private and send a plain message instead
    if request.path.startswith("/api/"):
        return api_error("Something went wrong on our end. Please try again.", 500)
    return error


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    # Stripe's servers call this directly when a payment succeeds, so an order is marked paid
    # even if the customer closes the tab before being sent back to their confirmation page

    # Fail closed: without the signing secret, there's no way to tell real messages from fake ones
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret.startswith("whsec_"):
        return "Webhook not configured.", 503

    # The signature is calculated over the exact bytes Stripe sent, so use the raw body, not parsed data
    payload = request.get_data(as_text=True)
    signature = request.headers.get("Stripe-Signature")

    try:
        # Checks the signature with our secret and rejects messages older than 5 minutes,
        # so a fake message, an edited message, or a replayed old one is refused
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except (ValueError, stripe.SignatureVerificationError):
        return "Invalid webhook.", 400

    # Card payments finish as "completed"; slower payment methods finish later as "async_payment_succeeded"
    if event["type"] in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        session = event["data"]["object"]

        if session["payment_status"] == "paid":
            conn = get_db_connection()
            order = conn.execute(
                "SELECT id FROM orders WHERE stripe_session_id = ?",
                (session["id"],),
            ).fetchone()

            # Stripe may send the same message more than once; mark_order_paid is safe to repeat
            if order is not None:
                mark_order_paid(conn, order["id"])
            conn.close()

    # Always answer 200 for messages we've read, or Stripe keeps resending them
    return "", 200


# ---------- Admin ----------

def admin_is_configured():
    # The admin area only works when both secrets are set on the server.
    # A short SECRET_KEY counts as missing, since a guessable key would let anyone forge a login cookie
    secret_key = app.config.get("SECRET_KEY") or ""
    return bool(os.environ.get("ADMIN_PASSWORD")) and len(secret_key) >= MIN_SECRET_KEY_LENGTH


def admin_credentials_valid(username, password):
    # The password lives in an environment variable, never in the code
    expected_password = os.environ.get("ADMIN_PASSWORD", "")
    expected_username = os.environ.get("ADMIN_USERNAME", "admin")

    # compare_digest takes the same time whether the first or last character is wrong,
    # so an attacker can't guess the password one character at a time by timing responses
    username_ok = secrets.compare_digest(username.encode(), expected_username.encode())
    password_ok = secrets.compare_digest(password.encode(), expected_password.encode())
    return username_ok and password_ok


def is_same_origin_request():
    # The browser sends the admin's login cookie automatically, even on requests another website triggers.
    # Checking where the request came from blocks other sites from submitting forms to our admin routes
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source:
        return False
    return urlparse(source).netloc == request.host


def require_same_origin(view):
    # A decorator for admin actions that change something: reject requests that came from other websites
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not is_same_origin_request():
            return api_error("That request came from somewhere unexpected and was blocked.", 403)
        return view(*args, **kwargs)

    return wrapped_view


def require_admin(view):
    # A decorator: wraps a route so the login check runs before the route's own code
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        # Fail closed: if the secrets aren't configured, the admin area is off rather than open to everyone
        if not admin_is_configured():
            return api_error("The admin area is turned off because it isn't configured.", 503)

        # The session cookie is signed with SECRET_KEY, so "admin" can only be in it if this server put it there
        if "admin" not in session:
            return api_error("Please log in.", 401)

        return view(*args, **kwargs)

    return wrapped_view


def to_utc_iso(created_at):
    # SQLite stores CURRENT_TIMESTAMP as UTC text like "2026-10-08 05:27:03".
    # The API sends the standard ISO 8601 form, "2026-10-08T05:27:03Z", where Z means UTC
    return created_at.replace(" ", "T") + "Z"


@app.route("/api/admin/login", methods=["POST"])
@require_same_origin
def api_admin_login():
    if not admin_is_configured():
        return api_error("The admin area is turned off because it isn't configured.", 503)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("Send the username and password as JSON.", 400)

    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return api_error("Send the username and password as JSON.", 400)

    # The same message for a wrong username or a wrong password, so attackers can't learn which usernames exist
    if not admin_credentials_valid(username, password):
        return api_error("Incorrect username or password.", 401)

    # Start a fresh session, then mark it as logged in.
    # permanent=True keeps the login for ADMIN_SESSION_LIFETIME instead of ending when the browser closes
    session.clear()
    session["admin"] = username
    session.permanent = True
    return jsonify({"username": username})


@app.route("/api/admin/logout", methods=["POST"])
@require_same_origin
def api_admin_logout():
    session.clear()
    # 204 means "No Content": it worked and there's nothing to send back
    return "", 204


@app.route("/api/admin/session")
def api_admin_session():
    # Lets the frontend decide whether to show the login form or the dashboard
    if admin_is_configured() and "admin" in session:
        return jsonify({"logged_in": True, "username": session["admin"]})
    return jsonify({"logged_in": False})


@app.route("/api/admin/orders")
@require_admin
def api_admin_orders():
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
        line = line_to_json(row)

        # Same grouping idea as get_menu(): rows for one order are next to each other thanks to ORDER BY
        if orders and orders[-1]["order_number"] == row["order_id"]:
            # Same order as the last row, so just add this item to it
            orders[-1]["lines"].append(line)
            orders[-1]["total_cents"] += line["line_total_cents"]
        else:
            # First row of a new order
            orders.append({
                "order_number": row["order_id"],
                "customer_name": row["customer_name"],
                "customer_phone": row["customer_phone"],
                "created_at": to_utc_iso(row["created_at"]),
                "status": row["status"],
                "lines": [line],
                "total_cents": line["line_total_cents"],
            })

    # Pending orders oldest first, like a queue; completed orders newest first, only the most recent few
    pending = [order for order in orders if order["status"] == "pending"]
    pending.reverse()
    completed = [order for order in orders if order["status"] == "completed"][:COMPLETED_ORDERS_SHOWN]

    return jsonify({"pending": pending, "completed": completed})


@app.route("/api/admin/orders/<int:order_number>/complete", methods=["POST"])
@require_admin
@require_same_origin
def api_admin_complete_order(order_number):
    conn = get_db_connection()

    order = conn.execute("SELECT status FROM orders WHERE id = ?", (order_number,)).fetchone()

    if order is None:
        conn.close()
        return api_error("There's no order with that number.", 404)

    # 409 means "Conflict": the request makes sense, but not for an order in this state
    if order["status"] == "awaiting_payment":
        conn.close()
        return api_error("That order hasn't been paid yet, so it can't be completed.", 409)

    with conn:
        # Only pending orders change; completing an already-completed order does nothing, which is fine
        conn.execute(
            "UPDATE orders SET status = 'completed' WHERE id = ? AND status = 'pending'",
            (order_number,),
        )
    conn.close()

    return jsonify({"order_number": order_number, "status": "completed"})


if __name__ == "__main__":
    # Running "python app.py" means local development over plain http://, where a Secure-only
    # cookie would never be sent back, so logging in couldn't work. In production (gunicorn) this
    # block never runs, so the cookie stays Secure there
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(debug=True)
