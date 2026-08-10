import { useEffect, useState } from 'react'
import { getRepNames, login } from './api'

export default function RepLogin({ onSignedIn }) {
  const [names, setNames] = useState([])
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // The roster comes from the server, so adding a rep never means editing two
  // places. A failure here leaves the dropdown empty and Sign in disabled,
  // which is the honest state — the login would be rejected anyway.
  useEffect(() => {
    getRepNames()
      .then((d) => setNames(d.names))
      .catch(() => setError('Could not load the rep list. Refresh to try again.'))
  }, [])

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(name, password)
      setPassword('')
      onSignedIn(name)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="admin-login" onSubmit={submit}>
      <h1>Rep sign-in</h1>
      <label>
        Your name
        <select value={name} onChange={(e) => setName(e.target.value)} autoFocus>
          <option value="">Select your name…</option>
          {names.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
      </label>
      {error && <p className="admin-error">{error}</p>}
      <button type="submit" disabled={busy || !name || !password}>
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  )
}
