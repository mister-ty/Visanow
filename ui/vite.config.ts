import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, /api y /admin se reenvían a la API local: el navegador ve un
// solo origen y no hace falta CORS. En Vercel la dirección de la API la da
// VITE_API_URL (ver .env.example).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/admin': 'http://127.0.0.1:8000',
    },
  },
})
