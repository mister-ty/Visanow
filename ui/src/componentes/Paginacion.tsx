import { Group, Pagination, Text } from '@mantine/core'
import type { ReactNode } from 'react'
import { useRef, useState } from 'react'

/**
 * El pie de un listado, con su paginador (RNF-08).
 *
 * Vive acá y no copiado en cada pantalla porque el descuido que arregla era el
 * mismo en siete de las nueve: pedían `tamano: 100` fijo, nunca mandaban
 * `pagina`, no tenían control de páginas, y el pie imprimía el total de verdad.
 * Medido el 10/10, la pantalla de trámites mostraba 100 de 189 y anunciaba
 * «189 trámite(s)» debajo: no era que faltara una función, era que la pantalla
 * decía algo falso. Alguien que busca un trámite y no lo encuentra concluye que
 * no está, y vuelve a crearlo.
 *
 * El texto cambió a propósito: en vez de «189 pago(s)» dice «Mostrando 51–100
 * de 189 pago(s)». El total sigue estando, pero ya no se lee como si fuera lo
 * que hay en la tabla.
 */

/** Filas por página. Un solo número para todas las pantallas. */
export const TAMANO_PAGINA = 50

/**
 * La página en la que está el usuario, que vuelve a la primera cuando cambian
 * los filtros.
 *
 * Sin eso, quien está en la página 4 y escribe algo en el buscador se queda
 * mirando una tabla vacía: el filtro deja dos páginas de resultados y él sigue
 * pidiendo la cuarta. Es el mismo final que no encontrar nada, y no se
 * distingue.
 *
 * El `setPagina` durante el render es a propósito y es el patrón que recomienda
 * React para ajustar estado cuando cambia una entrada: se descarta el render en
 * curso y se vuelve a pintar de inmediato, sin el parpadeo de la página vieja
 * que dejaría un `useEffect`.
 */
export function usePagina(filtros: unknown) {
  const [pagina, setPagina] = useState(1)
  const clave = JSON.stringify(filtros)
  const anterior = useRef(clave)
  if (anterior.current !== clave) {
    anterior.current = clave
    if (pagina !== 1) setPagina(1)
  }
  return [pagina, setPagina] as const
}

/**
 * El aviso para las listas que NO se paginan: los buscadores.
 *
 * Un paginador dentro de un desplegable de búsqueda es la solución equivocada
 * —nadie pasa páginas en un combo, se escribe más— pero el problema de fondo es
 * el mismo: la lista se corta y hay que decirlo. El buscador de «quién
 * contrata» pedía las primeras 20 de casi novecientas personas y no avisaba,
 * así que buscar un apellido común mostraba 20 y el que faltaba parecía no
 * existir.
 *
 * Devuelve `undefined` cuando no hay nada que avisar, para poder pasarlo
 * directo a `description` de un Select sin dejar un renglón vacío.
 */
export function avisoDeCorte(total: number | undefined, mostrados: number,
                             unidad: string): string | undefined {
  if (total === undefined || total <= mostrados) return undefined
  return `Coinciden ${total} ${unidad}; se muestran ${mostrados}. Escriba más para afinar.`
}

export function PiePaginacion({ total, pagina, onPagina, unidad, tamano = TAMANO_PAGINA, extra }: {
  total: number | undefined
  pagina: number
  onPagina: (p: number) => void
  /** Cómo se llama lo que se está listando: «pago(s)», «trámite(s)». */
  unidad: string
  tamano?: number
  /** Lo que la pantalla quiera agregar al pie, como la suma de los montos. */
  extra?: ReactNode
}) {
  const cuantos = total ?? 0
  const paginas = Math.ceil(cuantos / tamano)
  const desde = cuantos === 0 ? 0 : (pagina - 1) * tamano + 1
  const hasta = Math.min(pagina * tamano, cuantos)

  return (
    <Group justify="space-between" wrap="nowrap">
      <Text size="sm" c="dimmed">
        {paginas > 1
          ? `Mostrando ${desde}–${hasta} de ${cuantos} ${unidad}`
          : `${cuantos} ${unidad}`}
        {extra}
      </Text>
      {paginas > 1 && (
        <Pagination value={pagina} onChange={onPagina} total={paginas} size="sm" />
      )}
    </Group>
  )
}
