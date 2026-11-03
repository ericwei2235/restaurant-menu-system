# API Reference

The React frontend talks to the Flask backend only through the JSON endpoints below. Flask also serves the built React app itself, so the frontend and API share one address (no cross-origin setup needed).

## Conventions

- **JSON everywhere.** Every `/api/...` response is JSON, including errors. Requests with a body must send `Content-Type: application/json`.
- **Errors** always look like `{"error": "A message that can be shown to the user."}`.
- **Money is integer cents** (fields end in `_cents`, e.g. `375` = $3.75). The API never sends formatted dollar strings; formatting is the frontend's job.
- **Times are ISO 8601 in UTC**, e.g. `"2026-10-08T05:27:03Z"`. The frontend converts them to the restaurant's time zone (America/Chicago) for display.
- **`order_number`** is the order's internal id, shown to customers ("Order #12") and used in admin URLs. **`token`** is the long random string used in customer links; customer endpoints only ever accept the token, never the order number.

## Endpoints at a glance

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/menu` | Anyone | The full menu with prices |
| POST | `/api/orders` | Anyone | Place an order and get a Stripe payment link |
| GET | `/api/orders/<token>` | Anyone with the link | An order's items, total, and payment state |
| POST | `/api/admin/login` | Anyone | Log in as admin |
| POST | `/api/admin/logout` | Admin | Log out |
| GET | `/api/admin/session` | Anyone | Whether the current browser is logged in |
| GET | `/api/admin/orders` | Admin | Paid orders for the kitchen |
| POST | `/api/admin/orders/<order_number>/complete` | Admin | Mark a paid order complete |
| POST | `/stripe/webhook` | Stripe only | Payment notifications (unchanged from v1.5) |

---

## Public endpoints

### `GET /api/menu`

**200 OK**
```json
{
  "categories": [
    {
      "name": "Appetizers",
      "items": [
        {
          "name": "Egg Rolls (2)",
          "description": "Crispy fried rolls with cabbage and pork",
          "prices": [
            {"id": 1, "label": null, "price_cents": 375}
          ]
        }
      ]
    },
    {
      "name": "Soup",
      "items": [
        {
          "name": "Wonton Soup",
          "description": "Pork-filled wontons in a savory broth",
          "prices": [
            {"id": 2, "label": "Small", "price_cents": 425},
            {"id": 3, "label": "Large", "price_cents": 675}
          ]
        }
      ]
    }
  ]
}
```
- Categories are a list (not an object keyed by name) so their order is explicit.
- `label` is `null` for single-price items.
- `id` is the price option's id: it's what an order refers to.

### `POST /api/orders`

**Request**
```json
{
  "name": "Eric",
  "phone": "630-555-1234",
  "items": [
    {"price_id": 1, "quantity": 2},
    {"price_id": 3, "quantity": 1}
  ]
}
```
- `name`: required, 1–100 characters after trimming spaces.
- `phone`: optional, up to 30 characters.
- `items`: at least one entry. Each `price_id` must exist and appear only once; each `quantity` must be a whole number from 1 to 20. Only chosen items are sent (no zero quantities).
- Prices are never sent. The server looks them up.

**201 Created**
```json
{
  "order_number": 12,
  "token": "k3J9xQ_m2vLpA8rT0bZcWe",
  "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_..."
}
```
The frontend then sends the browser to `checkout_url`. After paying or cancelling, Stripe returns the customer to `/order/<token>`.

**Errors**

| Status | When |
|---|---|
| 400 | Invalid body or any validation failure (message explains which) |
| 415 | Body isn't JSON |
| 502 | Stripe couldn't be reached; the order is saved unpaid and hidden from the kitchen |
| 503 | Payments aren't configured (no test-mode Stripe key); nothing is saved |

### `GET /api/orders/<token>`

**200 OK**
```json
{
  "order_number": 12,
  "customer_name": "Eric",
  "payment_state": "paid",
  "checkout_url": null,
  "lines": [
    {"name": "Egg Rolls (2)", "size": null, "quantity": 2, "unit_price_cents": 375, "line_total_cents": 750},
    {"name": "Wonton Soup", "size": "Large", "quantity": 1, "unit_price_cents": 675, "line_total_cents": 675}
  ],
  "total_cents": 1425
}
```
`payment_state` is one of:

| Value | Meaning | `checkout_url` |
|---|---|---|
| `paid` | Payment confirmed; the order is with the kitchen | `null` |
| `open` | Not paid yet, Stripe's page still works | link back to Stripe |
| `expired` | Stripe's page expired unpaid; the order won't be made | `null` |
| `unknown` | Stripe couldn't be reached or payment is still processing; try again shortly | `null` |

For unpaid orders, this request asks Stripe for the current status and records the payment if it went through. This side effect is safe to repeat: it only ever moves an order from awaiting payment to paid.

**404 Not Found** if no order has that token.

---

## Admin endpoints

Admin access uses a login session. After a successful login, Flask sets a **session cookie** (`HttpOnly`, `SameSite=Lax`, and `Secure` in production) that the browser sends automatically with later requests. The session is signed with the `SECRET_KEY` environment variable, so it can't be forged.

**Cross-site protection:** every admin `POST` (including login and logout) is rejected with **403** unless its `Origin` or `Referer` header shows it came from this site.

**Not configured:** if `ADMIN_PASSWORD` or `SECRET_KEY` is missing, admin endpoints return **503** (fail closed).

### `POST /api/admin/login`

**Request**
```json
{"username": "admin", "password": "..."}
```
**200 OK** `{"username": "admin"}` and sets the session cookie.
**401** `{"error": "Incorrect username or password."}`. The message is the same whether the username or the password was wrong.

### `POST /api/admin/logout`

**204 No Content**. Clears the session.

### `GET /api/admin/session`

**200 OK** `{"logged_in": true, "username": "admin"}` or `{"logged_in": false}`.
Lets the frontend decide whether to show the login form or the dashboard.

### `GET /api/admin/orders`

**200 OK**
```json
{
  "pending": [
    {
      "order_number": 12,
      "customer_name": "Eric",
      "customer_phone": "630-555-1234",
      "created_at": "2026-10-08T05:27:03Z",
      "status": "pending",
      "lines": [
        {"name": "Wonton Soup", "size": "Large", "quantity": 1, "unit_price_cents": 675, "line_total_cents": 675}
      ],
      "total_cents": 675
    }
  ],
  "completed": []
}
```
- Only paid orders appear. `pending` is oldest first (the kitchen queue); `completed` is newest first, at most 20.

**401** if not logged in.

### `POST /api/admin/orders/<order_number>/complete`

No request body.
**200 OK** `{"order_number": 12, "status": "completed"}`. Also returned if the order was already completed, so repeating it is harmless.

| Status | When |
|---|---|
| 401 | Not logged in |
| 403 | Request came from another site |
| 404 | No order with that number |
| 409 | The order hasn't been paid yet, so it can't be completed |

---

## Stripe webhook

### `POST /stripe/webhook`

Unchanged from v1.5, and deliberately kept outside `/api/` so the URL registered in Stripe's dashboard keeps working. Accepts only Stripe-signed `checkout.session.completed` and `checkout.session.async_payment_succeeded` events. See the README's "How payment works" section.

---

## Pages (served by Flask, rendered by React)

Any non-API path returns the React app, which shows the right page for the URL:

| Path | Page |
|---|---|
| `/` | Menu and order form |
| `/order/<token>` | Order confirmation (Stripe returns customers here) |
| `/admin` | Admin login, then the order dashboard |
