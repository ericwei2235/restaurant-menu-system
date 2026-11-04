import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../api.js'
import { formatCents } from '../money.js'
import { formatOrderTime } from '../time.js'

// How often the dashboard checks for new orders on its own
const REFRESH_MS = 30000

// The admin page decides between the login form and the dashboard
function AdminPage() {
  // checked: whether we've asked the server yet; username: who's logged in (null if nobody)
  const [login, setLogin] = useState({ checked: false, username: null })
  // A message shown above the login form, e.g. after a login expires
  const [notice, setNotice] = useState(null)

  useEffect(() => {
    document.title = 'Admin | China Chef'
    return () => {
      document.title = 'China Chef'
    }
  }, [])

  // On arrival, ask the server whether this browser already has a login session (the cookie is sent automatically)
  useEffect(() => {
    let ignore = false
    apiRequest('/api/admin/session')
      .then((data) => {
        if (!ignore) setLogin({ checked: true, username: data.logged_in ? data.username : null })
      })
      .catch(() => {
        if (!ignore) setLogin({ checked: true, username: null })
      })
    return () => {
      ignore = true
    }
  }, [])

  // useCallback keeps this the same function between redraws. The dashboard's refresh timer depends on it,
  // and a brand-new function every redraw would make that timer restart over and over
  const handleLoggedOut = useCallback((message = null) => {
    setLogin({ checked: true, username: null })
    setNotice(message)
  }, [])

  function handleLoggedIn(username) {
    setLogin({ checked: true, username })
    setNotice(null)
  }

  if (!login.checked) {
    return <p className="loading">Loading...</p>
  }

  if (login.username) {
    return <Dashboard username={login.username} onLoggedOut={handleLoggedOut} />
  }

  return <LoginForm notice={notice} onLoggedIn={handleLoggedIn} />
}

function LoginForm({ notice, onLoggedIn }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      // On success the server sets the login cookie; the browser stores and resends it automatically
      const data = await apiRequest('/api/admin/login', { method: 'POST', body: { username, password } })
      onLoggedIn(data.username)
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <section className="admin-login">
      <h2>Staff login</h2>
      {notice && <p className="notice">{notice}</p>}

      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="username">Username</label>
          <input
            id="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            autoFocus
          />
        </div>

        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}

        <button type="submit" disabled={submitting}>
          {submitting ? 'Logging in...' : 'Log in'}
        </button>
      </form>
    </section>
  )
}

function Dashboard({ username, onLoggedOut }) {
  const [orders, setOrders] = useState(null)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  // Bumping this number reloads the orders right away (used after marking one complete)
  const [reloadCount, setReloadCount] = useState(0)
  // The order number currently being marked complete, so only its button shows as busy
  const [completing, setCompleting] = useState(null)

  // Load the orders now, then again every REFRESH_MS, so new orders appear without refreshing the page
  useEffect(() => {
    let ignore = false

    function load() {
      apiRequest('/api/admin/orders')
        .then((data) => {
          if (ignore) return
          setOrders(data)
          setError(null)
          setLastUpdated(new Date())
        })
        .catch((err) => {
          if (ignore) return
          // 401 means the 12-hour login ran out (or the server restarted with a new key)
          if (err.status === 401) {
            onLoggedOut('Your login has expired. Please log in again.')
          } else {
            setError(err.message)
          }
        })
    }

    load()
    const timer = setInterval(load, REFRESH_MS)

    // Stop the timer when leaving the page or before restarting it
    return () => {
      ignore = true
      clearInterval(timer)
    }
  }, [reloadCount, onLoggedOut])

  async function markComplete(orderNumber) {
    setCompleting(orderNumber)
    setError(null)
    try {
      await apiRequest(`/api/admin/orders/${orderNumber}/complete`, { method: 'POST' })
      setReloadCount((count) => count + 1)
    } catch (err) {
      if (err.status === 401) {
        onLoggedOut('Your login has expired. Please log in again.')
      } else {
        setError(err.message)
      }
    } finally {
      setCompleting(null)
    }
  }

  async function logOut() {
    try {
      await apiRequest('/api/admin/logout', { method: 'POST' })
    } finally {
      // Show the login form even if the request failed; the session ends on its own after 12 hours anyway
      onLoggedOut()
    }
  }

  return (
    <>
      <div className="admin-bar">
        <span>
          Logged in as <strong>{username}</strong>
          {lastUpdated && (
            <span className="updated"> · updated {lastUpdated.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</span>
          )}
        </span>
        <button type="button" className="secondary-button" onClick={logOut}>
          Log out
        </button>
      </div>

      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      {!orders ? (
        <p className="loading">Loading orders...</p>
      ) : (
        <>
          <section>
            <h3>Pending orders ({orders.pending.length})</h3>
            {orders.pending.length === 0 && <p className="empty">No pending orders.</p>}
            {orders.pending.map((order) => (
              <OrderCard
                key={order.order_number}
                order={order}
                busy={completing === order.order_number}
                onComplete={markComplete}
              />
            ))}
          </section>

          <section>
            <h3>Recently completed</h3>
            {orders.completed.length === 0 && <p className="empty">No completed orders yet.</p>}
            {orders.completed.map((order) => (
              <OrderCard key={order.order_number} order={order} />
            ))}
          </section>
        </>
      )}
    </>
  )
}

// One order's card. Used for both lists; only pending orders get the "Mark complete" button
function OrderCard({ order, busy = false, onComplete }) {
  return (
    <article className={`order-card ${order.status}`}>
      <div className="order-header">
        <span className="order-number">#{order.order_number}</span>
        <span className="order-time">{formatOrderTime(order.created_at)}</span>
      </div>

      <p className="order-customer">
        <strong>{order.customer_name}</strong>
        {/* tel: links let staff tap the number to call it from a phone */}
        {order.customer_phone && (
          <>
            {' · '}
            <a href={`tel:${order.customer_phone}`}>{order.customer_phone}</a>
          </>
        )}
      </p>

      <ul className="order-lines">
        {order.lines.map((line, index) => (
          <li key={index}>
            <span>
              {line.quantity} &times; {line.name}
              {line.size && ` (${line.size})`}
            </span>
            <span>{formatCents(line.line_total_cents)}</span>
          </li>
        ))}
      </ul>

      <div className="order-footer">
        <strong>Total: {formatCents(order.total_cents)}</strong>
        {order.status === 'pending' ? (
          <button type="button" disabled={busy} onClick={() => onComplete(order.order_number)}>
            {busy ? 'Saving...' : 'Mark complete'}
          </button>
        ) : (
          <span className="status-badge">Completed</span>
        )}
      </div>
    </article>
  )
}

export default AdminPage
