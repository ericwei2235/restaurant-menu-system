// The API sends money as whole cents (375 means $3.75), so all math stays exact.
// Cents are only turned into dollar text at the moment they're shown on screen

const dollars = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export function formatCents(cents) {
  return dollars.format(cents / 100)
}
