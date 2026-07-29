// Admin API. Every call sends the session cookie.
async function request(url, options = {}) {
  const res = await fetch(url, { credentials: 'same-origin', ...options })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = new Error(body.detail || `Request failed (${res.status})`)
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

// Store-name search for the account picker. Admin-only, so it carries rank and
// territory too — needed to choose between franchise locations.
export const suggestAccounts = (q) =>
  request(`/api/admin/accounts/suggest?q=${encodeURIComponent(q.trim())}`)

// Correct which store an order belongs to. accountId null = the typed name
// matches nothing, i.e. it really is a new store.
export const setOrderAccount = (id, accountName, accountId = null) =>
  post(`/api/admin/orders/${id}/account`, { account_name: accountName, account_id: accountId })

// Draft of the "we already have a stockist nearby" email. Pass { orderId } from
// the order table, or the store details from the conflict-check tab.
export const getConflictEmail = (payload) => post('/api/conflict-email', payload)

// Send a drafted email (To/Cc/Subject/Body) via the server's SMTP account.
export const sendEmail = (payload) => post('/api/send-email', payload)

export const pdfUrl = (id) => `/api/admin/orders/${id}/pdf`
// Admin copy showing the full card number, for keying into Salesforce. Rendered
// per request from the encrypted copy — never stored unencrypted or emailed.
export const cardPdfUrl = (id) => `/api/admin/orders/${id}/pdf?full=1`
export const certUrl = (id) => `/api/admin/orders/${id}/certificate`

// Admin reports (DTO/DMM). getReport = last cached run; runReport = run now.
export const getReport = (key) => request(`/api/admin/reports/${key}`)
export const runReport = (key) => post(`/api/admin/reports/${key}/run`)
