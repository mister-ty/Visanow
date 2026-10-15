import type { Esquemas } from '../api/cliente'

/**
 * De dónde viene un trámite (RF-021): los tres valores, con su nombre y su color.
 *
 * Viven en un solo lugar porque las dos pantallas que los muestran los
 * colapsaban en dos: la lista preguntaba `fuente === 'manual'` y la ficha
 * `fuente !== 'manual'`, así que un trámite híbrido se rotulaba «SaaS» y nunca
 * se veía como lo que es —abierto a mano aquí y amarrado al SaaS después—, que
 * es justo lo que hay que saber para entender por qué hay datos que ninguna
 * importación va a traer.
 *
 * El tipo sale del esquema generado: si algún día el backend agrega un cuarto
 * origen, el typecheck se cae aquí en vez de pintarlo en blanco en la pantalla.
 */
export type Origen = Esquemas['CasoSalida']['fuente']

export const ORIGEN: Record<Origen, { nombre: string; color: string }> = {
  manual: { nombre: 'Manual', color: 'gray' },
  saas: { nombre: 'SaaS', color: 'blue' },
  hibrido: { nombre: 'Híbrido', color: 'grape' },
}

export const OPCIONES_ORIGEN = (Object.keys(ORIGEN) as Origen[])
  .map((valor) => ({ value: valor, label: ORIGEN[valor].nombre }))
