import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // During development, Vite serves the React app at http://localhost:5173 and Flask runs
    // separately at http://127.0.0.1:5000. This "proxy" passes any /api/... request from the
    // React app on to Flask, so the browser only ever talks to one address, just like in
    // production, where Flask serves everything. That means no cross-origin (CORS) setup.
    //
    // changeOrigin stays false (the default), so Flask sees the browser's real address in the
    // Host header. Flask's cross-site check compares that to the Origin header, and they match.
    proxy: {
      '/api': 'http://127.0.0.1:5000',
    },
  },
})
