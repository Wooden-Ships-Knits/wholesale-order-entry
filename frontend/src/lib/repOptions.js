// Names for a rep dropdown, from the sales order's Written_By__c picklist.
// A value auto-filled from Salesforce may no longer be in the picklist; prepend
// it so the select can still show it instead of falling back to a blank.
// Shared by InternalUse (which renders the dropdowns) and App (which needs the
// same list to decide whether a territory's rep is selectable for a Split).
export function repOptions(writers, current) {
  return current && !writers.includes(current) ? [current, ...writers] : writers
}
