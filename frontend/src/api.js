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
export const getOrderWriters = () => get('/api/order-writers')
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

export async function submitOrder(payload) {
  const res = await fetch('/api/orders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msgs = body?.detail?.errors?.map((e) => e.message) || [body?.detail || `Submit failed (${res.status})`]
    const err = new Error(msgs.join(' '))
    err.messages = msgs
    throw err
  }
  return body
}
