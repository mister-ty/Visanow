import { useQuery, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, EVENTO_SESION_CERRADA, exigir, token, type Yo } from '../api/cliente'

interface Sesion {
  autenticado: boolean
  yo: Yo | undefined
  cargando: boolean
  /** Guarda el token recién emitido y carga el perfil. */
  entrar: (accessToken: string) => void
  /** Cierra la sesión en este navegador. */
  salir: (mensaje?: string, color?: string) => void
  /** La UI esconde lo que no se puede usar; quien decide es el backend. */
  puede: (permiso: string) => boolean
}

const Contexto = createContext<Sesion | null>(null)

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [autenticado, setAutenticado] = useState(() => token.leer() !== null)
  const clienteQuery = useQueryClient()
  const navegar = useNavigate()

  const yo = useQuery({
    queryKey: ['yo'],
    queryFn: () => exigir(api.GET('/api/v1/auth/yo')),
    enabled: autenticado,
    staleTime: 60_000,
  })

  const salir = useCallback(
    (mensaje?: string, color = 'yellow') => {
      token.borrar()
      setAutenticado(false)
      clienteQuery.clear()
      if (mensaje) notifications.show({ color, title: color === 'yellow' ? 'Sesión cerrada' : 'Listo', message: mensaje })
      navegar('/ingreso', { replace: true })
    },
    [clienteQuery, navegar],
  )

  const entrar = useCallback(
    (accessToken: string) => {
      token.guardar(accessToken)
      clienteQuery.removeQueries({ queryKey: ['yo'] })
      setAutenticado(true)
    },
    [clienteQuery],
  )

  // Cualquier 401 fuera del ingreso (sesión vencida, contraseña cambiada en otro
  // equipo, cuenta desactivada) llega aquí desde el cliente de la API.
  useEffect(() => {
    const alCerrar = (e: Event) => salir((e as CustomEvent<string | undefined>).detail ?? 'Ingrese de nuevo.')
    window.addEventListener(EVENTO_SESION_CERRADA, alCerrar)
    return () => window.removeEventListener(EVENTO_SESION_CERRADA, alCerrar)
  }, [salir])

  const valor = useMemo<Sesion>(
    () => ({
      autenticado,
      yo: yo.data,
      cargando: autenticado && yo.isPending,
      entrar,
      salir,
      puede: (permiso) => yo.data?.permisos.includes(permiso) ?? false,
    }),
    [autenticado, yo.data, yo.isPending, entrar, salir],
  )

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}

export function useSesion(): Sesion {
  const s = useContext(Contexto)
  if (!s) throw new Error('useSesion debe usarse dentro de ProveedorSesion')
  return s
}
