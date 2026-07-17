// Warning modal shown to sales reps when the conflict check finds an existing
// stockist too close to a new account's store. Informational only — never
// blocks submission. See docs/conflict-checker.md.
export default function ConflictWarning({ result, onDismiss }) {
  const conflicting = result.neighbors.filter((n) =>
    n.driveMinutes != null
      ? n.driveMinutes < result.maxMinutes
      : result.mode === 'straight-line' && n.distanceMiles < result.maxMinutes * 0.5,
  ).length

  return (
    <div className="conflict-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="conflict-modal-title">
      <div className="conflict-modal">
        <h2 id="conflict-modal-title">⚠ Possible stockist conflict</h2>
        <p>
          {conflicting} existing stockist{conflicting === 1 ? ' is' : 's are'} within a{' '}
          {result.maxMinutes}-minute drive of this store.
        </p>
        {result.mode === 'straight-line' && (
          <p className="conflict-modal-note">
            Approximate — based on straight-line distance ({result.maxMinutes} min ≈{' '}
            {result.maxMinutes * 0.5} miles), not drive time.
          </p>
        )}
        <table className="conflict-modal-table">
          <thead>
            <tr>
              <th>Store</th>
              <th>Location</th>
              <th>Last order</th>
              <th className="num">Miles</th>
              <th className="num">Drive (min)</th>
            </tr>
          </thead>
          <tbody>
            {result.neighbors.map((n) => (
              <tr
                key={n.accountId}
                className={
                  (n.driveMinutes != null
                    ? n.driveMinutes < result.maxMinutes
                    : result.mode === 'straight-line' && n.distanceMiles < result.maxMinutes * 0.5)
                    ? 'row-conflict'
                    : ''
                }
              >
                <td>{n.name}</td>
                <td>{n.cityState}</td>
                <td>{n.lastOrder ?? '—'}</td>
                <td className="num">{n.distanceMiles}</td>
                <td className="num">{n.driveMinutes ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="conflict-modal-note">This is a warning only — the order can still be submitted.</p>
        <div className="conflict-modal-actions">
          <button type="button" onClick={onDismiss}>
            OK, got it
          </button>
        </div>
      </div>
    </div>
  )
}
