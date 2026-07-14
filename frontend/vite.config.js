import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Local dev only — in production nginx does this proxying
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
})
