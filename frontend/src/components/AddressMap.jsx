import { useEffect, useRef, useState } from 'react'
import { loadGoogleMaps } from '../lib/googleMaps'

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY

// Pull street / city-state / zip / coords out of a Places result.
function parsePlace(place) {
  const comp = (type, short = false) => {
    const c = place.address_components?.find((x) => x.types.includes(type))
    return c ? (short ? c.short_name : c.long_name) : ''
  }
  const street = [comp('street_number'), comp('route')].filter(Boolean).join(' ')
  const city = comp('locality') || comp('postal_town') || comp('sublocality')
  const state = comp('administrative_area_level_1', true)
  const loc = place.geometry?.location
  return {
    street,
    cityState: [city, state].filter(Boolean).join(', '),
    zip: comp('postal_code'),
    lat: loc?.lat(),
    lng: loc?.lng(),
  }
}

// Places search box for one address. Selecting a suggestion fills the address
// fields and captures lat/lng. UI-only: coordinates live in form state.
export default function AddressMap({ lat, lng, onPlaceSelect }) {
  const inputRef = useRef(null)
  const [status, setStatus] = useState('')

  // Keep the latest callback reachable from the once-initialised listener.
  const onPlaceSelectRef = useRef(onPlaceSelect)
  useEffect(() => {
    onPlaceSelectRef.current = onPlaceSelect
  })

  // Attach Places autocomplete to the input once.
  useEffect(() => {
    if (!API_KEY) {
      setStatus('Missing VITE_GOOGLE_MAPS_API_KEY in frontend/.env')
      return
    }
    let cancelled = false
    loadGoogleMaps(API_KEY)
      .then((maps) => {
        if (cancelled || !inputRef.current) return
        const autocomplete = new maps.places.Autocomplete(inputRef.current, {
          fields: ['address_components', 'geometry'],
        })
        autocomplete.addListener('place_changed', () => {
          const place = autocomplete.getPlace()
          if (!place.geometry) {
            setStatus('No details for that place')
            return
          }
          setStatus('')
          onPlaceSelectRef.current(parsePlace(place))
        })
      })
      .catch((e) => !cancelled && setStatus(e.message))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="address-map">
      <input ref={inputRef} className="map-search" placeholder="Type an address…" />
      {status && <span className="map-status">{status}</span>}
      {/* {lat != null && lng != null && (
        <div className="coords">
          Lat {lat.toFixed(6)}, Lng {lng.toFixed(6)}
        </div>
      )} */}
    </div>
  )
}
