import { notifications } from '@mantine/notifications'
import { ErrorApi } from '../api/cliente'

/** Muestra el mensaje del backend tal cual: ya viene en español y pensado para el usuario. */
export function mostrarError(e: unknown, titulo = 'No se pudo completar') {
  const mensaje = e instanceof ErrorApi
    ? (e.errores.length ? e.errores.map((x) => x.mensaje).join(' · ') : e.message)
    : 'No hay conexión con el servidor. Intente de nuevo en un momento.'
  notifications.show({ color: 'red', title: titulo, message: mensaje })
}

export const codigoDe = (e: unknown): string | undefined => (e instanceof ErrorApi ? e.codigo : undefined)

/** Misma política que el backend (app/core/seguridad.py → validar_politica). */
export function validarPassword(valor: string): string | null {
  if (valor.length < 10) return 'Debe tener al menos 10 caracteres.'
  if (!/[A-Za-zÁÉÍÓÚáéíóúÑñ]/.test(valor)) return 'Debe incluir al menos una letra.'
  if (!/\d/.test(valor)) return 'Debe incluir al menos un número.'
  return null
}
