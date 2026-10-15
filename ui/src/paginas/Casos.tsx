import {
  ActionIcon, Badge, Button, Card, Chip, Group, Select, Stack, Switch, Table, Text, TextInput,
  Title, Tooltip,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { IconAlertTriangle, IconCloudDownload, IconSearch, IconX } from '@tabler/icons-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BotonExportar } from '../componentes/BotonExportar'
import { api, exigir } from '../api/cliente'
import { aSelect, useAsignables, useCatalogos } from '../lib/catalogos'
import { formatearFecha } from '../lib/formato'
import { ORIGEN } from '../lib/origen'
import { PiePaginacion, TAMANO_PAGINA, usePagina } from '../componentes/Paginacion'

const COLOR_RIESGO = { alto: 'red', medio: 'yellow', bajo: 'gray', ninguno: 'gray' } as const

// Lo que entrega un Select de Mantine puede ser número o nulo; los filtros se
// guardan como texto y se convierten al armar la consulta.
const aTexto = (v: unknown): string | null => (v === null || v === undefined ? null : String(v))

const RIESGOS = [
  { value: 'alto', label: 'Alto' }, { value: 'medio', label: 'Medio' },
  { value: 'bajo', label: 'Bajo' },
]

/** Las dos preguntas distintas del tablero. «Quieto» es cuánto lleva sin
 *  moverse —si se le olvidó a alguien— y «antigüedad» cuánto lleva abierto —si
 *  nos estamos demorando—. Un trámite de hace cinco meses que se movió ayer no
 *  es un trámite quieto, y antes el tablero solo sabía responder la primera. */
const ORDENES = [
  { value: 'quieto', label: 'Los más quietos primero' },
  { value: 'antiguedad', label: 'Los que llevan más tiempo abiertos' },
]

/** Tablero operativo (RF-022) por las siete dimensiones del requisito: estado,
 *  responsable, país, servicio, fecha de entrada, antigüedad y riesgo. */
export function Casos() {
  const navegar = useNavigate()
  const catalogos = useCatalogos()
  const asignables = useAsignables()
  const [estado, setEstado] = useState<string | null>(null)
  const [texto, setTexto] = useState('')
  const [busqueda] = useDebouncedValue(texto, 300)
  const [responsable, setResponsable] = useState<string | null>(null)
  const [pais, setPais] = useState<string | null>(null)
  const [servicio, setServicio] = useState<string | null>(null)
  const [riesgo, setRiesgo] = useState<string | null>(null)
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [orden, setOrden] = useState<string>('quieto')
  const [sinAsignar, setSinAsignar] = useState(false)
  const [finalizados, setFinalizados] = useState(false)

  const [pagina, setPagina] = usePagina([estado, busqueda, responsable, pais, servicio,
                                         riesgo, desde, hasta, sinAsignar, finalizados, orden])
  const filtros = {
    ...(estado ? { estado } : {}),
    ...(busqueda ? { texto: busqueda } : {}),
    ...(responsable ? { responsable_id: Number(responsable) } : {}),
    ...(pais ? { pais_id: Number(pais) } : {}),
    ...(servicio ? { servicio_id: Number(servicio) } : {}),
    ...(riesgo ? { riesgo: riesgo as 'alto' } : {}),
    ...(desde ? { desde } : {}),
    ...(hasta ? { hasta } : {}),
    sin_asignar: sinAsignar,
    incluir_finalizados: finalizados,
    orden: orden as 'quieto',
    pagina, tamano: TAMANO_PAGINA,
  }
  const hayFiltros = Boolean(estado || texto || responsable || pais || servicio || riesgo
    || desde || hasta || sinAsignar || finalizados)
  const limpiar = () => {
    setEstado(null); setTexto(''); setResponsable(null); setPais(null); setServicio(null)
    setRiesgo(null); setDesde(''); setHasta(''); setSinAsignar(false); setFinalizados(false)
  }

  const resumen = useQuery({
    queryKey: ['casos-resumen'],
    queryFn: () => exigir(api.GET('/api/v1/casos/resumen')),
  })
  const casos = useQuery({
    queryKey: ['casos', filtros],
    queryFn: () => exigir(api.GET('/api/v1/casos', { params: { query: filtros } })),
    placeholderData: keepPreviousData,
  })

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Trámites</Title>
        <BotonExportar recurso="casos" />
      </Group>

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
        <TextInput flex={1} maw={300} label="Buscar" placeholder="Nombre o n.º de solicitud del SaaS"
          leftSection={<IconSearch size={16} />} value={texto}
          onChange={(e) => setTexto(e.currentTarget.value)}
          rightSection={texto && (
            <ActionIcon variant="subtle" color="gray" onClick={() => setTexto('')} aria-label="Limpiar">
              <IconX size={14} /></ActionIcon>)} />
        <Select label="Responsable" w={180} clearable searchable value={responsable}
          data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))}
          onChange={(v) => setResponsable(aTexto(v))} />
        <Select label="País" w={150} clearable searchable value={pais}
          data={aSelect(catalogos.data?.paises)} onChange={(v) => setPais(aTexto(v))} />
        <Select label="Servicio" w={190} clearable searchable value={servicio}
          data={aSelect(catalogos.data?.servicios)} onChange={(v) => setServicio(aTexto(v))}
          description="Solo trámites con venta" />
        <Select label="Riesgo" w={120} clearable value={riesgo} data={RIESGOS} onChange={(v) => setRiesgo(aTexto(v))} />
      </Group>

      <Group align="flex-end">
        <TextInput type="date" label="Entró desde" value={desde}
          onChange={(e) => setDesde(e.currentTarget.value)} />
        <TextInput type="date" label="Entró hasta" value={hasta}
          onChange={(e) => setHasta(e.currentTarget.value)} />
        <Select label="Orden" w={260} data={ORDENES} value={orden} allowDeselect={false}
          onChange={(v) => v && setOrden(String(v))} />
        <Switch label="Sin responsable" checked={sinAsignar} mb={8}
          onChange={(e) => setSinAsignar(e.currentTarget.checked)} />
        <Switch label="Incluir finalizados" checked={finalizados} mb={8}
          onChange={(e) => setFinalizados(e.currentTarget.checked)} />
        {hayFiltros && (
          <Button variant="subtle" size="compact-sm" mb={8} onClick={limpiar}>Limpiar filtros</Button>)}
      </Group>

      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={1150}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Persona</Table.Th><Table.Th>Servicio</Table.Th><Table.Th>Estado</Table.Th>
                <Table.Th>Responsable</Table.Th><Table.Th>Próxima acción</Table.Th>
                <Table.Th>Entrada</Table.Th><Table.Th>Quieto</Table.Th><Table.Th>Origen</Table.Th>
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
                    <Text size="sm" c={c.servicio ? undefined : 'dimmed'}>{c.servicio ?? '—'}</Text>
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
                    <Text size="sm">{formatearFecha(c.creado_en)}</Text>
                    <Text size="xs" c="dimmed">
                      {c.es_final ? 'cerrado' : `${c.antiguedad_dias} d abierto`}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {c.riesgo === 'alto' && <IconAlertTriangle size={14} color="var(--mantine-color-red-6)" />}
                      <Text size="sm" c={COLOR_RIESGO[c.riesgo]}>
                        {c.es_final ? '—' : `${c.dias_sin_movimiento} d`}
                      </Text>
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    {c.fuente === 'manual'
                      ? <Text size="xs" c="dimmed">{ORIGEN.manual.nombre}</Text>
                      : (
                        <Tooltip label={`N.º de solicitud ${c.id_externo ?? '—'}`}>
                          <Badge size="sm" variant="light" color={ORIGEN[c.fuente].color}
                            leftSection={<IconCloudDownload size={12} />}>
                            {ORIGEN[c.fuente].nombre}
                          </Badge>
                        </Tooltip>)}
                  </Table.Td>
                </Table.Tr>
              ))}
              {casos.data?.items.length === 0 && (
                <Table.Tr><Table.Td colSpan={8}>
                  <Text size="sm" c="dimmed" ta="center" py="lg">
                    No hay trámites con esos filtros. Los trámites se crean desde la ficha del cliente,
                    sobre la persona que viaja.
                  </Text>
                </Table.Td></Table.Tr>)}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <PiePaginacion total={casos.data?.total} pagina={pagina} onPagina={setPagina}
        unidad="trámite(s)" />
    </Stack>
  )
}
