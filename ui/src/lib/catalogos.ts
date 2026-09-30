import { useQuery } from '@tanstack/react-query'
import { api, exigir, type Esquemas } from '../api/cliente'

export type Opcion = Esquemas['Opcion']

/** Países, tipos de visa, sedes, modalidades y estados. Cambian muy poco:
 *  se piden una vez y quedan en caché mientras dure la sesión. */
export function useCatalogos() {
  return useQuery({
    queryKey: ['catalogos'],
    queryFn: () => exigir(api.GET('/api/v1/catalogos')),
    staleTime: Infinity,
  })
}

export function useAsignables() {
  return useQuery({
    queryKey: ['asignables'],
    queryFn: () => exigir(api.GET('/api/v1/usuarios/asignables')),
    staleTime: 5 * 60_000,
  })
}

/** Opciones para un Select de Mantine: value siempre texto. */
export const aSelect = (opciones: Opcion[] | undefined) =>
  (opciones ?? []).map((o) => ({ value: String(o.id), label: o.nombre }))

/** Los tipos de visa y las sedes se filtran por el país del trámite. */
export const porPais = (opciones: Opcion[] | undefined, paisId: number | null | undefined) =>
  (opciones ?? []).filter((o) => !paisId || o.pais_id === paisId)
