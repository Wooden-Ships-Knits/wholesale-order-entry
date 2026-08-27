import { useState } from 'react'

/** A password box with a show/hide eye on the right.
 *
 * Shared by the admin and rep sign-ins so the two can't drift apart. Both
 * passwords are typed rarely and from memory, and a mistyped one gives only
 * "Incorrect password" — being able to look is the difference between one
 * attempt and three, which matters now that both logins are rate-limited.
 *
 * Starts hidden, and every mount starts hidden: revealing is a deliberate act,
 * never a state that persists into the next person's session.
 */
export default function PasswordField({
  value,
  onChange,
  label = 'Password',
  autoFocus = false,
  autoComplete = 'current-password',
  // Optional, because a browser's "save this password?" heuristic wants a named
  // field and `autocomplete` alone is often not enough to trigger it. Left
  // undefined by default so the callers that haven't opted in are unchanged —
  // an offer to save is a convenience with a cost, and it's per-page.
  name,
  id,
}) {
  const [shown, setShown] = useState(false)

  return (
    <label className="password-field">
      {label}
      <span className="password-input">
        <input
          type={shown ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          name={name}
          id={id}
        />
        {/* tabIndex -1: Tab should go from the password straight to Sign in,
            not detour through a button nobody reaches by keyboard. The label
            is still announced, so a screen reader can find and use it. */}
        <button
          type="button"
          className="password-toggle"
          onClick={() => setShown((s) => !s)}
          aria-label={shown ? 'Hide password' : 'Show password'}
          aria-pressed={shown}
          title={shown ? 'Hide password' : 'Show password'}
          tabIndex={-1}
        >
          {shown ? <EyeOff /> : <Eye />}
        </button>
      </span>
    </label>
  )
}

/* Inline SVG rather than an icon font or an image: two small shapes, no extra
   request, and they inherit the surrounding colour. */
function Eye() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        d="M1.5 12S5.5 5 12 5s10.5 7 10.5 7-4 7-10.5 7S1.5 12 1.5 12Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

function EyeOff() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        d="M1.5 12S5.5 5 12 5s10.5 7 10.5 7-4 7-10.5 7S1.5 12 1.5 12Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4 20 20 4" fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}
