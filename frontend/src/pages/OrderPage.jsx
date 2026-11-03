import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { apiRequest } from '../api.js'
import { formatCents } from '../money.js'

// When Stripe can't confirm a payment yet, check again automatically this many times, this far apart
const MAX_RECHECKS = 5
const RECHECK_DELAY_MS = 3000

function OrderPage() {
  // useParams reads the ":token" part of the address /order/:token
  const { token } = useParams()

  // When only the token changes, React would normally reuse this page and keep the previous order's
  // state. A different key makes React start a fresh OrderDetails instead, so nothing carries over
  return <OrderDetails key={token} token={token} />
}

function OrderDetails({ token }) {
  const [order, setOrder] = useState(null)
  const [error, setError] = useState(null)
  // How many times the order has been loaded; changing it makes the effect below run again
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let ignore = false
    let timer = null

    // Asking the API also makes the server check with Stripe, so this is how payment gets confirmed
    apiRequest(`/api/orders/${token}`)
      .then((data) => {
        if (ignore) return
        setOrder(data)
        setError(null)

        // Payment still unconfirmed (Stripe busy or payment processing): try again shortly
        if (data.payment_state === 'unknown' && attempt < MAX_RECHECKS) {
          timer = setTimeout(() => setAttempt((count) => count + 1), RECHECK_DELAY_MS)
        }
      })
      .catch((err) => {
        if (!ignore) setError(err)
      })

    // Runs when the page goes away or before the effect runs again: stop any waiting re-check
    return () => {
      ignore = true
      clearTimeout(timer)
    }
  }, [token, attempt])

  // Show the order number in the browser tab once it's known
  useEffect(() => {
    if (order) document.title = `Order #${order.order_number} | China Chef`
    return () => {
      document.title = 'China Chef'
    }
  }, [order])

  if (error) {
    return (
      <section className="error-page">
        <h2>Sorry!</h2>
        <p>{error.status === 404 ? "We couldn't find that order." : error.message}</p>
        <p>
          <Link className="button-link" to="/">
            Back to menu
          </Link>
        </p>
      </section>
    )
  }

  if (!order) {
    return <p className="loading">Loading your order...</p>
  }

  const stillChecking = order.payment_state === 'unknown' && attempt < MAX_RECHECKS

  return (
    <section className="confirmation">
      {order.payment_state === 'paid' && (
        <>
          <h2>Thanks, {order.customer_name}!</h2>
          <p>
            Your order number is <strong>#{order.order_number}</strong>.{' '}
            <span className="paid-badge">Payment received</span>
          </p>
        </>
      )}

      {order.payment_state === 'open' && (
        // The customer left Stripe's page without paying, but it can still be finished
        <>
          <h2>Almost done, {order.customer_name}</h2>
          <p>
            Your order <strong>#{order.order_number}</strong> isn&apos;t paid yet, so it hasn&apos;t been sent to the
            kitchen.
          </p>
          <p>
            {/* A plain link, not <Link>, because Stripe's page is on another website */}
            <a className="button-link" href={order.checkout_url}>
              Complete payment
            </a>
          </p>
        </>
      )}

      {order.payment_state === 'expired' && (
        <>
          <h2>This order wasn&apos;t paid</h2>
          <p>
            The payment page for order <strong>#{order.order_number}</strong> has expired, so the order was not
            placed. Please start a new order.
          </p>
        </>
      )}

      {order.payment_state === 'unknown' && (
        // role="status" lets screen readers announce the update without interrupting
        <div role="status">
          <h2>Checking your payment</h2>
          <p>
            {stillChecking
              ? `We're confirming the payment for order #${order.order_number}. This page will update on its own.`
              : `We couldn't confirm the payment for order #${order.order_number} yet. Please refresh this page in a moment.`}
          </p>
        </div>
      )}

      {/* One row per item ordered, plus the order total at the bottom */}
      <table className="order-table">
        <thead>
          <tr>
            <th>Item</th>
            <th>Qty</th>
            <th>Price</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {order.lines.map((line, index) => (
            <tr key={index}>
              <td>
                {line.name}
                {line.size && ` (${line.size})`}
              </td>
              <td>{line.quantity}</td>
              <td>{formatCents(line.unit_price_cents)}</td>
              <td>{formatCents(line.line_total_cents)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan="3">Order total</td>
            <td>{formatCents(order.total_cents)}</td>
          </tr>
        </tfoot>
      </table>

      <p>
        <Link className="button-link" to="/">
          Back to menu
        </Link>
      </p>
    </section>
  )
}

export default OrderPage
