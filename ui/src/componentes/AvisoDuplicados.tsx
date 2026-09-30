import { Alert, Anchor, Badge, Group, Loader, Stack, Text } from '@mantine/core'
import { IconAlertTriangle, IconUsersGroup } from '@tabler/icons-react'
import { Link } from 'react-router-dom'
import type { Esquemas } from '../api/cliente'

export type Coincidencia = Esquemas['CoincidenciaSalida']

const COLOR = { alta: 'red', media: 'yellow', baja: 'gray' } as const
const TEXTO = { alta: 'Casi seguro la misma persona', media: 'Puede ser la misma persona', baja: 'Parecido leve' }

/** Advierte, no bloquea (RF-002). Un aviso de confianza baja suele ser un
 *  familiar: comparten teléfono, correo y apellidos. */
export function AvisoDuplicados({ coincidencias, cargando, accion }: {
  coincidencias: Coincidencia[] | undefined
  cargando?: boolean
  accion?: (c: Coincidencia) => React.ReactNode
}) {
  if (cargando) return <Group gap="xs"><Loader size="xs" /><Text size="sm" c="dimmed">Buscando parecidos…</Text></Group>
  if (!coincidencias?.length) return null
  const peor = coincidencias[0].confianza

  return (
    <Alert color={COLOR[peor]} variant="light" title={`${coincidencias.length} ficha(s) parecida(s)`}
      icon={peor === 'baja' ? <IconUsersGroup size={18} /> : <IconAlertTriangle size={18} />}>
      <Stack gap="xs" mt={4}>
        {coincidencias.map((c) => (
          <Group key={c.cliente_id} justify="space-between" wrap="nowrap" align="flex-start">
            <div>
              <Group gap="xs">
                <Anchor size="sm" fw={500} component={Link} to={`/clientes/${c.cliente_id}`}>{c.nombre}</Anchor>
                <Badge size="xs" color={COLOR[c.confianza]} variant="light">{TEXTO[c.confianza]}</Badge>
                {c.archivado && <Badge size="xs" color="gray" variant="outline">Archivada</Badge>}
              </Group>
              <Text size="xs" c="dimmed">{c.explicacion}</Text>
            </div>
            {accion?.(c)}
          </Group>
        ))}
      </Stack>
    </Alert>
  )
}
