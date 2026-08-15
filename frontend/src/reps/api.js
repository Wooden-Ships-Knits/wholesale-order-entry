// Rep dashboard API. Its own client rather than admin/api.js: the two pages
// talk to different routers behind different sessions, and the rep page must
// stay incapable of calling an admin route by accident.

function detailToMessage(detail, fallback) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d?.msg || JSON.stringify(d)).join('; ')
  if (detail && typeof detail === 'object') return detail.msg || JSON.stringify(detail)
  return fallback
}

// Every call sends the session cookie.
async function request(url, options = {}) {
  const res = await fetch(url, { credentials: 'same-origin', ...options })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = new Error(detailToMessage(body.detail, `Request failed (${res.status})`))
    err.status = res.status
    throw err
  }
  return res.json()
}

const post = (url, payload) =>
  request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload ?? {}),
  })

export const getRepNames = () => request('/api/reps-portal/names')
export const getSession = () => request('/api/reps-portal/session')
export const login = (name, password) => post('/api/reps-portal/login', { name, password })
export const logout = () => post('/api/reps-portal/logout')
// The buyer-facing PDF for one of the rep's own orders. Scoped server-side:
// another rep's id 404s, so this is a link, not a permission.
export const pdfUrl = (id) => `/api/reps-portal/orders/${id}/pdf`

export const getOrders = (statusFilter) =>
  request(
    `/api/reps-portal/orders${
      statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : ''
    }`,
  )
export const searchStore = (query) =>
  request(`/api/reps-portal/stores${query ? `?q=${encodeURIComponent(query)}` : ''}`)

// --- Prospects -------------------------------------------------------------
// The endpoint does not exist yet. Rather than block the UI on it, a 404 falls
// back to sample data and flags itself with `mocked` so the page can say so —
// nothing here silently pretends to be real. Delete the fallback (and
// prospectsMock.js) once the route lands; the success path is already correct.
export async function getProspects() {
  try {
    return await request('/api/reps-portal/prospects')
  } catch (err) {
    if (err.status !== 404) throw err
    const build = (await import('./prospectsMock')).default
    return { ...build(), mocked: true }
  }
}

// The rep's own shortlist flag. Kept per rep server-side, so one rep starring a
// store never changes what another sees.
export async function markProspect(id, marked) {
  try {
    return await post(`/api/reps-portal/prospects/${encodeURIComponent(id)}/mark`, { marked })
  } catch (err) {
    if (err.status !== 404) throw err
    return { marked } // mock mode: the star is local until the route exists
  }
}