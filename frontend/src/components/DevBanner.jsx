import { useEffect, useState } from 'react'
import { getHealth } from '../api'

// Shown on every page when the backend has its dev safety switches on. The dev
// and production sites are identical to look at, and only one of them can email
// a real rep — so the difference has to be visible, not remembered.
//
// It renders nothing at all in production: a banner that is usually there is a
// banner nobody reads.
export default function DevBanner() {
  const [info, setInfo] = useState(null)

  useEffect(() => {
    // A failure here must never blank the page it sits above: no banner is the
    // right answer if we cannot tell which environment this is.
    getHealth()
      .then((h) => h?.dev && setInfo(h))
      .catch(() => {})
  }, [])

  if (!info) return null

  const neutered = [
    info.mailRedirected && 'email goes to the test inbox',
    info.salesforceReadonly && 'Salesforce writes are blocked',
  ].filter(Boolean)

  return (
    <div className="dev-banner" role="status">
      <strong>DEVELOPMENT</strong>
      <span>Not the live site — {neutered.join(' · ')}.</span>
    </div>
  )
}
