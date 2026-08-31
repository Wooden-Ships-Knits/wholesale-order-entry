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

// Close the tax-cert chase on one order without emailing the buyer — for a
// batch of orders from one new store, where the certificate arrives once. Does
// NOT mean a certificate exists here; `hasCertificate` still answers that.
export const setTaxCertCleared = (id, note = '', cleared = true) =>
  post(`/api/admin/orders/${id}/tax-cert-cleared`, { cleared, note })

// Capture new inbound conflict replies and classify them. Returns
// { captured, suggested }. No-op server-side if IMAP/OpenAI aren't configured.
export const pollReplies = () => post('/api/admin/poll-replies')
// Store-name search for the account picker. Admin-only, so it carries rank and
// territory too — needed to choose between franchise locations.
export const suggestAccounts = (q) =>
  request(`/api/admin/accounts/suggest?q=${encodeURIComponent(q.trim())}`)

// Correct which store an order belongs to. accountId null = the typed name
// matches nothing, i.e. it really is a new store.
export const setOrderAccount = (id, accountName, accountId = null) =>
  post(`/api/admin/orders/${id}/account`, { account_name: accountName, account_id: accountId })

// Ship window: the live list for this order's season, then the change itself.
// The season isn't editable — prices were resolved from its price book.
export const getOrderShipWindows = (id) => request(`/api/admin/orders/${id}/ship-windows`)
export const setOrderShipWindow = (id, shipWindow) =>
  post(`/api/admin/orders/${id}/ship-window`, { ship_window: shipWindow })

// Draft of the "we already have a stockist nearby" email. Pass { orderId } from
// the order table, or the store details from the conflict-check tab.
export const getConflictEmail = (payload) => post('/api/conflict-email', payload)

// Draft of the "review and sign your order" email to the buyer. Generating the
// draft mints the signing token embedded in the link (an unexpired one is
// reused), so re-drafting never leaves two working links for one order.
export const getSignatureEmail = (orderId, email = null) =>
  post('/api/signature-email', { orderId, email })

// Revoke an outstanding signing link. The buyer's link stops working at once,
// and the order becomes editable in /admin again (accept, ship window, relink
// are all blocked while a link is live).
export const cancelSignatureLink = (id) => post(`/api/admin/orders/${id}/cancel-signature`)

// Send a drafted email (To/Cc/Subject/Body) via the server's SMTP account.
export const sendEmail = (payload) => post('/api/send-email', payload)

export const pdfUrl = (id) => `/api/admin/orders/${id}/pdf`
// Admin copy showing the full card number, for keying into Salesforce. Rendered
// per request from the encrypted copy — never stored unencrypted or emailed.
export const cardPdfUrl = (id) => `/api/admin/orders/${id}/pdf?full=1`
export const certUrl = (id) => `/api/admin/orders/${id}/certificate`

// Every season with a wholesale price book, newest first. limit=0 opts out of
// the 2-season cap the order form uses — notices are built for past seasons.
export const getAllSeasons = () => request('/api/seasons?limit=0')

// ---- Payment notice cards ----
// Photos stream from Drive while the card is drawn, so there is nothing to
// pre-download — one request builds the cards.
export const runNotice = (seasonCode, soNumbers) =>
  post('/api/admin/notices/run', { season_code: seasonCode, so_numbers: soNumbers })
export const getNoticeCards = () => request('/api/admin/notices/cards')
// <img src> — the route is authenticated, and the session cookie rides along
// with the image request the same way it does for the order PDFs.
export const noticeCardUrl = (name) =>
  `/api/admin/notices/cards/${encodeURIComponent(name)}`

// Admin reports (DTO/DMM). getReport = last cached run; runReport = run now.
export const getReport = (key) => request(`/api/admin/reports/${key}`)
export const runReport = (key) => post(`/api/admin/reports/${key}/run`)
