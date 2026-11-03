import { useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../api.js'
import { formatCents } from '../money.js'

// Same limits the server enforces (the server checks again, since browsers can be bypassed)
const MAX_QUANTITY = 20
const MAX_NAME_LENGTH = 100
const MAX_PHONE_LENGTH = 30

function MenuPage() {
  // The menu from the API, or an error message if it couldn't load
  const [categories, setCategories] = useState(null)
  const [loadError, setLoadError] = useState(null)

  // How many of each price option the customer wants, e.g. { 1: 2, 3: 1 } (price id -> quantity)
  const [quantities, setQuantities] = useState({})
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')

  // While the order is being sent, the button is disabled so it can't be submitted twice
  const [submitting, setSubmitting] = useState(false)
  const [orderError, setOrderError] = useState(null)

  // Load the menu once, when the page first appears
  useEffect(() => {
    // If the page goes away before the answer arrives, ignore it instead of updating a page that's gone
    let ignore = false

    apiRequest('/api/menu')
      .then((data) => {
        if (!ignore) setCategories(data.categories)
      })
      .catch((error) => {
        if (!ignore) setLoadError(error.message)
      })

    return () => {
      ignore = true
    }
  }, [])

  // A lookup from price id to its details, e.g. 3 -> { itemName: "Wonton Soup", label: "Large", priceCents: 675 }.
  // useMemo rebuilds it only when the menu changes, not on every keystroke
  const priceOptions = useMemo(() => {
    const lookup = {}
    for (const category of categories ?? []) {
      for (const item of category.items) {
        for (const price of item.prices) {
          lookup[price.id] = { itemName: item.name, label: price.label, priceCents: price.price_cents }
        }
      }
    }
    return lookup
  }, [categories])

  // The order so far: one line per chosen option, with its total in cents
  const lines = Object.entries(quantities)
    .filter(([, quantity]) => quantity > 0)
    .map(([priceId, quantity]) => {
      const option = priceOptions[priceId]
      return { priceId: Number(priceId), quantity, ...option, lineCents: option.priceCents * quantity }
    })

  const totalCents = lines.reduce((sum, line) => sum + line.lineCents, 0)
  const itemCount = lines.reduce((sum, line) => sum + line.quantity, 0)

  function setQuantity(priceId, text) {
    // Turn what was typed into a whole number from 0 to MAX_QUANTITY (an empty box counts as 0)
    const number = Math.floor(Number(text)) || 0
    const quantity = Math.min(Math.max(number, 0), MAX_QUANTITY)

    // State must be replaced, not edited in place, so React notices the change:
    // copy the old quantities and overwrite just this one
    setQuantities((previous) => ({ ...previous, [priceId]: quantity }))
  }

  async function handleSubmit(event) {
    // Stop the browser's default form submission (a full page reload); this code sends the order instead
    event.preventDefault()
    setOrderError(null)

    if (lines.length === 0) {
      setOrderError('Please choose at least one item before placing your order.')
      return
    }
    if (!name.trim()) {
      setOrderError('Please enter your name.')
      return
    }

    setSubmitting(true)

    try {
      // Only ids and quantities are sent; the server looks up prices itself so they can't be tampered with
      const order = await apiRequest('/api/orders', {
        method: 'POST',
        body: {
          name,
          phone,
          items: lines.map((line) => ({ price_id: line.priceId, quantity: line.quantity })),
        },
      })

      // Leave this site for Stripe's payment page. Stripe sends the customer back to /order/<token>
      window.location.assign(order.checkout_url)
    } catch (error) {
      setOrderError(error.message)
      setSubmitting(false)
    }
  }

  if (loadError) {
    return (
      <section className="error-page">
        <h2>Sorry!</h2>
        <p>The menu couldn&apos;t be loaded. {loadError}</p>
      </section>
    )
  }

  if (!categories) {
    return <p className="loading">Loading the menu...</p>
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {categories.map((category) => (
        // "key" gives each repeated element a stable identity, so React can update lists efficiently
        <section key={category.name}>
          <h3>{category.name}</h3>
          <ul>
            {category.items.map((item) => (
              <li className="menu-item" key={item.name}>
                <div className="item-info">
                  <span className="item-name">{item.name}</span>
                  <span className="item-description">{item.description}</span>
                </div>

                {/* One price and quantity box per size (single-price items just have one) */}
                <ul className="item-options">
                  {item.prices.map((price) => (
                    <li key={price.id}>
                      <label className="option">
                        <span className="item-price">
                          {price.label && `${price.label} `}
                          {formatCents(price.price_cents)}
                        </span>
                        <input
                          className="qty"
                          type="number"
                          inputMode="numeric"
                          min="0"
                          max={MAX_QUANTITY}
                          placeholder="0"
                          // Show an empty box instead of "0", so it's easy to type a new number
                          value={quantities[price.id] || ''}
                          onChange={(event) => setQuantity(price.id, event.target.value)}
                          aria-label={`Quantity of ${item.name}${price.label ? `, ${price.label}` : ''}`}
                        />
                      </label>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      ))}

      <section id="your-order" className="order-summary">
        <h3>Your order</h3>
        {lines.length === 0 ? (
          <p className="empty">Nothing yet. Choose quantities above to start your order.</p>
        ) : (
          <table className="order-table">
            <tbody>
              {lines.map((line) => (
                <tr key={line.priceId}>
                  <td>
                    {line.quantity} &times; {line.itemName}
                    {line.label && ` (${line.label})`}
                  </td>
                  <td>{formatCents(line.lineCents)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td>Order total</td>
                <td>{formatCents(totalCents)}</td>
              </tr>
            </tfoot>
          </table>
        )}
      </section>

      <section className="customer-info">
        <h3>Your info</h3>
        <div className="field">
          <label htmlFor="name">Name</label>
          <input
            type="text"
            id="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Enter your name"
            maxLength={MAX_NAME_LENGTH}
            autoComplete="name"
          />
        </div>

        <div className="field">
          <label htmlFor="phone">
            Phone Number <span className="optional">(optional)</span>
          </label>
          <input
            type="tel"
            id="phone"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="(630) 555-1234"
            maxLength={MAX_PHONE_LENGTH}
            autoComplete="tel"
          />
        </div>

        {/* role="alert" makes screen readers announce the message as soon as it appears */}
        {orderError && (
          <p className="error-message" role="alert">
            {orderError}
          </p>
        )}

        <button type="submit" disabled={submitting}>
          {submitting ? 'Taking you to payment...' : `Continue to payment${totalCents ? ` · ${formatCents(totalCents)}` : ''}`}
        </button>
      </section>

      {/* Stays at the bottom of the screen while scrolling, once something is in the order */}
      {itemCount > 0 && (
        <div className="order-bar">
          <span>
            {itemCount} {itemCount === 1 ? 'item' : 'items'} · {formatCents(totalCents)}
          </span>
          <a href="#your-order">Review order</a>
        </div>
      )}
    </form>
  )
}

export default MenuPage
