import { token } from '../api/cliente'

/**
 * Bajar un documento adjunto al computador de quien lo pide.
 *
 * Va por `fetch` y no por un `<a href>` porque el token de la sesión vive en
 * `sessionStorage`, no en una cookie: un enlace corriente no lo mandaría y el
 * servidor respondería 401. Y tampoco puede ir en la dirección, que queda
 * escrita en el historial del navegador y en los registros del servidor.
 *
 * Cada descarga queda registrada del otro lado con el nombre de quien se la
 * llevó: un archivo deja de estar bajo el control del sistema en cuanto sale.
 *
 * La dirección se arma con `VITE_API_URL`, igual que el resto del cliente de
 * API: en producción la pantalla vive en Vercel y la API en otro dominio, y
 * una ruta relativa iría a parar al propio frontend, que reescribe todo a
 * `index.html`. En desarrollo la variable está vacía y el proxy de Vite la
 * reenvía, así que queda igual que antes.
 */
export async function descargarDocumento(id: number, nombre: string): Promise<void> {
  const base = import.meta.env.VITE_API_URL ?? ''
  const r = await fetch(`${base}/api/v1/documentos/${id}/contenido`, {
    headers: { Authorization: `Bearer ${token.leer() ?? ''}` },
  })
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => ({}))
    throw new Error(cuerpo.detalle ?? `No se pudo descargar (${r.status})`)
  }
  const url = URL.createObjectURL(await r.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = nombre
  a.click()
  URL.revokeObjectURL(url)
}
