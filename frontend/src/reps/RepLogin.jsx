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
    // action/method are never used — submit() cancels the browser's own POST
    // and fetch() does the work. They are here as a HINT: a browser deciding
    // whether to offer "save this password?" reads the form's target to know
    // which credential it would be saving, and a form with no action looks
    // less like a login than one that names its endpoint. See also the name/id
    // on both fields below, which is the part that actually matters.
    <form
      className="admin-login"
      onSubmit={submit}
      action="/api/reps-portal/login"
      method="post"
    >
      <h1>Rep sign-in</h1>
      {/* Typed, not picked (revised 2026-08-11): a rep types their first name.
          Case and stray spaces are the server's problem, and a full name still
          works for anyone who has the old dropdown in their muscle memory. */}
      <label>
        Your first name
        {/* name/id, not just autoComplete: a password manager keys its saved
            entry on the field's name, and a nameless input is one browsers
            routinely decline to offer to save. */}
        <input
          type="text"
          name="username"
          id="rep-username"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          autoComplete="username"
          autoCapitalize="words"
          autoCorrect="off"
          spellCheck={false}
        />
      </label>
      <PasswordField
        value={password}
        onChange={setPassword}
        name="password"
        id="rep-password"
      />
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
