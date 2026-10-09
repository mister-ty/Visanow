import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'

import { createTheme, MantineProvider } from '@mantine/core'
import { ModalsProvider } from '@mantine/modals'
import { Notifications } from '@mantine/notifications'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Outlet, RouterProvider } from 'react-router-dom'
import { ErrorApi } from './api/cliente'
import { ProveedorSesion } from './auth/sesion'
import { EnConstruccion } from './componentes/EnConstruccion'
import { Plantilla } from './componentes/Plantilla'
import { RutaProtegida } from './componentes/RutaProtegida'
import { SECCIONES } from './navegacion'
import { Alertas } from './paginas/Alertas'
import { CambiarContrasena } from './paginas/CambiarContrasena'
import { CasoFicha } from './paginas/CasoFicha'
import { Casos } from './paginas/Casos'
import { ClienteFicha } from './paginas/ClienteFicha'
import { Embudo } from './paginas/Embudo'
import { Clientes } from './paginas/Clientes'
import { Configuracion } from './paginas/Configuracion'
import { DobleFactor } from './paginas/DobleFactor'
import { Inicio } from './paginas/Inicio'
import { Ingreso } from './paginas/Ingreso'
import { Pagos } from './paginas/Pagos'
import { NoEncontrada } from './paginas/NoEncontrada'
import { Plantillas } from './paginas/Plantillas'
import { Tableros } from './paginas/Tableros'
import { Tareas } from './paginas/Tareas'
import { Recuperar, Restablecer } from './paginas/Recuperacion'
import { Usuarios } from './paginas/Usuarios'

const tema = createTheme({
  primaryColor: 'teal',
  defaultRadius: 'md',
  fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
})

const clienteQuery = new QueryClient({
  defaultOptions: {
    queries: {
      // Un 401/403/404 no se arregla reintentando
      retry: (intentos, e) => !(e instanceof ErrorApi && e.estado < 500) && intentos < 2,
      refetchOnWindowFocus: false,
    },
  },
})

const Raiz = () => (
  <ProveedorSesion>
    <Outlet />
  </ProveedorSesion>
)

const enruta = createBrowserRouter([
  {
    element: <Raiz />,
    children: [
      { path: '/ingreso', element: <Ingreso /> },
      { path: '/recuperar', element: <Recuperar /> },
      { path: '/restablecer', element: <Restablecer /> },
      {
        element: <RutaProtegida />,
        children: [
          { path: '/cambiar-contrasena', element: <CambiarContrasena /> },
          { path: '/doble-factor', element: <DobleFactor /> },
          {
            element: <Plantilla />,
            children: [
              { path: '/', element: <Inicio /> },
              { path: '/casos', element: <Casos /> },
              { path: '/casos/:id', element: <CasoFicha /> },
              { path: '/embudo', element: <Embudo /> },
              { path: '/clientes', element: <Clientes /> },
              { path: '/clientes/:id', element: <ClienteFicha /> },
              { path: '/pagos', element: <Pagos /> },
              { path: '/tareas', element: <Tareas /> },
              { path: '/alertas', element: <Alertas /> },
              { path: '/tableros', element: <Tableros /> },
              { path: '/mensajes', element: <Plantillas /> },
              { path: '/usuarios', element: <Usuarios /> },
              { path: '/configuracion', element: <Configuracion /> },
              ...SECCIONES.filter((s) => s.pendiente).map((s) => ({
                path: s.ruta, element: <EnConstruccion seccion={s} />,
              })),
              { path: '*', element: <NoEncontrada /> },
            ],
          },
        ],
      },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider theme={tema} defaultColorScheme="light">
      <QueryClientProvider client={clienteQuery}>
        <ModalsProvider>
          <Notifications position="top-right" />
          <RouterProvider router={enruta} />
        </ModalsProvider>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
)
