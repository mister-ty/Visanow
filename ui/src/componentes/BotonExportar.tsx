import { Button, Group } from '@mantine/core'
import { IconDownload } from '@tabler/icons-react'
import { useState } from 'react'
import { api } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { mostrarError } from '../lib/errores'

type Lista = 'clientes' | 'casos' | 'cartera' | 'comisiones'
type Filtros = Record<string, string | number | boolean | undefined>

/** Descarga una lista con los filtros que tiene la pantalla, y solo se muestra a
 *  quien tiene `<módulo>.exportar`. El servidor deja constancia de cada descarga
 *  (quién y cuántas filas): por eso no hay forma de bajarla sin pasar por él. */
export function BotonExportar({ lista, permiso, filtros = {} }: {
  lista: Lista; permiso: string; filtros?: Filtros
}) {
  const { puede } = useSesion()
  const [bajando, setBajando] = useState(false)
  if (!puede(permiso)) return null

  // Por fetch y no por un enlace: el token vive en sessionStorage, no en una
  // cookie, y un <a href> no lo enviaría.
  const bajar = async (formato: 'xlsx' | 'csv') => {
    setBajando(true)
    try {
      const { data, response } = await api.GET('/api/v1/exportaciones/{lista}', {
        params: { path: { lista }, query: { formato, ...filtros } },
        parseAs: 'blob',
      })
      if (!response.ok || !data) throw new Error('Exportación fallida')
      const url = URL.createObjectURL(data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${lista}.${formato}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      mostrarError(e, 'No se pudo exportar')
    } finally {
      setBajando(false)
    }
  }

  return (
    <Group gap="xs">
      <Button variant="light" loading={bajando} leftSection={<IconDownload size={16} />}
        onClick={() => bajar('xlsx')}>Excel</Button>
      <Button variant="default" loading={bajando} onClick={() => bajar('csv')}>CSV</Button>
    </Group>)
}
