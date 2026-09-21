import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, /api y /admin se reenvían a la API local: el navegador ve un
// solo origen y no hace falta CORS. En Vercel la dirección de la API la da
// VITE_API_URL (ver .env.example).
export default defineConfig({
  plugins: [react()],
  server: {
    // 5173 (el de Vite por defecto) lo usa otro proyecto en esta máquina. Con
    // strictPort, si el puerto está ocupado Vite falla en vez de moverse en
    // silencio a otro puerto o, peor, dejar que el navegador abra la otra app.
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/admin': 'http://127.0.0.1:8000',
    },
  },
})
