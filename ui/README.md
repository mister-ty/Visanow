# visanow-ui

Frontend de VisaNow: React + Vite + TypeScript + Mantine + TanStack Query.

```bash
npm install
npm run dev        # http://localhost:5173 — /api y /admin se reenvían a la API local (:8000)
npm run gen:api    # regenera src/api/esquema.d.ts desde el OpenAPI de la API (debe estar corriendo)
npm run build      # tsc + vite build → dist/
```

Los tipos de la API (`src/api/esquema.d.ts`) se generan del contrato de FastAPI: si el
backend cambia una ruta o un campo, el frontend deja de compilar hasta regenerarlos.

## Vercel

`vercel.json` ya trae la regla para que las rutas del navegador caigan en `index.html` y
las cabeceras de seguridad. En el proyecto de Vercel hay que definir:

- **Root directory:** `ui`
- **Variable de entorno:** `VITE_API_URL` = URL pública de la API, sin barra final

Y en la API, agregar el dominio de Vercel a `CORS_ORIGINS`.
