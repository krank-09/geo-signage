import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const backend = process.env.BACKEND_URL || 'http://localhost:8000'

// In dev, Vite would answer /display/ with the dashboard; nginx does the right thing in production. Serve the phone display's page here too.
const phoneDisplay = { name: 'phone-display-index', configureServer(server: { middlewares: { use: (fn: (req: { url?: string }, res: unknown, next: () => void) => void) => void } }) {
  server.middlewares.use((req, _res, next) => { if (/^\/display\/?(\?.*)?$/.test(req.url ?? '')) req.url = '/display/index.html'; next() })
} }

export default defineConfig({
  plugins: [react(), tailwindcss(), phoneDisplay],
  server: {
    port: 3000,
    proxy: {
      '/api': { target: backend, changeOrigin: true, ws: true, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
