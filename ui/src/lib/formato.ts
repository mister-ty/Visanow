// Fechas en la zona horaria del navegador (RN-10: se guardan con zona y se
// muestran en la del usuario). Dinero en pesos colombianos sin decimales.

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' })
const pesos = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 })

export const formatearFechaHora = (iso: string | null | undefined): string =>
  iso ? fechaHora.format(new Date(iso)) : '—'

export const formatearPesos = (valor: number | string | null | undefined): string =>
  valor === null || valor === undefined || valor === '' ? '—' : pesos.format(Number(valor))

export const NOMBRES_ROL: Record<string, string> = {
  administradora: 'Administradora',
  comercial: 'Comercial',
  operaciones: 'Operaciones',
  finanzas: 'Finanzas',
  apoyo_externo: 'Apoyo externo',
  solo_lectura: 'Solo lectura',
}

export const NOMBRES_ALCANCE: Record<string, string> = {
  todos: 'Todos los casos',
  asignados: 'Solo casos asignados',
  propios: 'Solo lo propio',
}
