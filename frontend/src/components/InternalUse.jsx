import { useEffect } from 'react'
import { repOptions } from '../lib/repOptions'

export default function InternalUse({
  internal,
  setInternal,
  certOnFile,
  setCertOnFile,
  reps = [],
  writers = [],
  // { show, required, territoryRep } from lib/splitRules.js — Split only
  // applies when the order lands in another rep's territory.
  splitRule = { show: true, required: false, territoryRep: null },
  // Territory owners from the sheet (REGION col C). Deliberately NOT the
  // writers list: a split is between reps, and Written_By also contains people
  // who write orders on a rep's behalf.
  splitOptions = [],
}) {
  const writerOptions = repOptions(writers, internal.orderWrittenBy)
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
          <legend>
            New or reorder<span className="req">*</span>
          </legend>
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
          <legend>
            Account<span className="req">*</span>
          </legend>
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

        <fieldset className="inline-radios campaign-field">
          <legend>
            Campaign<span className="req">*</span>
          </legend>
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
          Order written by<span className="req">*</span>
          <select
            value={internal.orderWrittenBy}
            onChange={(e) => setInternal('orderWrittenBy', e.target.value)}
            required
          >
            <option value="">Select a rep…</option>
            {writerOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>

        {/* Pinned to the third column so it sits on the right of the row,
            opposite "Order written by" — auto-flow would put it in column 2.
            Hidden entirely when the writer's rep owns this territory: there is
            no one to split with. */}
        {splitRule.show && (
        <fieldset className="inline-radios split-field">
          <legend>
            Split?{splitRule.required && <span className="req">*</span>}
          </legend>
          {splitRule.required && (
            <p className="split-note">In {splitRule.territoryRep}&rsquo;s territory</p>
          )}
          {/* Locked once the rule fills it in: the territory decides who the
              order is split with, so the answer is shown, not asked for. Left
              editable in the optional case, where nothing was filled in. */}
          <label className={splitRule.required ? 'field-disabled' : undefined}>
            <input
              type="radio"
              name="split"
              checked={internal.split === true}
              onChange={() => setInternal('split', true)}
              disabled={splitRule.required}
            />
            Y
          </label>
          <label className={splitRule.required ? 'field-disabled' : undefined}>
            <input
              type="radio"
              name="split"
              checked={internal.split === false}
              onChange={() => setInternal('split', false)}
              disabled={splitRule.required}
            />
            N
          </label>
          <select
            className="split-with"
            value={internal.splitWith}
            onChange={(e) => setInternal('splitWith', e.target.value)}
            disabled={!isSplit || splitRule.required}
          >
            <option value="">Split with…</option>
            {splitOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </fieldset>
        )}

        {/* <label>
          Rep*
          <select
            value={internal.rep}
            onChange={(e) => setInternal('rep', e.target.value)}
            disabled={!isSplit}
          >
            <option value="">Select a rep…</option>
            {writerOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label> */}

      </div>
    </section>
  )
}
