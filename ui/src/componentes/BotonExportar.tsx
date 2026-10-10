import { Button, Menu } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconDownload, IconFileSpreadsheet, IconFileText } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, token } from '../api/cliente'

type Recurso = 'clientes' | 'solicitantes' | 'casos' | 'cartera' | 'pagos' | 'comisiones'

/**
 * Descarga una lista en Excel o CSV.
 *
 * Quién puede exportar lo dice el servidor, no la pantalla: se le pregunta por
 * `/exportar/recursos` en vez de adivinar el nombre de un permiso acá. Si el
 * día que alguien cambie los permisos del rol la pantalla sigue en lo suyo,
 * ofrecería un botón que devuelve 403.
 *
 * El archivo no trae las columnas que el usuario no puede ver, y eso **se
 * avisa**: recibir la lista de trámites sin la columna de valor es correcto,
 * pero creer que la descargó completa cuando no es así, no.
 */
export function BotonExportar({ recurso, etiqueta }: { recurso: Recurso; etiqueta?: string }) {
  const [bajando, setBajando] = useState(false)

  const { data: permitidos } = useQuery({
    queryKey: ['exportar', 'recursos'],
    queryFn: async () => (await api.GET('/api/v1/exportar/recursos', {})).data?.recursos ?? [],
    staleTime: 5 * 60 * 1000,
  })
  if (!permitidos?.includes(recurso)) return null

  // Por fetch y no por un <a href>: el token vive en sessionStorage, no en una
  // cookie, y un enlace no lo enviaría. Tampoco se puede poner en la URL.
  const bajar = async (formato: 'xlsx' | 'csv') => {
    setBajando(true)
    try {
      const r = await fetch(`/api/v1/exportar/${recurso}?formato=${formato}`, {
        headers: { Authorization: `Bearer ${token.leer() ?? ''}` },
      })
      if (!r.ok) {
        const cuerpo = await r.json().catch(() => ({}))
        throw new Error(cuerpo.detalle ?? `No se pudo exportar (${r.status})`)
      }

      const adjunto = r.headers.get('content-disposition') ?? ''
      const nombre = /filename="([^"]+)"/.exec(adjunto)?.[1] ?? `${recurso}.${formato}`
      const url = URL.createObjectURL(await r.blob())
      const a = document.createElement('a')
      a.href = url
      a.download = nombre
      a.click()
      URL.revokeObjectURL(url)

      const omitidas = r.headers.get('x-columnas-omitidas')
      const filas = r.headers.get('x-filas')
      notifications.show({
        color: omitidas ? 'yellow' : 'teal',
        title: `${nombre} · ${filas ?? '?'} filas`,
        message: omitidas
          ? `El archivo va sin estas columnas, porque su rol no las ve: ${omitidas}.`
          : 'Descargado. La descarga queda registrada.',
        autoClose: omitidas ? 9000 : 4000,
      })
    } catch (e) {
      notifications.show({
        color: 'red', title: 'No se pudo exportar',
        message: e instanceof Error ? e.message : 'Error inesperado',
      })
    } finally {
      setBajando(false)
    }
  }

  return (
    <Menu position="bottom-end">
      <Menu.Target>
        <Button variant="light" loading={bajando} leftSection={<IconDownload size={16} />}>
          {etiqueta ?? 'Exportar'}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Queda registrado quién descarga</Menu.Label>
        <Menu.Item leftSection={<IconFileSpreadsheet size={16} />} onClick={() => bajar('xlsx')}>
          Excel (.xlsx)
        </Menu.Item>
        <Menu.Item leftSection={<IconFileText size={16} />} onClick={() => bajar('csv')}>
          CSV
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}
