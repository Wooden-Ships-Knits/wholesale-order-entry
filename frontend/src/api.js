// Normalise the many error shapes FastAPI can return into a flat string[]:
//  - order-minimum:  { detail: { errors: [{ message }] } }
//  - Pydantic 422:   { detail: [{ loc, msg, type }, ...] }  <- was rendering as [object Object]
//  - plain string:   { detail: "..." }
function extractErrors(body, status) {
  const detail = body?.detail
  if (detail?.errors?.length) return detail.errors.map((e) => e.message)
  if (Array.isArray(detail)) {
    return detail.map((e) => {
      const field = Array.isArray(e.loc) ? e.loc.filter((p) => p !== 'body').join('.') : ''
      return field ? `${field}: ${e.msg}` : e.msg
    })
  }
  if (typeof detail === 'string') return [detail]
  return [`Submit failed (${status})`]
}

async function get(url) {
  const res = await fetch(url)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export const getSeasons = () => get('/api/seasons')
export const getReps = () => get('/api/reps')
export const getTerritories = () => get('/api/territories')
// Territory auto-assigned to a NEW account from its Ship To state (2-letter code).
export const getTerritoryForState = (state) =>
  get(`/api/territory?state=${encodeURIComponent(state)}`)
export const getOrderWriters = () => get('/api/order-writers')
export const getShipWindows = (season) =>
  get(`/api/ship-windows?season=${encodeURIComponent(season)}`)
export const getProducts = (season) => get(`/api/products?season=${encodeURIComponent(season)}`)
// '@' -> email; a bare 15/18-char Salesforce id -> accountId; anything else is
// treated as the account (store) name.
export const lookupAccounts = (query) => {
  const q = query.trim()
  let param = 'name'
  if (q.includes('@')) param = 'email'
  else if (/^[a-zA-Z0-9]{15}([a-zA-Z0-9]{3})?$/.test(q)) param = 'accountId'
  return get(`/api/accounts?${param}=${encodeURIComponent(q)}`)
}

// New-customer stockist conflict check (see docs/conflict-checker.md).
// Server defaults apply: k=5 neighbors, 20-minute drive threshold.
export const getNearbyAccounts = (lat, lng) =>
  get(`/api/accounts/nearby?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`)

export async function submitOrder(payload) {
  const res = await fetch('/api/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msgs = extractErrors(body, res.status)
    const err = new Error(msgs.join(' '))
    err.messages = msgs
    throw err
  }
  return body
}
