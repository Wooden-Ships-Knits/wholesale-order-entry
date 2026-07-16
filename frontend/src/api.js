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
export const getProducts = (season) => get(`/api/products?season=${encodeURIComponent(season)}`)
export const lookupAccounts = (query) => {
  const param = query.includes('@') ? 'email' : 'accountId'
  return get(`/api/accounts?${param}=${encodeURIComponent(query.trim())}`)
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
