import { Link, Route, Routes } from 'react-router'
import MenuPage from './pages/MenuPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'

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
          {/* The order and admin pages are built in the next steps */}
          <Route path="/order/:token" element={<p>The order page is coming in the next step.</p>} />
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
