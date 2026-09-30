import {
  ActionIcon, Badge, Card, Chip, Group, Stack, Switch, Table, Text, TextInput, Title, Tooltip,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { IconAlertTriangle, IconCloudDownload, IconSearch, IconX } from '@tabler/icons-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, exigir } from '../api/cliente'

const COLOR_RIESGO = { alto: 'red', medio: 'yellow', bajo: 'gray', ninguno: 'gray' } as const

/** Tablero operativo (RF-022): qué trámites hay, en qué estado, de quién son y
 *  cuáles llevan días quietos. */
export function Casos() {
  const navegar = useNavigate()
  const [estado, setEstado] = useState<string | null>(null)
  const [texto, setTexto] = useState('')
  const [busqueda] = useDebouncedValue(texto, 300)
  const [sinAsignar, setSinAsignar] = useState(false)
  const [finalizados, setFinalizados] = useState(false)

  const resumen = useQuery({
    queryKey: ['casos-resumen'],
    queryFn: () => exigir(api.GET('/api/v1/casos/resumen')),
  })
  const casos = useQuery({
    queryKey: ['casos', estado, busqueda, sinAsignar, finalizados],
    queryFn: () => exigir(api.GET('/api/v1/casos', {
      params: { query: { estado: estado ?? undefined, texto: busqueda || undefined,
                         sin_asignar: sinAsignar, incluir_finalizados: finalizados, tamano: 100 } },
    })),
    placeholderData: keepPreviousData,
  })

  return (
    <Stack>
      <Title order={2}>Trámites</Title>

      <Group gap="xs">
        <Chip checked={estado === null} onChange={() => setEstado(null)} variant="light">
          Todos ({resumen.data?.reduce((t, e) => t + e.total, 0) ?? 0})
        </Chip>
        {resumen.data?.filter((e) => e.total > 0).map((e) => (
          <Chip key={e.codigo} checked={estado === e.codigo} variant="light"
            onChange={() => setEstado(estado === e.codigo ? null : e.codigo)}>
            {e.nombre} ({e.total})
          </Chip>
        ))}
      </Group>

      <Group align="flex-end">
        <TextInput flex={1} maw={360} label="Buscar" placeholder="Nombre o n.º de solicitud del SaaS"
          leftSection={<IconSearch size={16} />} value={texto}
          onChange={(e) => setTexto(e.currentTarget.value)}
          rightSection={texto && (
            <ActionIcon variant="subtle" color="gray" onClick={() => setTexto('')} aria-label="Limpiar">
              <IconX size={14} /></ActionIcon>)} />
        <Switch label="Sin responsable" checked={sinAsignar} mb={8}
          onChange={(e) => setSinAsignar(e.currentTarget.checked)} />
        <Switch label="Incluir finalizados" checked={finalizados} mb={8}
          onChange={(e) => setFinalizados(e.currentTarget.checked)} />
      </Group>

      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={900}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Persona</Table.Th><Table.Th>Estado</Table.Th><Table.Th>Responsable</Table.Th>
                <Table.Th>Próxima acción</Table.Th><Table.Th>Quieto</Table.Th><Table.Th>Origen</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {casos.data?.items.map((c) => (
                <Table.Tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => navegar(`/casos/${c.id}`)}>
                  <Table.Td>
                    <Text size="sm" fw={500}>{c.solicitante}</Text>
                    <Group gap={4}>
                      <Text size="xs" c="dimmed">{c.pais ?? 'sin país'}</Text>
                      {c.sin_venta && (
                        <Tooltip label="No tiene una venta registrada que lo respalde">
                          <Badge size="xs" color="orange" variant="light">sin venta</Badge>
                        </Tooltip>)}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="light" color={c.es_final ? 'gray' : 'teal'}>{c.estado_nombre}</Badge>
                    {c.resultado && <Text size="xs" c="dimmed" mt={2}>{c.resultado}</Text>}
                  </Table.Td>
                  <Table.Td>
                    {c.responsable ?? <Badge size="sm" color="orange" variant="light">sin asignar</Badge>}
                  </Table.Td>
                  <Table.Td><Text size="sm" c={c.proxima_accion ? undefined : 'dimmed'}>
                    {c.proxima_accion ?? '—'}</Text></Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {c.riesgo === 'alto' && <IconAlertTriangle size={14} color="var(--mantine-color-red-6)" />}
                      <Text size="sm" c={COLOR_RIESGO[c.riesgo]}>
                        {c.es_final ? '—' : `${c.dias_sin_movimiento} d`}
                      </Text>
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    {c.fuente === 'manual' ? <Text size="xs" c="dimmed">manual</Text> : (
                      <Tooltip label={`N.º de solicitud ${c.id_externo ?? ''}`}>
                        <Badge size="sm" variant="light" leftSection={<IconCloudDownload size={12} />}>SaaS</Badge>
                      </Tooltip>)}
                  </Table.Td>
                </Table.Tr>
              ))}
              {casos.data?.items.length === 0 && (
                <Table.Tr><Table.Td colSpan={6}>
                  <Text size="sm" c="dimmed" ta="center" py="lg">
                    No hay trámites con esos filtros. Los trámites se crean desde la ficha del cliente,
                    sobre la persona que viaja.
                  </Text>
                </Table.Td></Table.Tr>)}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Text size="sm" c="dimmed">{casos.data?.total ?? 0} trámite(s)</Text>
    </Stack>
  )
}
