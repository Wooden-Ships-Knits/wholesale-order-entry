import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Single entry (index.html): /order_form, /admin and /check-conflict are
  // routed client-side in src/main.jsx and served by the nginx SPA fallback.
  server: {
    // Let a cloudflared quick tunnel reach the dev server. Vite rejects
    // unknown Host headers by default; the leading dot matches any subdomain.
    // Dev only — production is served by nginx, which ignores this file.
    allowedHosts: ['.trycloudflare.com'],
    // Local dev only — in production nginx does this proxying
    proxy: {
      // Local dev: the wholesale API is served by the nginx container, which
      // publishes on host :8082 (:80/:8080 belong to other projects — see the
      // "align local port with VM" change in docker-compose.yml).
      '/api': 'http://localhost:8082',
    },
  },
})
