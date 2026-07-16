import { useEffect } from 'react'

export default function InternalUse({ internal, setInternal, certOnFile, setCertOnFile, reps = [] }) {
  // Keep an auto-filled rep selectable even if it isn't in the picklist.
  // const repOptions = internal.rep && !reps.includes(internal.rep) ? [internal.rep, ...reps] : reps
  const repOptions = ['Aviva', 'Denise', 'Jason', 'Kitty', 'Michael', 'Rande', 'Vickie']
  const isSplit = internal.split === true

  // Without a split, the credited rep is whoever wrote the order.
  useEffect(() => {
    if (!isSplit && internal.rep !== internal.orderWrittenBy) {
      setInternal('rep', internal.orderWrittenBy)
    }
    // setInternal is intentionally omitted: it's re-created each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSplit, internal.orderWrittenBy])

  return (
    <section className="section internal-use">
      <h2>Internal Use</h2>
      <div className="internal-grid">
        <fieldset className="inline-radios">
          <legend>New or reorder (optional)</legend>
          <label>
            <input
              type="radio"
              name="newOrReorder"
              checked={internal.newOrReorder === 'new'}
              onChange={() => setInternal('newOrReorder', 'new')}
            />
            New
          </label>
          <label>
            <input
              type="radio"
              name="newOrReorder"
              checked={internal.newOrReorder === 'reorder'}
              onChange={() => setInternal('newOrReorder', 'reorder')}
            />
            Reorder
          </label>
        </fieldset>

        <fieldset className="inline-radios">
          <legend>Account*</legend>
          <label>
            <input
              type="radio"
              name="accountStatus"
              checked={internal.accountStatus === 'new'}
              onChange={() => setInternal('accountStatus', 'new')}
            />
            New account
          </label>
          <label>
            <input
              type="radio"
              name="accountStatus"
              checked={internal.accountStatus === 'existing'}
              onChange={() => setInternal('accountStatus', 'existing')}
            />
            Existing
          </label>
        </fieldset>

        <fieldset className="inline-radios span2">
          <legend>Campaign (optional)</legend>
          <label>
            <input
              type="radio"
              name="campaign"
              checked={internal.campaign === 'rep-non-show'}
              onChange={() => setInternal('campaign', 'rep-non-show')}
            />
            Rep non-show order
          </label>
          <label>
            <input
              type="radio"
              name="campaign"
              checked={internal.campaign === 'other'}
              onChange={() => setInternal('campaign', 'other')}
            />
            Other:
          </label>
          <input
            type="text"
            className="campaign-other"
            value={internal.campaignOther}
            onChange={(e) => setInternal('campaignOther', e.target.value)}
            disabled={internal.campaign !== 'other'}
          />
        </fieldset>

        <label>
          PO # (optional)
          <input type="text" value={internal.poNumber} onChange={(e) => setInternal('poNumber', e.target.value)} />
        </label>
        <label>
          Order written by*
          <select
            value={internal.orderWrittenBy}
            onChange={(e) => setInternal('orderWrittenBy', e.target.value)}
            required
          >
            <option value="">Select a rep…</option>
            {repOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        
        {/* <label>
          Rep*
          <select
            value={internal.rep}
            onChange={(e) => setInternal('rep', e.target.value)}
            disabled={!isSplit}
          >
            <option value="">Select a rep…</option>
            {repOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label> */}

        <fieldset className="inline-radios">
          <legend>Split?</legend>
          <label>
            <input
              type="radio"
              name="split"
              checked={internal.split === true}
              onChange={() => setInternal('split', true)}
            />
            Y
          </label>
          <label>
            <input
              type="radio"
              name="split"
              checked={internal.split === false}
              onChange={() => setInternal('split', false)}
            />
            N
          </label>
          <select
            className="split-with"
            value={internal.splitWith}
            onChange={(e) => setInternal('splitWith', e.target.value)}
            disabled={!isSplit}
          >
            <option value="">Split with…</option>
            {repOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </fieldset>

      </div>
    </section>
  )
}
