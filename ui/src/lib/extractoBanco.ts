import type { Esquemas } from '../api/cliente'
import { aFecha } from './excelSaas'

export type MovimientoExtracto = Esquemas['MovimientoEntrada']

export type CampoExtracto = 'fecha' | 'valor' | 'descripcion' | 'referencia'

export interface HojaExtracto {
  encabezados: string[]
  /** Filas crudas bajo el encabezado, con su número de fila en el archivo. */
  filas: { n: number; celdas: unknown[] }[]
}

const normalizar = (t: string) =>
  t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '')

// Pistas para sugerir el mapeo. No se conoce el formato de cada banco: esto solo
// adelanta el trabajo y la persona confirma o corrige antes de importar.
const PISTAS: Record<CampoExtracto, string[]> = {
  fecha: ['fecha'],
  valor: ['valor', 'monto', 'credito', 'abono', 'importe'],
  descripcion: ['descripcion', 'detalle', 'concepto', 'transaccion'],
  referencia: ['referencia', 'documento', 'nrodoc', 'comprobante', 'ref'],
}

export function sugerirColumnas(encabezados: string[]): Record<CampoExtracto, number | null> {
  const norm = encabezados.map(normalizar)
  const r = {} as Record<CampoExtracto, number | null>
  for (const campo of Object.keys(PISTAS) as CampoExtracto[]) {
    const i = norm.findIndex((h) => h && PISTAS[campo].some((p) => h.includes(p)))
    r[campo] = i >= 0 ? i : null
  }
  return r
}

/** Lee la primera hoja del extracto en el navegador. El archivo no sube. */
export async function leerHojaExtracto(archivo: File): Promise<HojaExtracto & { hoja: string }> {
  // Carga perezosa: la librería pesa mucho y casi nadie importa extractos.
  const XLSX = await import('xlsx')
  const libro = XLSX.read(await archivo.arrayBuffer(), { type: 'array' })
  const nombre = libro.SheetNames[0] ?? ''
  const hoja = libro.Sheets[nombre]
  if (!hoja) return { hoja: nombre, encabezados: [], filas: [] }
  const crudas = XLSX.utils.sheet_to_json<unknown[]>(hoja, { header: 1, raw: true, defval: null })
  // Algunos extractos traen titulares antes de la tabla: el encabezado es la
  // primera fila con al menos dos celdas llenas.
  const k = crudas.findIndex((r) => r.filter((c) => c !== null && String(c).trim() !== '').length >= 2)
  if (k < 0) return { hoja: nombre, encabezados: [], filas: [] }
  const ancho = Math.max(...crudas.slice(k).map((r) => r.length))
  const encabezados = Array.from({ length: ancho }, (_, i) => String(crudas[k][i] ?? '').trim() || `Columna ${i + 1}`)
  const filas = crudas.slice(k + 1)
    .map((celdas, j) => ({ n: k + j + 2, celdas }))
    .filter((f) => f.celdas.some((c) => c !== null && String(c).trim() !== ''))
  return { hoja: nombre, encabezados, filas }
}

/** «1.234.567,50», «1,234,567.50», «$ 500.000» o un número: todos a número.
 *  Con un solo separador seguido de exactamente tres cifras se toma como miles
 *  (500.000 son quinientos mil, no quinientos): es lo normal en pesos. */
export function aValor(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (v === null || v === undefined) return null
  let t = String(v).trim().replace(/[^\d.,-]/g, '')
  if (!/\d/.test(t)) return null
  const punto = t.lastIndexOf('.')
  const coma = t.lastIndexOf(',')
  if (punto >= 0 && coma >= 0) {
    // el último que aparece es el decimal
    t = coma > punto ? t.replace(/\./g, '').replace(',', '.') : t.replace(/,/g, '')
  } else if (punto >= 0 || coma >= 0) {
    const sep = punto >= 0 ? '.' : ','
    const partes = t.split(sep)
    t = partes.length > 2 || partes[1].length === 3 ? partes.join('') : partes.join('.')
  }
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

export interface ResultadoMapeo {
  movimientos: MovimientoExtracto[]
  /** Filas que no se mandan: sin fecha, sin valor, o con valor que no es una entrada. */
  descartadas: { n: number; motivo: string }[]
}

/** Arma los movimientos con el mapeo elegido. Solo entran los valores positivos:
 *  lo que sale del banco no se concilia contra pagos de clientes. */
export function armarMovimientos(
  hoja: HojaExtracto, mapa: Record<CampoExtracto, number | null>, banco: string,
): ResultadoMapeo {
  const movimientos: MovimientoExtracto[] = []
  const descartadas: ResultadoMapeo['descartadas'] = []
  const celda = (c: unknown[], campo: CampoExtracto) => (mapa[campo] === null ? null : c[mapa[campo]!])
  const texto = (v: unknown) => (v === null || v === undefined || String(v).trim() === '' ? null : String(v).trim())
  for (const { n, celdas } of hoja.filas) {
    // Solo el día: el movimiento no tiene hora, y recortar evita que un
    // «-05:00» de la conversión cambie el día en el servidor.
    const fecha = aFecha(celda(celdas, 'fecha'))?.slice(0, 10) ?? null
    const valor = aValor(celda(celdas, 'valor'))
    if (!fecha || !/^\d{4}-\d{2}-\d{2}$/.test(fecha)) { descartadas.push({ n, motivo: 'sin fecha legible' }); continue }
    if (valor === null) { descartadas.push({ n, motivo: 'sin valor legible' }); continue }
    if (valor <= 0) { descartadas.push({ n, motivo: 'no es una entrada de plata' }); continue }
    movimientos.push({
      fecha, valor, banco, moneda: 'COP', fila: n,
      descripcion: texto(celda(celdas, 'descripcion')),
      referencia: texto(celda(celdas, 'referencia')),
    })
  }
  return { movimientos, descartadas }
}
