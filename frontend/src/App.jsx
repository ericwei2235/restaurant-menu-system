import { Link, Route, Routes } from 'react-router'
import MenuPage from './pages/MenuPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'
import OrderPage from './pages/OrderPage.jsx'

// The parts every page shares (banner, header, footer) are written once here,
// and <Routes> swaps in the right page for the current address
function App() {
  return (
    <>
      {/* Warns visitors this is a portfolio demo so nobody thinks they placed a real order */}
      <p className="demo-banner">
        Demo project &mdash; orders placed here are not sent to the restaurant. Payments run in test mode: use card{' '}
        <strong>4242 4242 4242 4242</strong> with any future date and any CVC.
      </p>

      <header>
        {/* Link changes the page without reloading, unlike a plain <a href> */}
        <h1>
          <Link to="/">China Chef</Link>
        </h1>
        <p className="tagline">Authentic Chinese-American Cuisine</p>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<MenuPage />} />
          {/* Stripe sends customers back here after paying or cancelling */}
          <Route path="/order/:token" element={<OrderPage />} />
          {/* The admin page is built in the next step */}
          <Route path="/admin" element={<p>The admin page is coming soon.</p>} />
          {/* "*" matches any address not listed above */}
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>

      <footer>
        <p>364 W Indian Trail Rd</p>
      </footer>
    </>
  )
}

export default App
