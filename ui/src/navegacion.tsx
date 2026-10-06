import {
  IconAddressBook, IconCalendarEvent, IconCash, IconChartBar, IconFilter, IconHome, IconMessage,
  IconPercentage, IconPlaneDeparture, IconSettings, IconUsers, type Icon,
} from '@tabler/icons-react'

export interface Seccion {
  ruta: string
  titulo: string
  icono: Icon
  /** Permiso para mostrarla en el menú. El backend es quien de verdad protege. */
  permiso?: string
  /** Si aún no está construida: qué va a tener y cuándo llega. */
  pendiente?: { actividad: string; fecha: string; desde: string; contenido: string[] }
}

// Las nueve pantallas mínimas de la sección 11 de la especificación, más la
// gestión de usuarios. El orden es el del trabajo diario, no el del cronograma.
export const SECCIONES: Seccion[] = [
  { ruta: '/', titulo: 'Mi trabajo', icono: IconHome },
  {
    ruta: '/clientes', titulo: 'Clientes', icono: IconAddressBook, permiso: 'clientes.ver',
  },
  {
    ruta: '/casos', titulo: 'Trámites', icono: IconPlaneDeparture, permiso: 'casos.ver',
  },
  {
    ruta: '/calendario', titulo: 'Calendario', icono: IconCalendarEvent, permiso: 'casos.ver',
    pendiente: {
      actividad: '2.5', fecha: '28/09', desde: '28/09',
      contenido: ['Citas CAS, biometría, entrevistas, preparaciones y entregas, con sede y zona horaria'],
    },
  },
  {
    ruta: '/embudo', titulo: 'Embudo comercial', icono: IconFilter,
    permiso: 'oportunidades.ver',
  },
  {
    ruta: '/pagos', titulo: 'Pagos y cartera', icono: IconCash, permiso: 'pagos.ver',
    pendiente: {
      actividad: '4.1 a 4.4', fecha: '07 y 08/10', desde: '07/10',
      contenido: [
        'Pagos ilimitados por venta, sin columnas Abono 1, 2, 3',
        'Saldo calculado solo, nunca digitado',
        'Anticipo del 20 % o del 80 %; el saldo vence a los 30 días',
        'Cartera por vencer, vencida y días de mora',
        'La tasa consular separada de lo vendido',
      ],
    },
  },
  {
    ruta: '/comisiones', titulo: 'Comisiones', icono: IconPercentage, permiso: 'comisiones.ver',
    pendiente: {
      actividad: '4.5', fecha: '09/10', desde: '09/10',
      contenido: ['Reglas por vendedor y servicio, congeladas al momento de la venta', 'Detalle de qué ventas componen cada total'],
    },
  },
  {
    ruta: '/tableros', titulo: 'Tableros', icono: IconChartBar, permiso: 'tableros.ver',
    pendiente: {
      actividad: '5.6 y 5.7', fecha: '15/10', desde: '15/10',
      contenido: [
        'Comercial: leads, conversión por canal y por vendedor',
        'Operativo: trámites por estado, antigüedad y riesgo',
        'Financiero: vendido, recaudado y cartera, por separado',
        'Exportación a Excel con los mismos filtros de la pantalla',
      ],
    },
  },
  { ruta: '/mensajes', titulo: 'Mensajes', icono: IconMessage, permiso: 'catalogos.editar' },
  { ruta: '/usuarios', titulo: 'Usuarios', icono: IconUsers, permiso: 'usuarios.ver' },
  { ruta: '/configuracion', titulo: 'Configuración', icono: IconSettings, permiso: 'catalogos.editar' },
]
