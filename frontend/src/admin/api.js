// FastAPI errors put `detail` as a string, or a list of {msg,...} objects for
// 422 validation errors. Render either as readable text (never "[object Object]").
function detailToMessage(detail, fallback) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d?.msg || JSON.stringify(d)).join('; ')
  if (detail && typeof detail === 'object') return detail.msg || JSON.stringify(detail)
  return fallback
}

// Admin API. Every call sends the session cookie.
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

export const getSession = () => request('/api/admin/session')
export const login = (password) => post('/api/admin/login', { password })
export const logout = () => post('/api/admin/logout')
export const getOrders = (statusFilter) =>
  request(`/api/admin/orders${statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : ''}`)
export const setOrderStatus = (id, status, reason = '') =>
  post(`/api/admin/orders/${id}/status`, { status, reason })

// Create the Salesforce Business Account for a new-account order (live write).
export const createSfAccount = (id) => post(`/api/admin/orders/${id}/create-account`)

// Record how a conflict inquiry ended so the row closes. outcome is
// "cleared" or "real_conflict"; note is optional free text. Local stamp only.
export const setConflictResolution = (id, outcome, note = '') =>
  post(`/api/admin/orders/${id}/conflict-resolution`, { outcome, note })

// Capture new inbound conflict replies and classify them. Returns
// { captured, suggested }. No-op server-side if IMAP/OpenAI aren't configured.
export const pollReplies = () => post('/api/admin/poll-replies')

// Draft of the "we already have a stockist nearby" email. Pass { orderId } from
// the order table, or the store details from the conflict-check tab.
export const getConflictEmail = (payload) => post('/api/conflict-email', payload)

// Send a drafted email (To/Cc/Subject/Body) via the server's SMTP account.
export const sendEmail = (payload) => post('/api/send-email', payload)

export const pdfUrl = (id) => `/api/admin/orders/${id}/pdf`
export const certUrl = (id) => `/api/admin/orders/${id}/certificate`

// Admin reports (DTO/DMM). getReport = last cached run; runReport = run now.
export const getReport = (key) => request(`/api/admin/reports/${key}`)
export const runReport = (key) => post(`/api/admin/reports/${key}/run`)
