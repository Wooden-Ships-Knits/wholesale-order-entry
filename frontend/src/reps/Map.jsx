// The prospect map. Deliberately DUMB: it takes rows and draws them, and owns
// no session, no fetching and no filtering. Everything it shows is a prop, so
// the same component serves both the small card and the expanded view.
//
// Colours mirror the Python map (app/maps/prospecting.py::plot) on purpose —
// grey for stores we already sell to, yellow for prospects — so the folium HTML
// and this page read as one tool rather than two.

import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const FL_CENTER = [27.8, -81.7]
const FL_ZOOM = 6

const ACCOUNT = { color: '#6b7280', fillColor: '#9aa0a6', fillOpacity: 0.85, weight: 1, radius: 5 }
const PROSPECT = { color: '#8a6d1f', fillColor: '#f2c14e', fillOpacity: 0.9, weight: 1, radius: 6 }
// A prospect inside a stockist's catchment. Same yellow — it is still a
// prospect — but ringed, because "there is already a store nearby" is the one
// thing a rep must see before picking up the phone.
const CONFLICT = { ...PROSPECT, color: '#b9451d', weight: 2 }

const esc = (s) =>
  String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))

/** Popup body. Built as a string because Leaflet popups are plain DOM — there
 *  is no React tree inside the map, and rendering one per marker for ~900
 *  markers would cost far more than it returns. */
function popupHtml(p) {
  const bits = [`<strong>${esc(p.storeName)}</strong>`]
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

export default function Map({ prospects = [], accounts = [], expanded = false, focus = null }) {
  const elRef = useRef(null)
  const mapRef = useRef(null)
  const layersRef = useRef({ accounts: null, prospects: null })

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
      center: FL_CENTER,
      zoom: FL_ZOOM,
      scrollWheelZoom: false, // enabled only when expanded — see below
    })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      // Required by the OSM tile usage policy. Do not remove.
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
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

    accounts.forEach((a) => {
      if (a.latitude == null || a.longitude == null) return
      L.circleMarker([a.latitude, a.longitude], ACCOUNT)
        .bindPopup(`<div class="map-popup"><strong>${esc(a.name)}</strong><br/>current stockist</div>`)
        .addTo(aLayer)
    })

    prospects.forEach((p) => {
      if (p.latitude == null || p.longitude == null) return
      L.circleMarker([p.latitude, p.longitude], p.potentialConflict ? CONFLICT : PROSPECT)
        .bindPopup(popupHtml(p))
        .addTo(pLayer)
    })
  }, [prospects, accounts])

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

  // Clicking a table row flies the map to that store.
  useEffect(() => {
    if (!focus || !mapRef.current) return
    if (focus.latitude == null || focus.longitude == null) return
    mapRef.current.flyTo([focus.latitude, focus.longitude], 13, { duration: 0.6 })
  }, [focus])

  return <div ref={elRef} className="prospect-map" />
}
