// Fechas siempre en hora de Bogotá (RN-10: se guardan con zona y el negocio
// opera en America/Bogota), sin importar la zona del equipo de quien mira. Dinero en pesos colombianos sin decimales.

const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Bogota' })
const soloFecha = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeZone: 'America/Bogota' })
const pesos = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 })

export const formatearFechaHora = (iso: string | null | undefined): string =>
  iso ? fechaHora.format(new Date(iso)) : '—'

/** El día, sin la hora: para columnas donde la hora no dice nada —cuándo entró
 *  un trámite— y en cambio ocupa el ancho de la tabla. Sigue siendo el día de
 *  Bogotá: algo abierto a las 8 p. m. del 9 es del 9 y no del 10. */
export const formatearFecha = (iso: string | null | undefined): string =>
  iso ? soloFecha.format(new Date(iso)) : '—'

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

/** Convierte lo que entrega un <input type="datetime-local"> (hora de pared, sin
 *  zona) en un instante con la zona de Bogotá. Colombia no tiene horario de
 *  verano, así que -05:00 es fijo; sin esto el servidor, que corre en UTC,
 *  tomaría la hora cinco horas antes de lo que la persona escribió. */
export const aInstanteBogota = (local: string): string => `${local}:00-05:00`
