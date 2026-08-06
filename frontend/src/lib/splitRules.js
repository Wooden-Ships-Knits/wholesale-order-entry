// Split rule for the order form.
//
// Every "Written By" name belongs to exactly one sales rep, and every Sales
// Territory is owned by a rep. When an order is written by someone from one
// rep's team but lands in another rep's territory, the two reps split it.
//
// The comparison is always rep vs rep — never the writer's own name, since
// several writers map to one rep (Julie Mandell and Maxey Zipperer both belong
// to Rande Cohen).
//
// Neither side is hardcoded; both come from the region/rep Google Sheet, so the
// sales team maintains them without a deploy:
//   writer  -> rep : 'Split' tab,  via GET /api/writer-reps
//   state   -> rep : REGION col C, via GET /api/territory?state=XX
//
// The territory's rep is looked up from the Ship To state, NOT parsed out of
// the Sales Territory label. An existing account's label comes from Salesforce
// and often names a showroom rather than a rep ("Mountain - Taylor & Denise"),
// and 31 of the 42 labels in use are absent from the sheet entirely.

/** The rep a "Written By" name belongs to, per the sheet's Split tab. */
export function repForWriter(writer, writerReps) {
  return (writerReps && writerReps[String(writer || '').trim()]) || null
}

/**
 * Whether the Split field applies, and what it should default to.
 *
 * @param orderWrittenBy  the selected "Written By" name
 * @param territoryRep    rep who owns the Ship To state's territory, from
 *                        GET /api/territory (REGION column C)
 * @param writerReps      writer -> rep map from /api/writer-reps
 * @param splitOptions    names selectable in the "Split with" dropdown
 * @returns {{show, required, defaultSplitWith, writerRep, territoryRep}}
 *
 * Rules:
 *   same rep            -> hidden, not required (nothing to split)
 *   different reps      -> shown, required, territory's rep preselected
 *   territory has no rep-> shown, optional, nothing preselected
 *   rep not selectable  -> shown, optional (it could not be preselected anyway;
 *                          "House" arrives here, being no one in the picklist)
 *   writer unmapped     -> shown, optional (fails open; a missing sheet row or
 *                          an unreachable sheet must never block an order)
 */
export function updateSplitRequirement({
  orderWrittenBy,
  territoryRep,
  writerReps,
  splitOptions = [],
}) {
  const writerRep = repForWriter(orderWrittenBy, writerReps)
  const optional = { show: true, required: false, defaultSplitWith: '', writerRep, territoryRep }

  if (!writerRep || !territoryRep) return optional
  if (writerRep === territoryRep) {
    return { show: false, required: false, defaultSplitWith: '', writerRep, territoryRep }
  }
  if (!splitOptions.includes(territoryRep)) return optional

  return { show: true, required: true, defaultSplitWith: territoryRep, writerRep, territoryRep }
}
