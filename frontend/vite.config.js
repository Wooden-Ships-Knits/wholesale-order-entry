import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Local dev only — in production nginx does this proxying
    proxy: {
      // Local dev: the wholesale API is served by the nginx container on :80
      // (:8080 on the host belongs to a different project).
      '/api': 'http://localhost:80',
    },
  },
})
