// Loads the Google Maps JS SDK once and shares the same promise across callers.
let mapsPromise = null

export function loadGoogleMaps(apiKey) {
  if (mapsPromise) return mapsPromise
  mapsPromise = new Promise((resolve, reject) => {
    if (window.google?.maps) {
      resolve(window.google.maps)
      return
    }
    const script = document.createElement('script')
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places`
    script.async = true
    script.onload = () => resolve(window.google.maps)
    script.onerror = () => reject(new Error('Failed to load Google Maps (check the API key and that Maps JavaScript API is enabled).'))
    document.head.appendChild(script)
  })
  return mapsPromise
}
