import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        // Order form (main SPA) + the standalone conflict-check tool.
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        conflict: fileURLToPath(new URL('./conflict.html', import.meta.url)),
      },
    },
  },
  server: {
    // Local dev only — in production nginx does this proxying
    proxy: {
      // Local dev: the wholesale API is served by the nginx container on :80
      // (:8080 on the host belongs to a different project).
      '/api': 'http://localhost:80',
    },
  },
})
