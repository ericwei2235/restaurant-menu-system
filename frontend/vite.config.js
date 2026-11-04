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
    // changeOrigin must be false, so Flask sees the browser's real address in the Host header.
    // Flask's cross-site check compares that to the Origin header, and they have to match.
    // (Vite's short form, '/api': 'http://...', quietly turns changeOrigin ON, which rewrites the
    // Host header to Flask's own address and makes every admin login look like a cross-site request.)
    //
    // If Flask runs somewhere else (port 5000 is taken by AirPlay on many Macs, for example),
    // start Vite with API_URL set, e.g. API_URL=http://127.0.0.1:5050
    proxy: {
      '/api': {
        target: process.env.API_URL || 'http://127.0.0.1:5000',
        changeOrigin: false,
      },
    },
  },
})
