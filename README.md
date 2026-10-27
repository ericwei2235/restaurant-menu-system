# China Chef — Online Ordering Menu System

A full-stack ordering site for my family's restaurant. The structure includes customers browsing a database-driven menu, placing orders, and paying through Stripe, and staff managing incoming orders from a password-protected admin page.

**Live demo:** https://china-chef-demo.onrender.com/

> This is a portfolio project modeled on my family's restaurant. Orders placed on the demo are **not** sent to the restaurant. Payments run in Stripe's test mode, so no real money is charged: pay with the test card `4242 4242 4242 4242`, any future expiration date, and any CVC. The demo runs on a free hosting tier, so the first visit after a period of inactivity can take up to a minute to load.

## Features

- **Menu from a database.** Items, descriptions, and prices are stored in SQLite and rendered with Jinja2 templates. Items can have a single price or several sizes (Small / Large / Extra Large).
- **Online ordering.** Customers choose quantities for any item or size, enter their name and phone number, and get a confirmation page with line items and an order total.
- **Online payment.** Checkout runs through Stripe's hosted payment page, so card details never touch this server. An order only reaches the kitchen once Stripe confirms it was paid. If a customer leaves the payment page early, their confirmation page offers a link back to finish paying.
- **Admin dashboard.** A password-protected page lists paid, pending orders (oldest first, like a kitchen queue) and recently completed ones, with times shown in the restaurant's local time. Staff mark orders complete with one click, and the page refreshes itself every 30 seconds.
- **Input validation and friendly errors.** Every form value is rechecked on the server, and problems are shown on a styled error page rather than as a crash.
- **Responsive layout.** Works on phones as well as desktops.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Templates | Jinja2 (with template inheritance and macros) |
| Database | SQLite, accessed with raw SQL through Python's `sqlite3` module (no ORM) |
| Payments | Stripe Checkout (test mode) and Stripe webhooks |
| Testing | pytest |
| Frontend | HTML, CSS (no JavaScript) |
| Deployment | Render, served by gunicorn |

## Database schema

```mermaid
erDiagram
    menu_items ||--|{ menu_item_prices : "has one or more"
    orders ||--|{ order_items : contains
    menu_item_prices ||--o{ order_items : "ordered as"

    menu_items {
        INTEGER id PK
        TEXT item_number
        TEXT name
        TEXT description
        TEXT category
    }
    menu_item_prices {
        INTEGER id PK
        INTEGER menu_item_id FK
        TEXT size_label
        INTEGER price "cents"
    }
    orders {
        INTEGER id PK
        TEXT customer_name
        TEXT customer_phone
        TEXT public_token UK "random, used in links"
        TEXT stripe_session_id UK
        TEXT created_at "UTC"
        TEXT status "awaiting_payment, pending, completed"
    }
    order_items {
        INTEGER id PK
        INTEGER order_id FK
        INTEGER menu_item_price_id FK
        INTEGER quantity
    }
```

- `menu_item_prices` is separate from `menu_items` because items have different numbers of sizes (one price, Small/Large, or Small/Large/Extra Large). Each size is just another row.
- `order_items` is a junction table resolving the many-to-many relationship between orders and the specific item-and-size that was ordered.
- An order's `status` moves from `awaiting_payment` to `pending` (paid, waiting for the kitchen) to `completed`. A `CHECK` constraint rejects any other value.

## How payment works

```mermaid
sequenceDiagram
    actor Customer
    participant App as Flask app
    participant Stripe

    Customer->>App: Submit order form (item IDs and quantities)
    App->>App: Validate, save order as awaiting_payment
    App->>Stripe: Create checkout session (prices from the database)
    App-->>Customer: Redirect to Stripe's payment page
    Customer->>Stripe: Pay with card
    par Customer returns
        Stripe-->>Customer: Redirect to the order's confirmation link
        Customer->>App: Open confirmation page
        App->>Stripe: Was this session paid?
        Stripe-->>App: Yes
    and Stripe notifies the server directly
        Stripe->>App: Signed webhook: checkout.session.completed
    end
    App->>App: Mark order paid (pending), visible to the kitchen
```

Payment is confirmed two independent ways. Whichever arrives first marks the order paid, and the other changes nothing. The webhook covers customers who close the tab before being sent back.

## Technical highlights

- **SQL injection prevention.** Every query that includes user input uses parameterized `?` placeholders, so input is always treated as data and never as SQL. Tested by submitting a name containing `DROP TABLE`, where it was stored as plain text.
- **Money stored as integer cents.** Prices are integers (`375` = $3.75) to avoid floating-point rounding errors when adding up order totals. They're converted to dollars only for display.
- **The server never trusts the browser.** The order form sends only item IDs and quantities, and the server looks up prices itself, so prices can't be tampered with. Quantities, lengths, and item IDs are validated on the server, and foreign key constraints reject nonexistent items.
- **Orders saved in a single transaction.** An order and all its line items are written together; if any part fails, nothing is saved.
- **Post/Redirect/Get.** After an order is placed, the browser is redirected to the confirmation page, so refreshing can't create a duplicate order.
- **Payment is verified with Stripe, never assumed.** Reaching the confirmation page proves nothing, since anyone can open a link, so the server asks Stripe directly whether the checkout was paid. Prices sent to Stripe come from the database in cents, never from the form.
- **Signed webhooks.** The webhook rejects any message without a valid Stripe signature (an HMAC of the message and its timestamp), so forged, edited, or replayed messages are refused. Repeated deliveries are harmless because marking an order paid only changes orders that are still unpaid.
- **Test mode only.** The app only accepts Stripe test keys (`sk_test_...`). With a missing or live key, ordering is switched off, so the demo can never charge a real card.
- **Unguessable order links.** Confirmation pages are addressed by a random 128-bit token (`/order/k3J9x...`) rather than the order number, so customers can't view each other's orders by changing a number in the URL.
- **Admin security.** HTTP Basic Auth with the password kept in an environment variable, never in the code; the page is disabled entirely if no password is set; credentials are compared in constant time; and the "mark complete" action rejects requests coming from other websites (CSRF protection).
- **Timestamps in UTC,** converted to Central time only when displayed.

## Running locally

Requires Python 3.9 or newer.

```bash
git clone https://github.com/ericwei2235/restaurant-menu-system.git
cd restaurant-menu-system

python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
python init_db.py          # creates restaurant.db from schema.sql and seed.sql
```

Set an admin password and a Stripe **test** secret key (from your Stripe dashboard in test mode, under Developers → API keys), then start the app:

```bash
# Windows (PowerShell):
$env:ADMIN_PASSWORD = "choose-a-password"
$env:STRIPE_SECRET_KEY = "sk_test_..."
# macOS / Linux:
export ADMIN_PASSWORD="choose-a-password"
export STRIPE_SECRET_KEY="sk_test_..."

python app.py
```

Then open http://127.0.0.1:5000 for the menu, or http://127.0.0.1:5000/admin for the admin page (username `admin`). Without `ADMIN_PASSWORD`, the admin page stays disabled; without a test-mode `STRIPE_SECRET_KEY`, ordering is turned off.

Locally, payments are confirmed when you return to the confirmation page. To also receive webhooks on your own machine, use the [Stripe CLI](https://docs.stripe.com/stripe-cli): `stripe listen --forward-to localhost:5000/stripe/webhook` prints a temporary signing secret to set as `STRIPE_WEBHOOK_SECRET`.

To reset all data, stop the app, delete `restaurant.db`, and run `python init_db.py` again.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

The 84 tests use a fresh temporary database for every test, so they never touch `restaurant.db`, and a fake Stripe client, so they never contact Stripe or need a key. They cover the menu, placing orders, input validation (including SQL injection and price IDs that don't exist), transaction rollback, payment confirmation (paid, unpaid, expired, and Stripe being unreachable), webhook signature checks (forged, edited, and replayed messages), admin login, and the cross-site request check.

## Project structure

```
app.py              Flask routes, database access, validation, payments, webhook, admin authentication
init_db.py          Builds restaurant.db from the SQL files
schema.sql          Table definitions
seed.sql            Menu items and prices
requirements.txt    Python dependencies
requirements-dev.txt  Extra development dependencies (pytest)
pytest.ini          Test settings
tests/              Automated tests
templates/
  base.html         Shared layout (header, footer, stylesheet)
  menu.html         Menu and order form
  confirmation.html Order confirmation
  admin.html        Admin dashboard
  error.html        Error page
static/
  style.css         Styles
```

## Deployment

Hosted on Render's free tier:

- **Build command:** `pip install -r requirements.txt && python init_db.py`
- **Start command:** `gunicorn app:app`
- **Environment variables:** `ADMIN_PASSWORD`, `STRIPE_SECRET_KEY` (test mode), `STRIPE_WEBHOOK_SECRET`
- **Stripe webhook:** a destination pointing at `https://china-chef-demo.onrender.com/stripe/webhook`, sending `checkout.session.completed` and `checkout.session.async_payment_succeeded` events with snapshot payloads

The database is rebuilt from the SQL files on every deploy. Because the free tier's filesystem isn't persistent, orders are cleared whenever the service redeploys or restarts after being idle. The menu is always available.

## Known limitations

- Orders don't persist long-term on the free hosting tier (see Deployment).
- The menu contains a representative subset of the restaurant's real menu, not the full menu.

## Roadmap

- ~~**v1.5:** Online payments using Stripe in test mode.~~ Done.
- **v2:** A React frontend backed by a Flask REST API.
- Persistent order storage that survives redeploys.
