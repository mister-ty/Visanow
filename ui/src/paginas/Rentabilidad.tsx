import {
  Alert, Badge, Card, Center, Group, Loader, Select, SimpleGrid, Stack, Table, Text,
  TextInput, Title,
} from '@mantine/core'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, exigir, type Esquemas } from '../api/cliente'
import { aSelect, useAsignables, useCatalogos } from '../lib/catalogos'
import { formatearPesos } from '../lib/formato'

type Margen = Esquemas['MargenSalida']
type MargenVenta = Esquemas['MargenVentaSalida']
type Orden = 'peores' | 'mejores' | 'recientes'

const ORDENES = [
  { value: 'peores', label: 'Las que menos dejan' },
  { value: 'mejores', label: 'Las que más dejan' },
  { value: 'recientes', label: 'Las más recientes' },
]

const texto = (v: unknown): string | null => (v === null || v === undefined ? null : String(v))

const porcentaje = (v: number | null): string => (v === null ? '—' : `${v} %`)

// El margen se lee de un vistazo por el color: lo que da pérdida, en rojo.
const colorMargen = (v: number) => (v < 0 ? 'red' : v === 0 ? 'dimmed' : 'teal')

/** La resta, en el orden en que se explica. Cada fila dice si suma o si se va. */
function Resta({ m }: { m: Margen }) {
  const filas: { etiqueta: string; valor: number; tipo: 'entra' | 'sale' | 'suma' }[] = [
    { etiqueta: 'Recaudado', valor: m.ingreso_bruto, tipo: 'entra' },
    { etiqueta: 'Devuelto al cliente', valor: m.reembolsos, tipo: 'sale' },
    { etiqueta: 'Costo del medio de pago', valor: m.costo_medio, tipo: 'sale' },
    { etiqueta: 'Ingreso neto', valor: m.ingreso_neto, tipo: 'suma' },
    { etiqueta: 'Comisiones', valor: m.comisiones, tipo: 'sale' },
    { etiqueta: 'Gastos directos', valor: m.gastos_directos, tipo: 'sale' },
    { etiqueta: 'Costo del servicio', valor: m.costo_servicio, tipo: 'sale' },
  ]
  return (
    <Card withBorder padding="sm">
      <Text fw={600} mb="xs">{m.etiqueta}</Text>
      <Table>
        <Table.Tbody>
          {filas.map((f) => (
            <Table.Tr key={f.etiqueta}>
              <Table.Td>
                <Text size="sm" fw={f.tipo === 'suma' ? 600 : 400}>
                  {f.tipo === 'sale' ? '− ' : ''}{f.etiqueta}
                </Text>
              </Table.Td>
              <Table.Td ta="right">
                <Text size="sm" fw={f.tipo === 'suma' ? 600 : 400}
                  c={f.tipo === 'sale' ? 'dimmed' : undefined}>
                  {formatearPesos(f.valor)}
                </Text>
              </Table.Td>
            </Table.Tr>))}
          <Table.Tr>
            <Table.Td><Text fw={700}>= Margen</Text></Table.Td>
            <Table.Td ta="right">
              <Text fw={700} c={colorMargen(m.margen)}>{formatearPesos(m.margen)}</Text>
              <Text size="xs" c="dimmed">{porcentaje(m.margen_pct)} del ingreso neto</Text>
            </Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
      {m.recaudo_terceros > 0 && (
        <Alert color="gray" mt="xs" variant="light">
          <Text size="xs">
            Aparte: {formatearPesos(m.recaudo_terceros)} de tasa consular recaudada. Es plata del
            consulado que la agencia solo recibe y entrega, así que no cuenta como ingreso ni
            entra en el margen.
          </Text>
        </Alert>)}
    </Card>
  )
}

/** Las mismas columnas para el corte por servicio y para el corte por mes. */
function TablaCorte({ titulo, primera, filas }: {
  titulo: string; primera: string; filas: Margen[]
}) {
  return (
    <Card withBorder padding="sm">
      <Text fw={600} mb="xs">{titulo}</Text>
      {filas.length === 0
        ? <Text size="sm" c="dimmed">Sin ventas con estos filtros.</Text>
        : (
          <Table.ScrollContainer minWidth={760}>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{primera}</Table.Th>
                  <Table.Th ta="right">Ventas</Table.Th>
                  <Table.Th ta="right">Ingreso neto</Table.Th>
                  <Table.Th ta="right">Comisiones</Table.Th>
                  <Table.Th ta="right">Gastos directos</Table.Th>
                  <Table.Th ta="right">Costo del servicio</Table.Th>
                  <Table.Th ta="right">Margen</Table.Th>
                  <Table.Th ta="right">%</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filas.map((f) => (
                  <Table.Tr key={f.clave}>
                    <Table.Td>{f.etiqueta}</Table.Td>
                    <Table.Td ta="right">{f.ventas}</Table.Td>
                    <Table.Td ta="right">{formatearPesos(f.ingreso_neto)}</Table.Td>
                    <Table.Td ta="right">{formatearPesos(f.comisiones)}</Table.Td>
                    <Table.Td ta="right">{formatearPesos(f.gastos_directos)}</Table.Td>
                    <Table.Td ta="right">{formatearPesos(f.costo_servicio)}</Table.Td>
                    <Table.Td ta="right">
                      <Text size="sm" fw={600} c={colorMargen(f.margen)}>
                        {formatearPesos(f.margen)}
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right">{porcentaje(f.margen_pct)}</Table.Td>
                  </Table.Tr>))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>)}
    </Card>
  )
}

function TablaVentas({ filas }: { filas: MargenVenta[] }) {
  return (
    <Table.ScrollContainer minWidth={820}>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Venta</Table.Th>
            <Table.Th>Fecha</Table.Th>
            <Table.Th>Servicio</Table.Th>
            <Table.Th>Vendedor</Table.Th>
            <Table.Th ta="right">Ingreso neto</Table.Th>
            <Table.Th ta="right">Comisión</Table.Th>
            <Table.Th ta="right">Gastos</Table.Th>
            <Table.Th ta="right">Costo</Table.Th>
            <Table.Th ta="right">Margen</Table.Th>
            <Table.Th ta="right">%</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {filas.map((v) => (
            <Table.Tr key={v.negocio_id}>
              {/* El numero de la venta, sin enlace: no hay todavia una pantalla
                  de la venta a la que llevar, y un enlace que no va a ninguna
                  parte es peor que ninguno. */}
              <Table.Td>#{v.negocio_id}</Table.Td>
              <Table.Td>{v.fecha_venta}</Table.Td>
              <Table.Td>
                {v.servicio}
                {v.es_recaudo_de_terceros && (
                  <Badge ml={6} size="xs" color="gray" variant="light">Tasa consular</Badge>)}
              </Table.Td>
              <Table.Td>{v.vendedor ?? '—'}</Table.Td>
              <Table.Td ta="right">{formatearPesos(v.ingreso_neto)}</Table.Td>
              <Table.Td ta="right">{formatearPesos(v.comisiones)}</Table.Td>
              <Table.Td ta="right">{formatearPesos(v.gastos_directos)}</Table.Td>
              <Table.Td ta="right">{formatearPesos(v.costo_servicio)}</Table.Td>
              <Table.Td ta="right">
                <Text size="sm" fw={600} c={colorMargen(v.margen)}>
                  {formatearPesos(v.margen)}
                </Text>
              </Table.Td>
              <Table.Td ta="right">{porcentaje(v.margen_pct)}</Table.Td>
            </Table.Tr>))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  )
}

export function Rentabilidad() {
  const catalogos = useCatalogos()
  const asignables = useAsignables()
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [servicio, setServicio] = useState<string | null>(null)
  const [vendedor, setVendedor] = useState<string | null>(null)
  const [orden, setOrden] = useState<Orden>('peores')

  const consulta = {
    ...(desde ? { desde } : {}),
    ...(hasta ? { hasta } : {}),
    ...(servicio ? { servicio_id: Number(servicio) } : {}),
    ...(vendedor ? { vendedor_id: Number(vendedor) } : {}),
  }

  const informe = useQuery({
    queryKey: ['rentabilidad', consulta],
    queryFn: () => exigir(api.GET('/api/v1/rentabilidad', { params: { query: consulta } })),
    placeholderData: keepPreviousData,
    // Un 403 por alcance o por permiso no se arregla reintentando
    retry: false,
  })

  const ventas = useQuery({
    queryKey: ['rentabilidad-ventas', consulta, orden],
    queryFn: () => exigir(api.GET('/api/v1/rentabilidad/ventas',
      { params: { query: { ...consulta, orden } } })),
    placeholderData: keepPreviousData,
    retry: false,
  })

  return (
    <Stack>
      <div>
        <Title order={2}>Rentabilidad</Title>
        <Text size="sm" c="dimmed">
          Lo que de verdad quedó: ingreso neto menos comisiones, gastos directos y costos.
          El periodo es la fecha de la venta, y cada venta se mide con el costo que regía ese día.
        </Text>
      </div>

      <Group align="flex-end" wrap="wrap">
        <TextInput type="date" label="Desde" value={desde}
          onChange={(e) => setDesde(e.currentTarget.value)} />
        <TextInput type="date" label="Hasta" value={hasta}
          onChange={(e) => setHasta(e.currentTarget.value)} />
        <Select label="Servicio" w={220} clearable value={servicio}
          onChange={(v) => setServicio(texto(v))} data={aSelect(catalogos.data?.servicios)} />
        <Select label="Vendedor" w={180} clearable value={vendedor}
          onChange={(v) => setVendedor(texto(v))}
          data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))} />
      </Group>

      {informe.isPending && <Center h={160}><Loader color="teal" /></Center>}
      {informe.isError && <Alert color="red">{informe.error.message}</Alert>}

      {informe.data && (
        <>
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Resta m={informe.data.total} />
            <TablaCorte titulo="Por mes de venta" primera="Mes"
              filas={informe.data.por_periodo} />
          </SimpleGrid>

          <TablaCorte titulo="Por servicio" primera="Servicio"
            filas={informe.data.por_servicio} />
        </>)}

      <Card withBorder padding="sm">
        <Group justify="space-between" mb="xs" align="flex-end">
          <div>
            <Text fw={600}>Por venta</Text>
            <Text size="xs" c="dimmed">
              Una venta con margen negativo costó más de lo que ha entrado: o todavía no
              terminan de pagarla, o se le cargó más de lo que dejó.
            </Text>
          </div>
          <Select w={200} label="Orden" value={orden} allowDeselect={false}
            onChange={(v) => setOrden((v ?? 'peores') as Orden)} data={ORDENES} />
        </Group>
        {ventas.isPending && <Center h={120}><Loader color="teal" /></Center>}
        {ventas.isError && <Alert color="red">{ventas.error.message}</Alert>}
        {ventas.data && (ventas.data.items.length === 0
          ? <Text size="sm" c="dimmed">Sin ventas con estos filtros.</Text>
          : (
            <>
              <TablaVentas filas={ventas.data.items} />
              <Text size="xs" c="dimmed" mt="xs">
                {ventas.data.items.length} de {ventas.data.total} ventas.
              </Text>
            </>))}
      </Card>
    </Stack>
  )
}
