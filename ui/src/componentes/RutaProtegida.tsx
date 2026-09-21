import { Center, Loader } from '@mantine/core'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSesion } from '../auth/sesion'

/** Deja pasar solo con sesión, y obliga al orden que exige el backend:
 *  primero cambiar la contraseña temporal, después activar el doble factor.
 *  Si se saltara, el backend respondería 403 en todo lo demás. */
export function RutaProtegida() {
  const { autenticado, yo, cargando } = useSesion()
  const { pathname } = useLocation()

  if (!autenticado) return <Navigate to="/ingreso" replace />
  if (cargando || !yo) return <Center h="100vh"><Loader color="teal" /></Center>

  if (yo.debe_cambiar_password && pathname !== '/cambiar-contrasena') {
    return <Navigate to="/cambiar-contrasena" replace />
  }
  if (!yo.debe_cambiar_password && yo.mfa_requerido && pathname !== '/doble-factor') {
    return <Navigate to="/doble-factor" replace />
  }
  return <Outlet />
}
