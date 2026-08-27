import { useEffect, useState } from 'react'
import PasswordField from '../components/PasswordField'
import { login } from './api'

export default function RepLogin({ onSignedIn }) {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      // The server matches what was typed against the roster and hands back
      // the full name. Use that, not the typing: the dashboard header and
      // every ownership check are about the rep, not about the box.
      const d = await login(name.trim(), password)
      setPassword('')
      onSignedIn(d.name || name.trim())
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="admin-login" onSubmit={submit}>
      <h1>Rep sign-in</h1>
      {/* Typed, not picked (revised 2026-08-11): a rep types their first name.
          Case and stray spaces are the server's problem, and a full name still
          works for anyone who has the old dropdown in their muscle memory. */}
      <label>
        Your first name
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          autoComplete="username"
          autoCapitalize="words"
          autoCorrect="off"
          spellCheck={false}
        />
      </label>
      <PasswordField value={password} onChange={setPassword} />
      {error && <p className="admin-error">{error}</p>}
      <button type="submit" disabled={busy || !name.trim() || !password}>
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
      {/* Below the button and deliberately quiet: a rep who came here to sign
          in should not be pulled away from the form, but one who is stuck
          needs somewhere to go. The FAQ is public, so it opens without a
          session — which is the point, since being unable to sign in is one of
          the things it answers. */}
      <a className="faq-link" href="/faq">
        FAQ&rsquo;s
      </a>
    </form>
  )
}
