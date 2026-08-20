// TEMPORARY — delete this file once /api/reps-portal/prospects exists.
//
// Synthetic data, NOT the real sweep. The reps bundle is served before sign-in,
// so anything embedded here is readable by anyone who loads /reps — which rules
// out shipping real prospect rows, and especially rules out real values of
// `nearestStockist`, which names our own accounts (see CLAUDE.md: stockist
// names are internal). Shapes and volumes match the real thing so the UI is
// exercised honestly; the names are invented.

const WORDS_A = ['Coastal', 'Palm', 'Harbour', 'Sandbar', 'Willow', 'Indigo', 'Marlin',
  'Seagrape', 'Bayside', 'Driftwood', 'Cypress', 'Mango', 'Pelican', 'Coral', 'Sunfish']
const WORDS_B = ['Boutique', 'Threads', 'Collective', 'Studio', 'Trading Co', 'Apparel',
  'Closet', 'Room', 'Market', 'Loft']
const CITIES = ['Miami', 'Naples', 'Sarasota', 'Tampa', 'Orlando', 'Jacksonville',
  'Key West', 'Vero Beach', 'Fort Myers', 'Tallahassee']

// Deterministic PRNG so the mock looks identical on every reload — a mock that
// reshuffles makes it impossible to tell a UI bug from new data.
function rng(seed) {
  let s = seed
  return () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff)
}

function build() {
  const r = rng(20260815)
  const pick = (arr) => arr[Math.floor(r() * arr.length)]

  const accounts = Array.from({ length: 28 }, (_, i) => ({
    name: `${pick(WORDS_A).toUpperCase()} ${pick(WORDS_B).toUpperCase()}`,
    latitude: 25.4 + r() * 5.2,
    longitude: -82.4 + r() * 2.6,
    __i: i,
  }))

  const prospects = Array.from({ length: 140 }, (_, i) => {
    const conflict = r() < 0.62
    const hasSite = r() < 0.55
    const rated = r() < 0.7
    return {
      id: `node/${100000 + i}`,
      storeName: `${pick(WORDS_A)} ${pick(WORDS_B)}`,
      latitude: 25.4 + r() * 5.2,
      longitude: -82.4 + r() * 2.6,
      city: pick(CITIES),
      address: `${100 + Math.floor(r() * 800)} Main St`,
      website: hasSite ? 'https://example.com' : null,
      phone: r() < 0.4 ? `(850) 555-0${100 + Math.floor(r() * 800)}` : null,
      rating: rated ? Math.round((3.2 + r() * 1.8) * 10) / 10 : null,
      reviewCount: rated ? Math.floor(r() * 300) : null,
      womenswear: r() < 0.2,
      potentialConflict: conflict,
      nearestStockist: accounts[Math.floor(r() * accounts.length)].name,
      distanceMiles: Math.round((conflict ? r() * 10 : 10 + r() * 40) * 10) / 10,
      driveMinutes: null,
      marked: false,
    }
  })

  return {
    prospects,
    accounts: accounts.map(({ __i, ...a }) => a),
    counts: {
      total: prospects.length,
      noConflict: prospects.filter((p) => !p.potentialConflict).length,
      marked: 0,
    },
  }
}

export default build
