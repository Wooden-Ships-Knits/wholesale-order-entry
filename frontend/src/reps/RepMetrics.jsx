// Metric cards above the rep's order table. Display only — the status chips are
// the filter control.
//
// The counts come from the server and always describe the rep's WHOLE book,
// never the filtered view. That still matters with the cards inert: the chips
// filter server-side, so without it selecting "Accepted" would leave the page
// holding only accepted orders and the other four cards would read zero.

// The three status cards partition the total exactly. Awaiting signature cuts
// across them (an order can be awaiting both a signature and a review), so it
// is rendered apart from the status group rather than in line with it.
const STATUS_CARDS = [
  { label: 'Awaiting review', key: 'awaitingReview' },
  { label: 'Accepted', key: 'accepted' },
  { label: 'Declined', key: 'declined' },
]

function Card({ label, value, sub, title }) {
  return (
    <div className="metric-card" title={title}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
      {/* A slot even when empty, so cards with a sub-line and cards without
          still line up along the bottom. */}
      <span className="metric-sub">{sub || ' '}</span>
    </div>
  )
}

export default function RepMetrics({ counts }) {
  if (!counts) return null

  const waiting = counts.awaitingSignature
  const oldest = counts.oldestAwaitingDays
  const unsent = counts.signatureNotSent

  // "longest 12 days" is what makes the count actionable — three links out for
  // two days is healthy, one out for three weeks is a lost order. The unsent
  // count only appears when there is one, because it means someone must act.
  const waitingSub = [
    oldest != null ? `longest ${oldest} ${oldest === 1 ? 'day' : 'days'}` : '',
    unsent ? `${unsent} not sent yet` : '',
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <div className="metric-row">
      <Card
        label="Total orders"
        value={counts.total}
        sub={counts.total ? `${counts.totalQty} pcs` : ''}
        title="Every order of yours, whatever the table below is showing"
      />
      <Card
        label="Awaiting signature"
        value={waiting}
        sub={waiting ? waitingSub : ''}
        title="A signing link is out and the buyer hasn't signed yet"
      />
      {STATUS_CARDS.map((c) => (
        <Card key={c.key} label={c.label} value={counts[c.key]} />
      ))}
    </div>
  )
}
