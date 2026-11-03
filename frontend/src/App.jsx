import { useEffect, useState } from 'react'

// A component is a function that returns what should appear on screen.
// The HTML-like syntax is JSX: it looks like HTML but compiles to JavaScript
function App() {
  // useState creates a value React remembers between renders, plus a function to change it.
  // Calling the setter makes React re-run this function and update the page
  const [menu, setMenu] = useState(null)
  const [error, setError] = useState(null)

  // useEffect runs code after the component appears on screen.
  // The empty list [] at the end means "only once", not after every re-render
  useEffect(() => {
    // Ask Flask for the menu. In development, Vite's proxy forwards /api/... to Flask
    fetch('/api/menu')
      .then((response) => {
        if (!response.ok) {
          throw new Error(`The server answered ${response.status}`)
        }
        return response.json()
      })
      .then((data) => setMenu(data))
      .catch((err) => setError(err.message))
  }, [])

  // Count the items and price options across all categories
  const itemCount = menu ? menu.categories.reduce((total, category) => total + category.items.length, 0) : 0

  return (
    <>
      <header>
        <h1>China Chef</h1>
        <p className="tagline">Authentic Chinese-American Cuisine</p>
      </header>

      <main>
        {/* Exactly one of these three lines shows, depending on where loading stands */}
        {error && <p>Couldn't reach the server: {error}</p>}
        {!error && !menu && <p>Loading the menu...</p>}
        {menu && (
          <p>
            Connected to the API: {menu.categories.length} categories, {itemCount} items.
          </p>
        )}
      </main>
    </>
  )
}

export default App
