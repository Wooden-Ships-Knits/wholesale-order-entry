import { useMemo, useState } from 'react'

const SIZES = [
  { key: 'xs', label: 'X/S' },
  { key: 'sm', label: 'S/M' },
  { key: 'ml', label: 'M/L' },
]

const MAX_SUGGESTIONS = 8

function StyleTypeahead({ styles, line, onPickStyle, onQueryChange }) {
  const [open, setOpen] = useState(false)

  const suggestions = useMemo(() => {
    const q = (line.query || '').trim().toUpperCase()
    if (!q) return []
    return styles
      .filter((s) => s.styleName.includes(q) || s.code.toUpperCase().includes(q))
      .slice(0, MAX_SUGGESTIONS)
  }, [styles, line.query])

  return (
    <div className="typeahead">
      <input
        type="text"
        placeholder="Type a style name or code…"
        value={line.query}
        onChange={(e) => {
          onQueryChange(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && suggestions.length > 0 && (
        <ul className="suggestions">
          {suggestions.map((s) => (
            <li key={s.styleName}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault()
                  onPickStyle(s)
                  setOpen(false)
                }}
              >
                <span className="sugg-code">{s.code}</span> {s.styleName}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function ProductLines({
  rows,
  lines,
  updateLine,
  addLine,
  removeLine,
  perLine,
  totalPieces,
  totalAmount,
  badCells,
  loading,
  seasonSelected,
}) {
  // catalog derived per style: styleName -> { code, colors: [row, ...] }
  const styles = useMemo(() => {
    const map = new Map()
    for (const r of rows) {
      if (!map.has(r.styleName)) map.set(r.styleName, { styleName: r.styleName, code: r.code, colors: [] })
      map.get(r.styleName).colors.push(r)
    }
    return [...map.values()].sort((a, b) => a.styleName.localeCompare(b.styleName))
  }, [rows])

  const styleByName = useMemo(() => new Map(styles.map((s) => [s.styleName, s])), [styles])

  if (loading) {
    return (
      <section className="section">
        <p>Loading products…</p>
      </section>
    )
  }
  if (!seasonSelected) {
    return (
      <section className="section">
        <p className="muted">Select a collection above, then add your items below.</p>
      </section>
    )
  }

  return (
    <section className="section products">
      <h2>Products</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="code-col">Code #</th>
              <th className="style-col">Style name</th>
              <th className="color-col">Color</th>
              {SIZES.map((s) => (
                <th key={s.key} className="num size-col">
                  {s.label}
                </th>
              ))}
              <th className="num">Total qty</th>
              <th className="num">Unit price $</th>
              <th className="num">Line total $</th>
              <th className="rm-col" />
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => {
              const style = line.styleName ? styleByName.get(line.styleName) : null
              const totals = perLine[line.id] || { pieces: 0, amount: 0 }
              return (
                <tr key={line.id}>
                  <td className="code-col">{style?.code || ''}</td>
                  <td className="style-col">
                    <StyleTypeahead
                      styles={styles}
                      line={line}
                      onQueryChange={(q) =>
                        updateLine(line.id, { query: q.toUpperCase(), styleName: '', color: '' })
                      }
                      onPickStyle={(s) =>
                        updateLine(line.id, {
                          query: s.styleName,
                          styleName: s.styleName,
                          color: s.colors.length === 1 ? s.colors[0].color : '',
                        })
                      }
                    />
                  </td>
                  <td className="color-col">
                    <select
                      value={line.color}
                      disabled={!style}
                      onChange={(e) => updateLine(line.id, { color: e.target.value })}
                    >
                      <option value="">{style ? 'Choose color…' : '—'}</option>
                      {style?.colors.map((c) => (
                        <option key={c.color} value={c.color}>
                          {c.color}
                        </option>
                      ))}
                    </select>
                  </td>
                  {SIZES.map((s) => {
                    const available = line.row?.sizes?.[s.key]
                    return (
                      <td key={s.key} className="num qty-cell size-col">
                        <input
                          type="number"
                          min="0"
                          step="1"
                          inputMode="numeric"
                          disabled={!line.row || !available}
                          className={badCells.has(`${line.id}|${s.key}`) ? 'bad' : ''}
                          value={line.qty[s.key] ?? ''}
                          onChange={(e) => updateLine(line.id, { qty: { ...line.qty, [s.key]: e.target.value === '' ? undefined : Math.max(0, Math.floor(Number(e.target.value) || 0)) } })}
                        />
                      </td>
                    )
                  })}
                  <td className="num">{totals.pieces || ''}</td>
                  <td className="num">{line.row?.unitPrice?.toFixed(2) || ''}</td>
                  <td className="num">{totals.amount ? totals.amount.toFixed(2) : ''}</td>
                  <td className="rm-col">
                    <button
                      type="button"
                      className="remove-line"
                      title="Remove line"
                      onClick={() => removeLine(line.id)}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan="7" className="num strong">
                Total pieces: {totalPieces}
              </td>
              <td className="num strong" colSpan="3">
                Grand total: ${totalAmount.toFixed(2)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="add-line-row">
        <button type="button" className="add-line" onClick={addLine}>
          + Add line
        </button>
      </div>
      <p className="muted small">
        Minimums: 18 pieces total · 4 per style · 2 per size (singles allowed once a style reaches 4) · no
        pre-packs
      </p>
    </section>
  )
}
