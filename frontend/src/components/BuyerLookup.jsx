import { useState } from 'react'
import { lookupAccounts } from '../api'

export default function BuyerLookup({ onSelect, onResult, accountName, setAccountName }) {
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState(null)
  const [status, setStatus] = useState('')

  async function search(e) {
    e.preventDefault()
    if (!query.trim()) return
    setStatus('Searching…')
    setMatches(null)
    try {
      const data = await lookupAccounts(query)
      setMatches(data.matches)
      onResult?.(data.matches)
      if (data.matches.length === 0) {
        setStatus('No matching account — please enter your details below.')
      } else if (data.matches.length === 1) {
        onSelect(data.matches[0])
        setStatus(`Found: ${data.matches[0].name} — details filled in below.`)
      } else {
        setStatus('Multiple matching accounts — choose one:')
      }
    } catch (err) {
      setStatus(`Lookup failed: ${err.message}`)
    }
  }

  return (
    <section className="section buyer-lookup">
      <h2>Account</h2>
      <div className="lookup-row">
        <label>
          Find your Account
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="'you@yourstore.com' or 'your store name'"
          />
        </label>
        <button type="button" onClick={search}>
          Look up
        </button>
      </div>
      {status && <p className="lookup-status">{status}</p>}

      <label>
        Account Name (store)<span className="req">*</span>
        <input
          type="text"
          value={accountName}
          onChange={(e) => setAccountName(e.target.value)}
          autoComplete="organization"
          placeholder="The store / account this order is for"
        />
      </label>
      {matches && matches.length > 1 && (
        <select
          className="match-select"
          defaultValue=""
          onChange={(e) => {
            const m = matches.find((x) => x.accountId === e.target.value)
            if (m) {
              onSelect(m)
              setStatus(`Selected: ${m.name} — details filled in below.`)
            }
          }}
        >
          <option value="" disabled>
            Select your account…
          </option>
          {matches.map((m) => (
            <option key={m.accountId} value={m.accountId}>
              {m.name} — {m.billTo.cityState || 'no address'}
            </option>
          ))}
        </select>
      )}
    </section>
  )
}
