import { useState } from 'react'
import { lookupAccounts, suggestAccounts } from '../api'

export default function BuyerLookup({ onSelect, onResult, accountName, setAccountName }) {
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [status, setStatus] = useState('')
  const [picking, setPicking] = useState(false)

  async function search(e) {
    e.preventDefault()
    if (!query.trim()) return
    setStatus('Searching…')
    setMatches(null)
    setSuggestions([])
    try {
      const data = await lookupAccounts(query)
      setMatches(data.matches)
      onResult?.(data.matches)
      if (data.matches.length === 0) {
        // The name is exact-matched, so a franchise ("Scout & Molly" vs
        // "SCOUT & MOLLY'S (NASHVILLE)") or a slightly-off spelling finds
        // nothing. Offer the closest names rather than sending them off to
        // fill everything in by hand — that is how duplicate accounts start.
        await offerSuggestions()
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

  async function offerSuggestions() {
    // Email lookups have no fuzzy equivalent — an almost-right address is a
    // different person, not a near miss.
    if (query.includes('@')) {
      setStatus('No matching account — please enter your details below.')
      return
    }
    try {
      const { suggestions: found } = await suggestAccounts(query)
      setSuggestions(found)
      setStatus(
        found.length
          ? 'No exact match. Did you mean one of these?'
          : 'No matching account — please enter your details below.',
      )
    } catch {
      setStatus('No matching account — please enter your details below.')
    }
  }

  // Suggestions carry only id/name/city, so fetch the full record before
  // filling the form.
  async function pick(accountId) {
    setPicking(true)
    setStatus('Loading account…')
    try {
      const data = await lookupAccounts(accountId)
      const account = data.matches[0]
      if (!account) {
        setStatus('That account could not be loaded — please enter your details below.')
        return
      }
      onSelect(account)
      onResult?.(data.matches)
      setSuggestions([])
      setStatus(`Found: ${account.name} — details filled in below.`)
    } catch (err) {
      setStatus(`Could not load that account: ${err.message}`)
    } finally {
      setPicking(false)
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

      {/* City/state is the only way to tell franchise locations apart —
          nine "SCOUT & MOLLY'S" rows are indistinguishable by name alone. */}
      {suggestions.length > 0 && (
        <ul className="suggestion-list">
          {suggestions.map((s) => (
            <li key={s.accountId}>
              <button type="button" disabled={picking} onClick={() => pick(s.accountId)}>
                <span className="suggestion-name">{s.name}</span>
                {s.cityState && <span className="suggestion-where">{s.cityState}</span>}
              </button>
            </li>
          ))}
          <li className="suggestion-none">
            None of these? Continue filling in your details below.
          </li>
        </ul>
      )}

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
