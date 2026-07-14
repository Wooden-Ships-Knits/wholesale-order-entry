// Client-side mirror of the order-minimum rules (PRD §6). The server is the
// authority; this exists for immediate buyer feedback only.
//
// A "line" is a manually added order row: { id, styleName, color, qty:{xs,sm,ml} }
// plus `row` — the matched catalog entry (null until style+color are picked).

export const MIN_TOTAL = 18
export const MIN_PER_STYLE = 4
export const MIN_PER_SKU = 2

export const catalogKey = (styleName, color) => `${styleName}|${color}`

export function computeTotals(lines) {
  let totalPieces = 0
  let totalAmount = 0
  const perLine = {}
  for (const l of lines) {
    const pieces = (l.qty.xs || 0) + (l.qty.sm || 0) + (l.qty.ml || 0)
    const amount = l.row ? pieces * (l.row.unitPrice || 0) : 0
    perLine[l.id] = { pieces, amount }
    if (l.row) {
      totalPieces += pieces
      totalAmount += amount
    }
  }
  return { totalPieces, totalAmount, perLine }
}

export function validateMinimums(lines) {
  const errors = []
  const badCells = new Set()

  // lines with quantities but no product picked
  for (const l of lines) {
    const pieces = (l.qty.xs || 0) + (l.qty.sm || 0) + (l.qty.ml || 0)
    if (pieces > 0 && !l.row) {
      errors.push('A line has quantities but no product selected — pick a style and color.')
    }
  }

  // duplicate style+color lines
  const seen = new Map()
  for (const l of lines) {
    if (!l.row) continue
    const k = catalogKey(l.row.styleName, l.row.color)
    if (seen.has(k)) {
      errors.push(`"${l.row.styleName} — ${l.row.color}" appears on more than one line — combine them.`)
    }
    seen.set(k, l.id)
  }

  const styleTotals = {}
  for (const l of lines) {
    if (!l.row) continue
    const pieces = (l.qty.xs || 0) + (l.qty.sm || 0) + (l.qty.ml || 0)
    if (pieces > 0) styleTotals[l.row.styleName] = (styleTotals[l.row.styleName] || 0) + pieces
  }

  const totalPieces = Object.values(styleTotals).reduce((a, b) => a + b, 0)
  if (totalPieces > 0 && totalPieces < MIN_TOTAL) {
    errors.push(`Order total is ${totalPieces} pieces — the minimum is ${MIN_TOTAL}.`)
  }

  for (const [style, pieces] of Object.entries(styleTotals)) {
    if (pieces < MIN_PER_STYLE) {
      errors.push(`"${style}" has ${pieces} piece${pieces === 1 ? '' : 's'} — each style needs at least ${MIN_PER_STYLE}.`)
    }
  }

  for (const l of lines) {
    if (!l.row) continue
    for (const size of ['xs', 'sm', 'ml']) {
      const n = l.qty[size] || 0
      if (n > 0 && n < MIN_PER_SKU && (styleTotals[l.row.styleName] || 0) < MIN_PER_STYLE) {
        errors.push(
          `"${l.row.styleName} — ${l.row.color}" ${size.toUpperCase()} has ${n} piece — minimum ${MIN_PER_SKU} per size until the style reaches ${MIN_PER_STYLE}.`,
        )
        badCells.add(`${l.id}|${size}`)
      }
    }
  }

  return { errors, badCells, totalPieces }
}
