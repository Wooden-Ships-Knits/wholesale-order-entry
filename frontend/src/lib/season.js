// The Salesforce "Order Name" starts with the season code, e.g.
// "F26 SWEATERS 11/01 - 11/20" -> "F26", "S25 SWEATERS …" -> "S25".
// Returns '—' when there is no order name or no season-looking prefix.
export function seasonFromOrderName(orderName) {
  if (!orderName) return '—'
  const token = orderName.trim().split(/\s+/)[0]
  return /^[FS]\d{2}$/i.test(token) ? token.toUpperCase() : '—'
}
