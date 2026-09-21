import createClient, { type Middleware } from 'openapi-fetch'
import type { components, paths } from './esquema'

export type Esquemas = components['schemas']
export type Yo = Esquemas['YoSalida']
export type Usuario = Esquemas['UsuarioSalida']
export type Rol = Esquemas['RolSalida']

const CLAVE_TOKEN = 'visanow.token'

// sessionStorage y no localStorage: la sesión sobrevive a recargar la página
// pero muere al cerrar la pestaña. En un equipo compartido de la oficina no
// queda una sesión abierta para el siguiente que se siente.
export const token = {
  leer: (): string | null => sessionStorage.getItem(CLAVE_TOKEN),
  guardar: (t: string) => sessionStorage.setItem(CLAVE_TOKEN, t),
  borrar: () => sessionStorage.removeItem(CLAVE_TOKEN),
}

/** Error de la API con el formato que devuelve el backend: {detalle, codigo}. */
export class ErrorApi extends Error {
  readonly estado: number
  readonly codigo: string
  readonly errores: { campo: string; mensaje: string }[]

  constructor(estado: number, cuerpo: unknown) {
    const c = (cuerpo ?? {}) as { detalle?: string; codigo?: string; errores?: ErrorApi['errores'] }
    super(c.detalle ?? `Error ${estado}`)
    this.estado = estado
    this.codigo = c.codigo ?? 'desconocido'
    this.errores = c.errores ?? []
  }
}

// Las rutas de ingreso responden 401 como parte normal del flujo; cualquier
// otro 401 significa que la sesión venció o se cerró.
const RUTAS_DE_INGRESO = ['/auth/login', '/auth/mfa/verificar', '/auth/recuperar', '/auth/restablecer']
export const EVENTO_SESION_CERRADA = 'visanow:sesion-cerrada'

const autenticacion: Middleware = {
  onRequest({ request }) {
    const t = token.leer()
    if (t) request.headers.set('Authorization', `Bearer ${t}`)
    return request
  },
  async onResponse({ request, response }) {
    if (response.status === 401 && !RUTAS_DE_INGRESO.some((r) => request.url.includes(r))) {
      const cuerpo = await response.clone().json().catch(() => ({}))
      token.borrar()
      window.dispatchEvent(new CustomEvent(EVENTO_SESION_CERRADA, { detail: cuerpo?.detalle }))
    }
    return response
  },
}

export const api = createClient<paths>({ baseUrl: import.meta.env.VITE_API_URL ?? '' })
api.use(autenticacion)

/** Convierte la respuesta de openapi-fetch en dato o excepción, para TanStack Query. */
export async function exigir<T>(promesa: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promesa
  if (!response.ok) throw new ErrorApi(response.status, error)
  return data as T
}

/** URL absoluta de la administración de catálogos (la sirve la API, no el frontend). */
export const urlAdministracion = `${import.meta.env.VITE_API_URL ?? ''}/admin`
