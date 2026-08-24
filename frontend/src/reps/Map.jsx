// The prospect map. Deliberately DUMB: it takes rows and draws them, and owns
// no session, no fetching and no filtering. Everything it shows is a prop, so
// the same component serves both the small card and the expanded view.
//
// Colours mirror the Python map (app/maps/prospecting.py::plot) on purpose —
// grey for stores we already sell to, yellow for prospects — so the folium HTML
// and this page read as one tool rather than two. The verdict layer below is an
// addition the folium map has no equivalent for: it varies SIZE and OPACITY of
// the same yellow, never the hue, so "yellow means prospect" stays true.

import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// The whole lower 48. A rep's territory can be nine states, and several span
// the country — opening on one state meant most reps landed somewhere their
// dots were not. Alaska and Hawaii sit outside this; the search box or a chip
// gets there in one step, which is better than zooming out far enough to fit
// them and rendering everyone else too small to read.
const US_CENTER = [39.5, -98.35]
const US_ZOOM = 4

const ACCOUNT = { color: '#6b7280', fillColor: '#9aa0a6', fillOpacity: 0.85, weight: 1, radius: 5 }
// Midway between the folium map's acid '#f2ff01' and the softer '#f2c14e'
// this page started with: bright enough to carry against Positron's pale grey,
// not so bright it reads as a warning.
const PROSPECT = { color: '#ae8207', fillColor: '#f2e027', fillOpacity: 0.9, weight: 1, radius: 6 }
// A prospect inside a stockist's catchment. Same yellow — it is still a
// prospect — but ringed, because "there is already a store nearby" is the one
// thing a rep must see before picking up the phone.
const CONFLICT = { ...PROSPECT, color: '#b9451d', weight: 2 }

// How the assessment (app/prospects/assess.py) changes a dot. Size and opacity
// only — the stroke stays free to mean "conflict", which is the one thing a rep
// must see before phoning, and hue stays free to mean "prospect".
//
// A shop with NO verdict is drawn unchanged, at the base size. That is the
// honest default: it has not been assessed, which is different from having been
// assessed poorly, and shrinking it would state a finding nobody made.
const VERDICT = {
  strong: { radius: 9, fillOpacity: 1 },
  possible: { radius: 8, fillOpacity: 1 },
  weak: { radius: 4, fillOpacity: 0.4 },
  // Not "bad" — we could not read the shelf. Faded because there is nothing to
  // act on, not because the shop was judged and found wanting. 30 of the first
  // 92 landed here through scraper failure alone.
  insufficient_data: { radius: 4, fillOpacity: 0.25 },
}

/** Base style for a prospect: its conflict state, then its verdict. */
const prospectStyle = (p) => {
  const base = p.potentialConflict ? CONFLICT : PROSPECT
  const v = VERDICT[p.verdict]
  return v ? { ...base, ...v } : base
}

// When a city is selected, its stores grow and everything else fades rather
// than disappearing. Removing the others would lose the context that makes the
// answer useful — how this town compares with what surrounds it.
const HIGHLIGHT = 1.7 // radius multiplier for a store in the chosen city
const DIMMED = 0.18 // opacity for everything outside it

/** Circle style for one row, given whether a city filter is on and matched. */
const styleFor = (base, state) =>
  state === 'hit'
    ? { ...base, radius: base.radius * HIGHLIGHT }
    : state === 'dim'
      ? { ...base, fillOpacity: DIMMED, opacity: DIMMED, weight: 1 }
      : base

const esc = (s) =>
  String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))

/** Popup body. Built as a string because Leaflet popups are plain DOM — there
 *  is no React tree inside the map, and rendering one per marker for ~900
 *  markers would cost far more than it returns. */
const VERDICT_LABEL = {
  strong: 'Strong', possible: 'Possible', weak: 'Weak',
  insufficient_data: 'Couldn\u2019t read site',
}

function popupHtml(p) {
  const bits = [`<strong>${esc(p.storeName)}</strong>`]
  // Directly under the name: it is the answer the rep opened the dot for, and
  // burying it under the address would make the map a worse version of the
  // table rather than a different view of it.
  if (p.verdict) {
    const label = VERDICT_LABEL[p.verdict] || p.verdict
    bits.push(
      `<span class="popup-verdict verdict-${esc(p.verdict)}">${esc(label)}</span>` +
        (p.forTheRep ? `<br/>${esc(p.forTheRep)}` : ''),
    )
  }
  // judge.check() disagreed with the verdict above. The only marker saying the
  // answer is unchecked, so it cannot be left out of the map copy of it.
  if (p.problems) bits.push(`<span class="verdict-problem">\u26a0 unchecked: ${esc(p.problems)}</span>`)
  if (p.address) bits.push(esc(p.address))
  if (p.rating != null) bits.push(`★ ${esc(p.rating)}${p.reviewCount ? ` (${esc(p.reviewCount)})` : ''}`)
  if (p.phone) bits.push(esc(p.phone))
  if (p.website)
    bits.push(`<a href="${esc(p.website)}" target="_blank" rel="noreferrer">website</a>`)
  if (p.nearestStockist)
    // Rep-only information; see the serializer note in ProspectsPanel.
    bits.push(
      `<em>nearest stockist:</em> ${esc(p.nearestStockist)}` +
        (p.distanceMiles != null ? ` — ${esc(p.distanceMiles)} mi` : ''),
    )
  return `<div class="map-popup">${bits.join('<br/>')}</div>`
}

export default function Map({
  prospects = [],
  accounts = [],
  expanded = false,
  focus = null,
  highlightCity = null, // { name, bounds } — stores in this city stand out
  // Which circles to draw. Hiding a layer is a VIEW choice, not a filter: the
  // table still lists every row, so dropping the grey dots to read a crowded
  // high street does not change what the rep is working from.
  layers = { prospect: true, conflict: true, account: true },
}) {
  const elRef = useRef(null)
  const mapRef = useRef(null)
  const layersRef = useRef({ accounts: null, prospects: null })
  // id -> marker, so a search result can open the right popup. A plain object,
  // NOT a `new Map()`: this component is itself named Map, which shadows the
  // built-in inside this module.
  const markersRef = useRef({})

  // Create the map once. A second L.map() on the same element throws
  // "Map container is already initialized", which is what a naive effect
  // without this guard does on every re-render.
  useEffect(() => {
    if (mapRef.current) return
    const map = L.map(elRef.current, {
      // Canvas rather than one DOM node per marker: ~900 circles is where SVG
      // rendering starts to stutter on pan, and this is the same volume the
      // folium map struggled with.
      preferCanvas: true,
      center: US_CENTER,
      zoom: US_ZOOM,
      scrollWheelZoom: false, // enabled only when expanded — see below
    })
    // CartoDB Positron — the SAME basemap as the Python map
    // (prospecting.py::plot uses tiles="cartodbpositron"), so the folium HTML
    // and this page look like one tool. Chosen over greying OSM's standard
    // tiles with a CSS filter: Positron removes road and label clutter by
    // design rather than just desaturating it, which is what lets the markers
    // carry the page.
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      // Both attributions are required — OSM for the data, CARTO for the tiles.
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
        '&copy; <a href="https://carto.com/attributions">CARTO</a>',
    }).addTo(map)
    layersRef.current.accounts = L.layerGroup().addTo(map)
    layersRef.current.prospects = L.layerGroup().addTo(map)
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Redraw markers whenever the filtered rows change.
  useEffect(() => {
    const { accounts: aLayer, prospects: pLayer } = layersRef.current
    if (!aLayer || !pLayer) return
    aLayer.clearLayers()
    pLayer.clearLayers()
    markersRef.current = {}

    const city = highlightCity?.name?.trim().toLowerCase() || null
    // No city chosen -> everything normal. Otherwise a row is either in it or
    // faded. Matched on the row's own `city` field; see the note in
    // ProspectsPanel about why that is a text match.
    const stateOf = (row) =>
      !city ? 'normal' : (row.city || '').trim().toLowerCase() === city ? 'hit' : 'dim'

    if (layers.account) {
      accounts.forEach((a, i) => {
        if (a.latitude == null || a.longitude == null) return
        const m = L.circleMarker([a.latitude, a.longitude], styleFor(ACCOUNT, stateOf(a)))
          .bindPopup(`<div class="map-popup"><strong>${esc(a.name)}</strong><br/>current stockist</div>`)
          .addTo(aLayer)
        markersRef.current[`account:${i}`] = m
      })
    }

    prospects.forEach((p) => {
      if (p.latitude == null || p.longitude == null) return
      // Two prospect layers, toggled separately: "we already sell nearby" and
      // "we do not" are the two piles a rep sorts into, and being able to drop
      // one is most of the value of a legend.
      if (!(p.potentialConflict ? layers.conflict : layers.prospect)) return
      const m = L.circleMarker([p.latitude, p.longitude],
                               styleFor(prospectStyle(p), stateOf(p)))
        .bindPopup(popupHtml(p))
        .addTo(pLayer)
      // Highlighted pins should sit above the faded ones.
      if (stateOf(p) === 'hit') m.bringToFront()
      markersRef.current[p.id] = m
    })
  }, [prospects, accounts, highlightCity, layers])

  // Frame the chosen city on the bounds of the stores actually in it. No
  // boundary polygon is drawn: we do not have one, and a rectangle or a
  // convex hull would assert a city limit that does not exist. Real outlines
  // need admin_level=8 relations from Overpass — see the note in
  // ProspectsPanel.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !highlightCity?.bounds?.length) return
    map.fitBounds(L.latLngBounds(highlightCity.bounds), { padding: [28, 28], maxZoom: 13 })
  }, [highlightCity])

  // Leaflet caches the container's pixel size, so a container that changes size
  // without being told renders grey tiles and a wrong centre. This is THE bug
  // of expand-to-fullscreen maps. The frame waits for the CSS transition.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const t = setTimeout(() => {
      map.invalidateSize()
      // Wheel zoom only in the big view: in the small card it would hijack the
      // page scroll, which is infuriating on a long table.
      if (expanded) map.scrollWheelZoom.enable()
      else map.scrollWheelZoom.disable()
    }, 220)
    return () => clearTimeout(t)
  }, [expanded])

  // Selecting a row or a search result flies the map there and opens its popup,
  // so the answer is legible without hunting for which dot just moved. The
  // popup opens after the flight so Leaflet positions it at the final centre.
  useEffect(() => {
    if (!focus || !mapRef.current) return
    if (focus.latitude == null || focus.longitude == null) return
    mapRef.current.flyTo([focus.latitude, focus.longitude], 13, { duration: 0.6 })
    const marker = markersRef.current[focus.id]
    if (!marker) return
    const t = setTimeout(() => marker.openPopup(), 700)
    return () => clearTimeout(t)
  }, [focus])

  return <div ref={elRef} className="prospect-map" />
}
