export default function InternalUse({ internal, setInternal, certOnFile, setCertOnFile }) {
  return (
    <section className="section internal-use">
      <h2>Internal Use</h2>
      <div className="internal-grid">
        <fieldset className="inline-radios">
          <legend>New or reorder</legend>
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
          <legend>Account</legend>
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
          <legend>Campaign</legend>
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
          PO #
          <input type="text" value={internal.poNumber} onChange={(e) => setInternal('poNumber', e.target.value)} />
        </label>
        <label>
          Rep
          <input type="text" value={internal.rep} onChange={(e) => setInternal('rep', e.target.value)} />
        </label>
        <label>
          Order written by
          <input
            type="text"
            value={internal.orderWrittenBy}
            onChange={(e) => setInternal('orderWrittenBy', e.target.value)}
          />
        </label>

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
          <input
            type="text"
            className="split-with"
            placeholder="with…"
            value={internal.splitWith}
            onChange={(e) => setInternal('splitWith', e.target.value)}
            disabled={internal.split !== true}
          />
        </fieldset>

        <label className="check span2">
          <input type="checkbox" checked={certOnFile} onChange={(e) => setCertOnFile(e.target.checked)} />
          Certificate on file
        </label>
      </div>
    </section>
  )
}
