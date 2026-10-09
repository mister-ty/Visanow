import * as XLSX from 'xlsx'
import type { Esquemas } from '../api/cliente'

export type FilaSaas = Esquemas['FilaEntrada']

// Los encabezados del export del SaaS, normalizados (sin tildes, ni símbolos,
// ni mayúsculas) para que «N° Solicitud» y «N Solicitud» sean lo mismo.
const COLUMNAS: Record<string, keyof FilaSaas> = {
  nsolicitud: 'numero_solicitud',
  solicitante: 'solicitante',
  pasaporte: 'pasaporte',
  etapaactual: 'etapa',
  fechacreacion: 'fecha_creacion',
  fechadeenviods160: 'ds160_enviado_en',
  nds160: 'ds160_numero',
  busquedadecitas: 'busqueda_citas',
}

const ENCABEZADOS: Record<keyof FilaSaas, string> = {
  numero_solicitud: 'N° Solicitud', solicitante: 'Solicitante', pasaporte: 'Pasaporte',
  etapa: 'Etapa actual', fecha_creacion: 'Fecha Creacion', ds160_enviado_en: 'Fecha de envio DS-160',
  ds160_numero: 'N° DS-160', busqueda_citas: 'Busqueda de citas', fila: 'Fila',
}

const normalizar = (t: string) =>
  t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '')

const dos = (n: number) => String(n).padStart(2, '0')

// Excel guarda las fechas como días desde 1899-12-30. Se leen como número y se
// arman con getters UTC: pasar por la zona del navegador correría el día.
// La hora, si la hay, es hora de pared de Bogotá y viaja con su desfase -05:00
// (sin horario de verano) para que el servidor, en UTC, no la tome cinco horas antes.
function aFecha(v: unknown): string | null {
  if (v === null || v === undefined || v === '') return null
  let fecha: Date | null = null
  if (typeof v === 'number') fecha = new Date(Math.round((v - 25569) * 86400 * 1000))
  else if (v instanceof Date) fecha = v
  else {
    const t = String(v).trim()
    // dd/mm/aaaa [hh:mm]: el formato con que se escribe en Colombia
    const m = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:[ T](\d{1,2}):(\d{2}))?/.exec(t)
    if (m) {
      const f = `${m[3]}-${dos(+m[2])}-${dos(+m[1])}`
      return m[4] ? `${f}T${dos(+m[4])}:${m[5]}:00-05:00` : f
    }
    return t // ya viene ISO, o el servidor dirá que no la entiende
  }
  if (Number.isNaN(fecha.getTime())) return null
  const dia = `${fecha.getUTCFullYear()}-${dos(fecha.getUTCMonth() + 1)}-${dos(fecha.getUTCDate())}`
  const conHora = fecha.getUTCHours() + fecha.getUTCMinutes() + fecha.getUTCSeconds() > 0
  return conHora ? `${dia}T${dos(fecha.getUTCHours())}:${dos(fecha.getUTCMinutes())}:${dos(fecha.getUTCSeconds())}-05:00` : dia
}

const aTexto = (v: unknown): string | null => {
  if (v === null || v === undefined) return null
  const t = String(v).trim()
  return t === '' ? null : t
}

export interface LecturaSaas {
  filas: FilaSaas[]
  /** Columnas esperadas que el archivo no trae: avisar antes de mandar nada. */
  faltantes: string[]
}

/** Lee el Excel del SaaS en el navegador: el archivo no sube al servidor, solo
 *  las filas ya leídas, que es lo que el backend espera (RF-033). */
export async function leerExcelSaas(archivo: File): Promise<LecturaSaas> {
  const libro = XLSX.read(await archivo.arrayBuffer(), { type: 'array' })
  const hoja = libro.Sheets[libro.SheetNames[0]]
  if (!hoja) return { filas: [], faltantes: Object.values(COLUMNAS).map((c) => ENCABEZADOS[c]) }
  // raw: las fechas llegan como número de serie y se convierten arriba
  const crudas = XLSX.utils.sheet_to_json<unknown[]>(hoja, { header: 1, raw: true, defval: null })
  const encabezado = (crudas[0] ?? []).map((c) => normalizar(String(c ?? '')))
  const indice = new Map<keyof FilaSaas, number>()
  encabezado.forEach((h, i) => {
    const campo = COLUMNAS[h]
    if (campo && !indice.has(campo)) indice.set(campo, i)
  })
  const faltantes = Object.values(COLUMNAS).filter((c) => !indice.has(c)).map((c) => ENCABEZADOS[c])

  const filas: FilaSaas[] = []
  crudas.slice(1).forEach((r, k) => {
    if (r.every((c) => c === null || String(c).trim() === '')) return
    const v = (c: keyof FilaSaas) => (indice.has(c) ? r[indice.get(c)!] : null)
    filas.push({
      numero_solicitud: aTexto(v('numero_solicitud')),
      solicitante: aTexto(v('solicitante')),
      pasaporte: aTexto(v('pasaporte')),
      etapa: aTexto(v('etapa')),
      fecha_creacion: aFecha(v('fecha_creacion')),
      ds160_enviado_en: aFecha(v('ds160_enviado_en')),
      ds160_numero: aTexto(v('ds160_numero')),
      busqueda_citas: aTexto(v('busqueda_citas')),
      fila: k + 2, // fila del archivo: 1 es el encabezado
    })
  })
  return { filas, faltantes }
}
