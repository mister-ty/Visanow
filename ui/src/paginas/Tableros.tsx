import {
  Alert, Button, Card, Center, Group, Loader, Select, SimpleGrid, Stack, Table, Tabs, Text,
  TextInput, Title,
} from '@mantine/core'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { IconDownload } from '@tabler/icons-react'
import { useState } from 'react'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { aSelect, useAsignables, useCatalogos } from '../lib/catalogos'
import { mostrarError } from '../lib/errores'
import { formatearPesos } from '../lib/formato'

type Tablero = Esquemas['TableroSalida']
type Indicador = Esquemas['IndicadorSalida']
type Nombre = 'comercial' | 'operativo' | 'financiero' | 'ejecutivo'

const PESTANAS: { valor: Nombre; titulo: string }[] = [
  { valor: 'comercial', titulo: 'Comercial' },
  { valor: 'operativo', titulo: 'Operativo' },
  { valor: 'financiero', titulo: 'Financiero' },
  { valor: 'ejecutivo', titulo: 'Ejecutivo' },
]

const ESTADOS_FINANCIEROS = [
  { value: 'sin_acuerdo', label: 'Sin acuerdo' },
  { value: 'pendiente_anticipo', label: 'Pendiente de anticipo' },
  { value: 'abono', label: 'Con abonos' },
  { value: 'pagado', label: 'Pagado' },
]

const texto = (v: unknown): string | null => (v === null || v === undefined ? null : String(v))

const valorDe = (i: Indicador): string =>
  i.formato === 'pesos' ? formatearPesos(i.valor)
    : i.formato === 'porcentaje' ? `${i.valor} %`
      : new Intl.NumberFormat('es-CO').format(i.valor)

// Una celda numérica grande es dinero solo si su columna lo dice: el backend
// manda filas sin tipo, así que se infiere del encabezado.
const ES_DINERO = /vendido|cobrado|saldo|valor/i
const celda = (col: string, v: string | number | null) =>
  v === null ? '—' : typeof v === 'number' && ES_DINERO.test(col) ? formatearPesos(v) : String(v)

export function Tableros() {
  const { puede } = useSesion()
  const catalogos = useCatalogos()
  const asignables = useAsignables()
  const [pestana, setPestana] = useState<Nombre>('comercial')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [vendedor, setVendedor] = useState<string | null>(null)
  const [servicio, setServicio] = useState<string | null>(null)
  const [estado, setEstado] = useState<string | null>(null)
  const [bajando, setBajando] = useState(false)

  const cambiarPestana = (v: string | null) => {
    if (!v) return
    setPestana(v as Nombre)
    // Los códigos de estado son de cada tablero: uno viejo no filtra nada, pero deja
    // la pantalla en blanco sin explicación
    setEstado(null)
  }

  const consulta = {
    ...(desde ? { desde } : {}),
    ...(hasta ? { hasta } : {}),
    ...(vendedor ? { vendedor_id: Number(vendedor) } : {}),
    ...(servicio ? { servicio_id: Number(servicio) } : {}),
    ...(estado ? { estado } : {}),
  }

  const tablero = useQuery({
    queryKey: ['tablero', pestana, consulta],
    queryFn: () => exigir(api.GET('/api/v1/tableros/{tablero}',
      { params: { path: { tablero: pestana }, query: consulta } })),
    placeholderData: keepPreviousData,
    // Un 403 por alcance no se arregla reintentando
    retry: false,
  })

  const opcionesEstado = pestana === 'financiero' ? ESTADOS_FINANCIEROS
    : pestana === 'operativo'
      ? (catalogos.data?.estados_operativos ?? []).map((e) => ({ value: e.codigo ?? '', label: e.nombre }))
      : pestana === 'comercial'
        ? (catalogos.data?.estados_comerciales ?? []).map((e) => ({ value: e.codigo ?? '', label: e.nombre }))
        : []

  // La exportación va por fetch y no por un enlace: el token vive en sessionStorage,
  // no en una cookie, y un <a href> no lo enviaría.
  const exportar = async (formato: 'xlsx' | 'csv') => {
    setBajando(true)
    try {
      const { data, error, response } = await api.GET('/api/v1/tableros/{tablero}/exportar', {
        params: { path: { tablero: pestana }, query: { formato, ...consulta } },
        parseAs: 'blob',
      })
      if (!response.ok || !data) throw Object.assign(new Error('Exportación fallida'), { error })
      const url = URL.createObjectURL(data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `tablero-${pestana}.${formato}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      mostrarError(e, 'No se pudo exportar')
    } finally {
      setBajando(false)
    }
  }

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Tableros</Title>
          <Text size="sm" c="dimmed">
            Las fechas son días de Bogotá. Lo que se exporta lleva los mismos filtros de la pantalla.
          </Text>
        </div>
        {puede('tableros.exportar') && (
          <Group gap="xs">
            <Button variant="light" loading={bajando} leftSection={<IconDownload size={16} />}
              onClick={() => exportar('xlsx')}>Excel</Button>
            <Button variant="default" loading={bajando} onClick={() => exportar('csv')}>CSV</Button>
          </Group>)}
      </Group>

      <Tabs value={pestana} onChange={cambiarPestana}>
        <Tabs.List>
          {PESTANAS.map((p) => <Tabs.Tab key={p.valor} value={p.valor}>{p.titulo}</Tabs.Tab>)}
        </Tabs.List>
      </Tabs>

      <Group align="flex-end" wrap="wrap">
        <TextInput type="date" label="Desde" value={desde} onChange={(e) => setDesde(e.currentTarget.value)} />
        <TextInput type="date" label="Hasta" value={hasta} onChange={(e) => setHasta(e.currentTarget.value)} />
        <Select label={pestana === 'operativo' ? 'Responsable' : 'Vendedor'} w={180} clearable
          value={vendedor} onChange={(v) => setVendedor(texto(v))}
          data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))} />
        <Select label="Servicio" w={200} clearable value={servicio} onChange={(v) => setServicio(texto(v))}
          data={aSelect(catalogos.data?.servicios)} />
        {opcionesEstado.length > 0 && (
          <Select label="Estado" w={200} clearable value={estado} onChange={(v) => setEstado(texto(v))}
            data={opcionesEstado} />)}
      </Group>

      {tablero.isPending && <Center h={160}><Loader color="teal" /></Center>}
      {tablero.isError && <Alert color="red">{tablero.error.message}</Alert>}
      {tablero.data && <Contenido t={tablero.data} />}
    </Stack>
  )
}

function Contenido({ t }: { t: Tablero }) {
  return (
    <Stack>
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }}>
        {t.indicadores.map((i) => (
          <Card key={i.clave} withBorder padding="sm">
            <Text size="xs" c="dimmed">{i.nombre}</Text>
            <Text fz={22} fw={700}>{valorDe(i)}</Text>
          </Card>))}
      </SimpleGrid>
      {t.tablas.map((x) => (
        <Card key={x.clave} withBorder padding="sm">
          <Text fw={600} mb="xs">{x.titulo}</Text>
          {x.filas.length === 0
            ? <Text size="sm" c="dimmed">Sin datos con estos filtros.</Text>
            : (
              <Table.ScrollContainer minWidth={420}>
                <Table striped>
                  <Table.Thead>
                    <Table.Tr>{x.columnas.map((c) => <Table.Th key={c}>{c}</Table.Th>)}</Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {x.filas.map((fila, i) => (
                      <Table.Tr key={i}>
                        {fila.map((v, j) => <Table.Td key={j}>{celda(x.columnas[j], v)}</Table.Td>)}
                      </Table.Tr>))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>)}
        </Card>))}
    </Stack>
  )
}
