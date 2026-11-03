import { Link } from 'react-router'

function NotFoundPage() {
  return (
    <section className="error-page">
      <h2>Sorry!</h2>
      <p>We couldn&apos;t find that page.</p>
      <p>
        <Link className="button-link" to="/">
          Back to menu
        </Link>
      </p>
    </section>
  )
}

export default NotFoundPage
