import {
  Alert, Badge, Button, Card, Center, Group, Loader, Modal, NumberInput, Select, SimpleGrid, Stack,
  Switch, Table, Tabs, Text, TextInput, Textarea, Title,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconPlus, IconSearch } from '@tabler/icons-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { BotonExportar } from '../componentes/BotonExportar'
import { aSelect, useAsignables, useCatalogos } from '../lib/catalogos'
import { mostrarError } from '../lib/errores'
import { formatearPesos } from '../lib/formato'
import { PiePaginacion, TAMANO_PAGINA, usePagina } from '../componentes/Paginacion'

type Pago = Esquemas['PagoSalida']
type Tramo = Esquemas['TramoAntiguedad']['tramo']

const COLOR_ESTADO_PAGO: Record<string, string> = {
  confirmado: 'teal', pendiente: 'yellow', no_identificado: 'orange', reversado: 'gray', duplicado: 'gray',
}
const NOMBRE_ESTADO_PAGO: Record<string, string> = {
  confirmado: 'Confirmado', pendiente: 'Pendiente', no_identificado: 'Sin identificar',
  reversado: 'Reversado', duplicado: 'Duplicado',
}
const NOMBRE_AJUSTE: Record<string, string> = {
  reembolso: 'Reembolso', cargo: 'Cargo', descuento: 'Descuento', condonacion: 'Condonación',
}

// Los cortes de antigüedad de la contabilidad colombiana. En qué tramo cae cada
// deuda lo decide la API, no esta pantalla: acá solo se le pone color y nombre.
// El color sube de tono con la edad para que el ojo encuentre lo peor sin leer.
const COLOR_TRAMO: Record<string, string> = {
  al_dia: 'teal', '1_30': 'yellow', '31_60': 'orange', '61_90': 'red', mas_90: 'grape',
}
const NOMBRE_TRAMO: Record<string, string> = {
  al_dia: 'Al día', '1_30': '1 a 30 d', '31_60': '31 a 60 d', '61_90': '61 a 90 d',
  mas_90: '+ de 90 d',
}
// El filtro no ofrece «al día»: en una lista de cobro no se filtra por quien no
// debe nada vencido. Para eso está «le vence en N días».
const TRAMOS: { valor: Tramo; titulo: string }[] = [
  { valor: '1_30', titulo: '1 a 30 días' },
  { valor: '31_60', titulo: '31 a 60 días' },
  { valor: '61_90', titulo: '61 a 90 días' },
  { valor: 'mas_90', titulo: 'Más de 90 días' },
]

// La API entrega la fecha como AAAA-MM-DD sin hora. Se parte el texto en vez de
// pasarlo por Date: `new Date('2026-10-16')` es medianoche UTC y en Bogotá se
// vería como el día anterior.
const formatearDia = (d: string | null | undefined) =>
  d ? d.split('-').reverse().join('/') : '—'

/** Pagos y cartera (RF-040 a RF-046): quién debe, los pagos sueltos por asignar
 *  y el estado financiero de cada venta. El saldo siempre viene de la API: no
 *  se calcula ni se guarda acá. */
export function Pagos() {
  const { puede } = useSesion()
  const [registrando, setRegistrando] = useState(false)
  const [ventaAbierta, setVentaAbierta] = useState<number | null>(null)
  // El buscador global trae acá con la referencia puesta (RF-029): si alguien
  // llega buscando un pago, la pantalla tiene que abrir en la lista de pagos y
  // no en la cartera, o parecería que no encontró nada.
  const [params] = useSearchParams()
  const referenciaBuscada = params.get('referencia') ?? ''

  const sinAsignar = useQuery({
    queryKey: ['pagos', 'sin-asignar-conteo'],
    queryFn: () => exigir(api.GET('/api/v1/pagos', { params: { query: { sin_asignar: true, tamano: 1 } } })),
  })
  // Se pide acá y no dentro de la pestaña para poder poner el número en la
  // solapa: una cartera inflada por ventas repetidas no se va a mirar si hay
  // que entrar a buscarla.
  const repetidas = useQuery({
    queryKey: ['ventas-repetidas'],
    queryFn: () => exigir(api.GET('/api/v1/ventas/repetidas')),
  })

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Pagos y cartera</Title>
          <Text size="sm" c="dimmed">Quién debe, cuánto y desde cuándo; y los pagos que aún no tienen dueño.</Text>
        </div>
        <Group gap="xs">
          <BotonExportar recurso="cartera" etiqueta="Exportar cartera" />
          <BotonExportar recurso="pagos" etiqueta="Exportar pagos" />
        </Group>
        {puede('pagos.crear') && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setRegistrando(true)}>
            Registrar pago
          </Button>)}
      </Group>

      <Tabs defaultValue={referenciaBuscada ? 'pagos' : 'cartera'} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="cartera">Cartera</Tabs.Tab>
          <Tabs.Tab value="bandeja"
            rightSection={sinAsignar.data?.total ? <Badge size="sm" color="orange">{sinAsignar.data.total}</Badge> : null}>
            Pagos sin identificar
          </Tabs.Tab>
          <Tabs.Tab value="pagos">Todos los pagos</Tabs.Tab>
          <Tabs.Tab value="repetidas"
            rightSection={repetidas.data?.length ? <Badge size="sm" color="red">{repetidas.data.length}</Badge> : null}>
            Ventas repetidas
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="cartera" pt="md"><Cartera abrirVenta={setVentaAbierta} /></Tabs.Panel>
        <Tabs.Panel value="bandeja" pt="md">
          <TablaPagos soloSinAsignar abrirVenta={setVentaAbierta} />
        </Tabs.Panel>
        <Tabs.Panel value="pagos" pt="md">
          <TablaPagos abrirVenta={setVentaAbierta} referenciaInicial={referenciaBuscada} />
        </Tabs.Panel>
        <Tabs.Panel value="repetidas" pt="md">
          <VentasRepetidas grupos={repetidas.data} cargando={repetidas.isPending}
            abrirVenta={setVentaAbierta} />
        </Tabs.Panel>
      </Tabs>

      <ModalPago abierto={registrando} cerrar={() => setRegistrando(false)} />
      <ModalEstadoFinanciero negocioId={ventaAbierta} cerrar={() => setVentaAbierta(null)} />
    </Stack>
  )
}

// ------------------------------------------------------------------ cartera

function Cartera({ abrirVenta }: { abrirVenta: (id: number) => void }) {
  const asignables = useAsignables()
  const catalogos = useCatalogos()
  const [soloVencida, setSoloVencida] = useState(false)
  const [tramo, setTramo] = useState<Tramo | null>(null)
  const [vendedor, setVendedor] = useState<string | null>(null)
  const [servicio, setServicio] = useState<string | null>(null)
  const [moraMinima, setMoraMinima] = useState<number | string>('')
  const [venceEn, setVenceEn] = useState<number | string>('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')

  // Un solo juego de filtros para las tres respuestas de la pantalla: los
  // totales de arriba, el corte por edades y la tabla. Si cada uno filtrara a
  // su manera, la tarjeta diría un número y la suma de la tabla otro, y es
  // justo lo que hoy pasa entre las hojas PAGOS y REV PAGOS.
  const filtros = {
    solo_vencida: soloVencida,
    ...(tramo ? { tramo } : {}),
    ...(vendedor ? { vendedor_id: Number(vendedor) } : {}),
    ...(servicio ? { servicio_id: Number(servicio) } : {}),
    ...(moraMinima !== '' ? { desde_dias: Number(moraMinima) } : {}),
    ...(venceEn !== '' ? { vence_en_dias: Number(venceEn) } : {}),
    ...(desde ? { desde } : {}),
    ...(hasta ? { hasta } : {}),
  }
  const resumen = useQuery({
    queryKey: ['cartera-resumen', filtros],
    queryFn: () => exigir(api.GET('/api/v1/cartera/resumen', { params: { query: filtros } })),
    placeholderData: keepPreviousData,
  })
  const edades = useQuery({
    queryKey: ['cartera-antiguedad', filtros],
    queryFn: () => exigir(api.GET('/api/v1/cartera/antiguedad', { params: { query: filtros } })),
    placeholderData: keepPreviousData,
  })
  const porEstado = useQuery({
    queryKey: ['cartera-por-estado'],
    queryFn: () => exigir(api.GET('/api/v1/cartera/por-estado')),
  })
  const [pagina, setPagina] = usePagina(filtros)
  const consulta = { ...filtros, pagina, tamano: TAMANO_PAGINA }
  const cartera = useQuery({
    queryKey: ['cartera', consulta],
    queryFn: () => exigir(api.GET('/api/v1/cartera', { params: { query: consulta } })),
    placeholderData: keepPreviousData,
  })

  const r = resumen.data
  return (
    <Stack>
      {/* Vendido, cobrado y cartera por separado: son preguntas distintas. «Por
          vencer» va al lado de «vencido» porque sin él de la cartera solo se ve
          la mitad: lo que ya se pasó de fecha, y no lo que se va a pasar. */}
      <SimpleGrid cols={{ base: 2, md: 5 }}>
        <Tarjeta titulo="Vendido" valor={r?.vendido} />
        <Tarjeta titulo="Cobrado" valor={r?.cobrado} />
        <Tarjeta titulo="Cartera (saldo)" valor={r?.cartera} sub={`${r?.ventas_con_saldo ?? 0} venta(s) con saldo`} />
        <Tarjeta titulo="Vencido" valor={r?.vencido} color="red" />
        <Tarjeta titulo="Por vencer" valor={r?.por_vencer} />
      </SimpleGrid>

      {/* El informe con el que se cobra. Cada tramo es un botón: se hace clic en
          «31 a 60 días» y abajo queda la lista de llamadas de ese tramo. */}
      <div>
        <Text size="xs" c="dimmed" tt="uppercase" fw={600} mb={6}>Cartera por edades</Text>
        <SimpleGrid cols={{ base: 2, md: 5 }}>
          {(edades.data ?? []).map((t) => (
            <Card key={t.tramo} withBorder padding="sm" style={{ cursor: 'pointer' }}
              bg={tramo === t.tramo ? 'var(--mantine-color-default-hover)' : undefined}
              onClick={() => setTramo(tramo === t.tramo ? null : t.tramo)}>
              <Group gap={6} justify="space-between" wrap="nowrap">
                <Text size="xs" fw={600} c={COLOR_TRAMO[t.tramo]}>{t.etiqueta}</Text>
                <Badge size="xs" variant="light" color={COLOR_TRAMO[t.tramo]}>{t.cuantas}</Badge>
              </Group>
              <Text size="md" fw={700}>{formatearPesos(t.saldo)}</Text>
              <Text size="xs" c="dimmed">
                {t.tramo === 'al_dia' ? 'nada vencido' : `${formatearPesos(t.vencido)} vencido`}
              </Text>
            </Card>))}
        </SimpleGrid>
      </div>

      {porEstado.data && porEstado.data.length > 0 && (
        <Group gap="xs">
          {porEstado.data.map((e) => (
            <Badge key={e.estado} variant="light" color="gray" size="lg">
              {e.estado}: {e.cuantas} · {formatearPesos(e.saldo)}
            </Badge>))}
        </Group>)}

      <Group align="flex-end" wrap="wrap">
        <Select label="Edad de la mora" w={170} clearable value={tramo}
          onChange={(v) => setTramo(v === null ? null : (v as Tramo))}
          data={TRAMOS.map((t) => ({ value: t.valor, label: t.titulo }))} />
        <Select label="Vendedor" w={200} clearable value={vendedor}
          onChange={(v) => setVendedor(v === null ? null : String(v))}
          data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))} />
        <Select label="Servicio" w={200} clearable value={servicio} searchable
          onChange={(v) => setServicio(v === null ? null : String(v))}
          data={aSelect(catalogos.data?.servicios)} />
        <NumberInput label="Mora de más de (días)" w={170} min={0} allowDecimal={false}
          value={moraMinima} onChange={(v) => setMoraMinima(typeof v === 'bigint' ? Number(v) : v)} />
        <NumberInput label="Le vence en (días)" w={160} min={0} allowDecimal={false}
          description="Para llamar antes" value={venceEn}
          onChange={(v) => setVenceEn(typeof v === 'bigint' ? Number(v) : v)} />
        <TextInput type="date" label="Vendido desde" value={desde}
          onChange={(e) => setDesde(e.currentTarget.value)} />
        <TextInput type="date" label="Vendido hasta" value={hasta}
          onChange={(e) => setHasta(e.currentTarget.value)} />
        <Switch mb={8} label="Solo lo vencido" checked={soloVencida}
          onChange={(e) => setSoloVencida(e.currentTarget.checked)} />
      </Group>

      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={1100}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Cliente</Table.Th><Table.Th>Servicio</Table.Th><Table.Th>Vendedor</Table.Th>
                <Table.Th ta="right">Pactado</Table.Th><Table.Th ta="right">Pagado</Table.Th>
                <Table.Th ta="right">Saldo</Table.Th><Table.Th ta="right">Vencido</Table.Th>
                <Table.Th ta="right">Por vencer</Table.Th><Table.Th>Edad de la mora</Table.Th>
                <Table.Th>Le vence</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {cartera.data?.items.map((f) => (
                <Table.Tr key={f.negocio_id} style={{ cursor: 'pointer' }} onClick={() => abrirVenta(f.negocio_id)}>
                  <Table.Td>
                    <Text size="sm" fw={500} component={Link} to={`/clientes/${f.cliente_id}`}
                      onClick={(e) => e.stopPropagation()} style={{ textDecoration: 'none', color: 'inherit' }}>
                      {f.cliente}
                    </Text>
                    <Text size="xs" c="dimmed">Venta del {formatearDia(f.fecha_venta)}</Text>
                  </Table.Td>
                  <Table.Td>{f.servicio}</Table.Td>
                  <Table.Td>{f.vendedor ?? '—'}</Table.Td>
                  <Table.Td ta="right">{formatearPesos(f.valor_pactado)}</Table.Td>
                  <Table.Td ta="right">{formatearPesos(f.total_pagado)}</Table.Td>
                  <Table.Td ta="right" fw={600}>{formatearPesos(f.saldo)}</Table.Td>
                  <Table.Td ta="right" c={f.vencido > 0 ? 'red' : 'dimmed'}>{formatearPesos(f.vencido)}</Table.Td>
                  <Table.Td ta="right" c="dimmed">{formatearPesos(f.por_vencer)}</Table.Td>
                  <Table.Td>
                    {/* El tramo es lo que se lee de un golpe; los días quedan al
                        lado para cuando hay que afinar la decisión. */}
                    {f.tramo === 'al_dia'
                      ? <Text size="sm" c="dimmed">Al día</Text>
                      : (
                        <Group gap={6} wrap="nowrap">
                          <Badge color={COLOR_TRAMO[f.tramo]} variant="light">
                            {NOMBRE_TRAMO[f.tramo]}
                          </Badge>
                          <Text size="xs" c="dimmed">{f.dias_vencido} d</Text>
                        </Group>)}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed">{formatearDia(f.proximo_vencimiento)}</Text>
                  </Table.Td>
                </Table.Tr>))}
              {cartera.data?.items.length === 0 && (
                <Table.Tr><Table.Td colSpan={10}>
                  <Text size="sm" c="dimmed" ta="center" py="lg">No hay ventas con saldo con esos filtros.</Text>
                </Table.Td></Table.Tr>)}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <PiePaginacion total={cartera.data?.total} pagina={pagina} onPagina={setPagina}
        unidad="venta(s)" extra={` · saldo ${formatearPesos(cartera.data?.suma_saldo)}`} />
    </Stack>
  )
}

function Tarjeta({ titulo, valor, sub, color }: {
  titulo: string; valor: number | undefined; sub?: string; color?: string
}) {
  return (
    <Card withBorder padding="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{titulo}</Text>
      <Text size="xl" fw={700} c={color}>{formatearPesos(valor)}</Text>
      {sub && <Text size="xs" c="dimmed">{sub}</Text>}
    </Card>)
}

// -------------------------------------------------------------------- pagos

function TablaPagos({ soloSinAsignar, abrirVenta, referenciaInicial = '' }: {
  soloSinAsignar?: boolean; abrirVenta: (id: number) => void; referenciaInicial?: string
}) {
  const { puede } = useSesion()
  const [asignando, setAsignando] = useState<Pago | null>(null)
  const [referencia, setReferencia] = useState(referenciaInicial)
  const [buscada] = useDebouncedValue(referencia.trim(), 300)
  const [pagina, setPagina] = usePagina([soloSinAsignar, buscada])
  const consulta = {
    sin_asignar: !!soloSinAsignar,
    ...(buscada ? { referencia: buscada } : {}),
    pagina, tamano: TAMANO_PAGINA,
  }
  const pagos = useQuery({
    queryKey: ['pagos', consulta],
    queryFn: () => exigir(api.GET('/api/v1/pagos', { params: { query: consulta } })),
    placeholderData: keepPreviousData,
  })

  if (pagos.isPending) return <Center h={120}><Loader color="teal" /></Center>
  return (
    <Stack>
      {soloSinAsignar && (
        <Alert color="orange" variant="light">
          Estos pagos entraron sin saberse de qué venta son. Mientras no tengan dueño no bajan ningún saldo.
        </Alert>)}
      {/* El filtro que responde «¿llegó este pago?» con el comprobante del
          cliente a la vista: se pega la referencia y listo (RF-029). */}
      <TextInput w={{ base: '100%', sm: 320 }} value={referencia} label="Referencia del comprobante"
        placeholder="Un pedazo basta" leftSection={<IconSearch size={16} />}
        onChange={(e) => setReferencia(e.currentTarget.value)} />
      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={820}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Fecha</Table.Th><Table.Th>Quién pagó</Table.Th><Table.Th>Referencia</Table.Th>
                <Table.Th ta="right">Monto</Table.Th><Table.Th>Estado</Table.Th><Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {pagos.data?.items.map((p) => (
                <Table.Tr key={p.id}>
                  <Table.Td>{formatearDia(p.fecha)}</Table.Td>
                  <Table.Td>{p.pagador_nombre ?? '—'}
                    {p.observacion && <Text size="xs" c="dimmed">{p.observacion}</Text>}</Table.Td>
                  <Table.Td>{p.referencia ?? '—'}</Table.Td>
                  <Table.Td ta="right">
                    {formatearPesos(p.monto_bruto)}
                    {p.costo_medio > 0 && <Text size="xs" c="dimmed">neto {formatearPesos(p.monto_neto)}</Text>}
                  </Table.Td>
                  <Table.Td><Badge variant="light" color={COLOR_ESTADO_PAGO[p.estado]}>
                    {NOMBRE_ESTADO_PAGO[p.estado]}</Badge></Table.Td>
                  <Table.Td>
                    <Group gap="xs" justify="flex-end" wrap="nowrap">
                      {p.negocio_id === null && puede('pagos.editar') && (
                        <Button size="compact-sm" onClick={() => setAsignando(p)}>Asignar a una venta</Button>)}
                      {p.negocio_id !== null && (
                        <Button size="compact-sm" variant="default" onClick={() => abrirVenta(p.negocio_id!)}>
                          Ver venta</Button>)}
                      {p.negocio_id !== null && puede('pagos.editar')
                        && (p.estado === 'confirmado' || p.estado === 'pendiente') && (
                        <CambiarEstado pago={p} />)}
                    </Group>
                  </Table.Td>
                </Table.Tr>))}
              {pagos.data?.items.length === 0 && (
                <Table.Tr><Table.Td colSpan={6}>
                  <Text size="sm" c="dimmed" ta="center" py="lg">
                    {buscada
                      ? `Ningún pago con la referencia «${buscada}».`
                      : soloSinAsignar ? 'No hay pagos por identificar.' : 'Todavía no hay pagos registrados.'}
                  </Text>
                </Table.Td></Table.Tr>)}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <PiePaginacion total={pagos.data?.total} pagina={pagina} onPagina={setPagina}
        unidad="pago(s)" />
      <ModalAsignar key={asignando?.id ?? 'ninguno'} pago={asignando} cerrar={() => setAsignando(null)} />
    </Stack>
  )
}

function invalidarTodo(cq: ReturnType<typeof useQueryClient>) {
  for (const k of ['pagos', 'cartera', 'cartera-resumen', 'cartera-por-estado', 'estado-financiero',
                   'ventas-repetidas']) {
    cq.invalidateQueries({ queryKey: [k] })
  }
}

/** Reversar o marcar duplicado: nunca se borra un pago (queda en el historial). */
function CambiarEstado({ pago }: { pago: Pago }) {
  const cq = useQueryClient()
  const [abierto, setAbierto] = useState(false)
  const [estado, setEstado] = useState<string | null>('reversado')
  const [obs, setObs] = useState('')
  const m = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/pagos/{pago_id}/estado', {
      params: { path: { pago_id: pago.id } },
      body: { estado: estado as 'reversado' | 'duplicado', ...(obs ? { observacion: obs } : {}) },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', title: 'Pago actualizado', message: 'El saldo se recalculó.' })
      invalidarTodo(cq); setAbierto(false)
    },
    onError: (e) => mostrarError(e),
  })
  return (
    <>
      <Button size="compact-sm" variant="subtle" color="gray" onClick={() => setAbierto(true)}>Reversar</Button>
      <Modal opened={abierto} onClose={() => setAbierto(false)} title="Reversar o marcar duplicado">
        <Stack>
          <Text size="sm">El pago de {formatearPesos(pago.monto_bruto)} deja de contar en el saldo, pero queda en el historial.</Text>
          <Select label="Motivo" allowDeselect={false} value={estado} onChange={(v) => setEstado(v === null ? null : String(v))}
            data={[{ value: 'reversado', label: 'Reversado' }, { value: 'duplicado', label: 'Duplicado' }]} />
          <Textarea label="Observación" value={obs} onChange={(e) => setObs(e.currentTarget.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setAbierto(false)}>Cancelar</Button>
            <Button color="red" loading={m.isPending} onClick={() => m.mutate()}>Confirmar</Button>
          </Group>
        </Stack>
      </Modal>
    </>)
}

/** Le pone dueño a un pago suelto. Se busca la venta en la cartera: es donde
 *  están las ventas con saldo, que son las únicas a las que tiene sentido asignar. */
function ModalAsignar({ pago, cerrar }: { pago: Pago | null; cerrar: () => void }) {
  const cq = useQueryClient()
  const [venta, setVenta] = useState<string | null>(null)
  const cartera = useQuery({
    queryKey: ['cartera', 'para-asignar'],
    queryFn: () => exigir(api.GET('/api/v1/cartera', { params: { query: { tamano: 100 } } })),
    enabled: pago !== null,
  })
  const m = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/pagos/{pago_id}/asignar', {
      params: { path: { pago_id: pago!.id } }, body: { negocio_id: Number(venta) },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', title: 'Pago asignado', message: 'Ya baja el saldo de esa venta.' })
      invalidarTodo(cq); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo asignar el pago'),
  })
  return (
    <Modal opened={pago !== null} onClose={cerrar} title="Asignar el pago a una venta">
      <Stack>
        <Text size="sm">
          Pago de {formatearPesos(pago?.monto_bruto)} del {formatearDia(pago?.fecha)}
          {pago?.pagador_nombre ? `, consignado por ${pago.pagador_nombre}` : ''}.
        </Text>
        <Select label="Venta" searchable placeholder="Busque por cliente" value={venta} onChange={(v) => setVenta(v === null ? null : String(v))}
          nothingFoundMessage="Ninguna venta con saldo coincide"
          data={(cartera.data?.items ?? []).map((f) => ({
            value: String(f.negocio_id),
            label: `${f.cliente} · ${f.servicio} · saldo ${formatearPesos(f.saldo)}`,
          }))} />
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button disabled={!venta} loading={m.isPending} onClick={() => m.mutate()}>Asignar</Button>
        </Group>
      </Stack>
    </Modal>)
}

/** Registrar un pago. La venta es opcional a propósito: si no se sabe de quién
 *  es, entra a la bandeja en vez de perderse (RF-043). */
function ModalPago({ abierto, cerrar }: { abierto: boolean; cerrar: () => void }) {
  const cq = useQueryClient()
  const [venta, setVenta] = useState<string | null>(null)
  const [monto, setMonto] = useState<number | string>('')
  const [costo, setCosto] = useState<number | string>('')
  const [fecha, setFecha] = useState('')
  const [referencia, setReferencia] = useState('')
  const [pagador, setPagador] = useState('')
  const [observacion, setObservacion] = useState('')

  const cartera = useQuery({
    queryKey: ['cartera', 'para-asignar'],
    queryFn: () => exigir(api.GET('/api/v1/cartera', { params: { query: { tamano: 100 } } })),
    enabled: abierto,
  })
  const limpiar = () => {
    setVenta(null); setMonto(''); setCosto(''); setFecha(''); setReferencia(''); setPagador(''); setObservacion('')
  }
  const m = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/pagos', {
      body: {
        monto_bruto: Number(monto), moneda: 'COP', costo_medio: Number(costo || 0),
        ...(venta ? { negocio_id: Number(venta) } : {}),
        ...(fecha ? { fecha } : {}),
        ...(referencia ? { referencia } : {}),
        ...(pagador ? { pagador_nombre: pagador } : {}),
        ...(observacion ? { observacion } : {}),
      },
    })),
    onSuccess: (p) => {
      notifications.show({
        color: 'teal', title: 'Pago registrado',
        message: p.negocio_id ? 'El saldo de la venta se recalculó.' : 'Quedó en la bandeja de pagos sin identificar.',
      })
      invalidarTodo(cq); limpiar(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo registrar el pago'),
  })

  return (
    <Modal opened={abierto} onClose={cerrar} title="Registrar un pago" size="lg">
      <Stack>
        <Select label="Venta" searchable clearable value={venta} onChange={(v) => setVenta(v === null ? null : String(v))}
          description="Si no sabe de cuál es, déjelo vacío: queda en la bandeja de pagos sin identificar"
          nothingFoundMessage="Ninguna venta con saldo coincide"
          data={(cartera.data?.items ?? []).map((f) => ({
            value: String(f.negocio_id),
            label: `${f.cliente} · ${f.servicio} · saldo ${formatearPesos(f.saldo)}`,
          }))} />
        <Group grow align="flex-start">
          <NumberInput label="Monto recibido" required thousandSeparator="." decimalSeparator=","
            prefix="$ " allowNegative={false} min={0} value={monto}
            onChange={(v) => setMonto(typeof v === 'bigint' ? Number(v) : v)} />
          <NumberInput label="Costo del medio" thousandSeparator="." decimalSeparator=","
            description="Lo que cobra la pasarela o el banco" prefix="$ " allowNegative={false}
            min={0} value={costo} onChange={(v) => setCosto(typeof v === 'bigint' ? Number(v) : v)} />
        </Group>
        <Group grow align="flex-start">
          <TextInput label="Fecha del pago" type="date" value={fecha}
            description="Vacío = hoy" onChange={(e) => setFecha(e.currentTarget.value)} />
          <TextInput label="Referencia" value={referencia} maxLength={80}
            onChange={(e) => setReferencia(e.currentTarget.value)} />
        </Group>
        <TextInput label="Quién consignó" description="Solo si no es el cliente" value={pagador}
          maxLength={160} onChange={(e) => setPagador(e.currentTarget.value)} />
        <Textarea label="Observación" value={observacion} onChange={(e) => setObservacion(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={m.isPending} disabled={!(Number(monto) > 0)} onClick={() => m.mutate()}>
            Registrar</Button>
        </Group>
      </Stack>
    </Modal>)
}

// --------------------------------------------------------- estado financiero

function ModalEstadoFinanciero({ negocioId, cerrar }: { negocioId: number | null; cerrar: () => void }) {
  const { puede } = useSesion()
  const cq = useQueryClient()
  const estado = useQuery({
    queryKey: ['estado-financiero', negocioId],
    queryFn: () => exigir(api.GET('/api/v1/ventas/{negocio_id}/estado-financiero', {
      params: { path: { negocio_id: negocioId! } },
    })),
    enabled: negocioId !== null,
  })
  const [ajustando, setAjustando] = useState(false)
  const plan = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/ventas/{negocio_id}/cuotas', {
      params: { path: { negocio_id: negocioId! } }, body: {},
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', title: 'Plan creado', message: 'Anticipo del 20 % y saldo del 80 %.' })
      invalidarTodo(cq)
    },
    onError: (e) => mostrarError(e, 'No se pudo crear el plan de cuotas'),
  })
  const e = estado.data

  return (
    <Modal opened={negocioId !== null} onClose={cerrar} size="xl" title="Estado financiero de la venta">
      {estado.isPending && <Center h={120}><Loader color="teal" /></Center>}
      {estado.isError && <Alert color="red">No se pudo abrir la venta.</Alert>}
      {e && (
        <Stack>
          <SimpleGrid cols={{ base: 2, sm: 4 }}>
            <Tarjeta titulo="Pactado" valor={e.valor_pactado} />
            <Tarjeta titulo="Pagado" valor={e.total_pagado} />
            <Tarjeta titulo="Ajustes" valor={e.ajustes} />
            <Tarjeta titulo="Saldo" valor={e.saldo} color={e.saldo > 0 ? 'red' : 'teal'} />
          </SimpleGrid>
          <Badge variant="light" size="lg" w="fit-content">{e.estado_financiero}</Badge>

          <Group justify="space-between">
            <Text fw={600}>Cuotas</Text>
            {e.cuotas.length === 0 && puede('negocios.editar') && (
              <Button size="compact-sm" loading={plan.isPending} onClick={() => plan.mutate()}>
                Crear plan 20 / 80</Button>)}
          </Group>
          {e.cuotas.length === 0
            ? <Alert color="orange" variant="light">
                Sin plan de cuotas esta venta nunca vence, y la cartera vencida no la va a mostrar.
              </Alert>
            : <Table.ScrollContainer minWidth={600}>
              <Table>
                <Table.Tbody>
                  {e.cuotas.map((c) => (
                    <Table.Tr key={c.numero}>
                      <Table.Td>{c.numero}. {c.concepto}</Table.Td>
                      <Table.Td>vence {formatearDia(c.fecha_pactada)}</Table.Td>
                      <Table.Td ta="right">{formatearPesos(c.monto)}</Table.Td>
                    </Table.Tr>))}
                </Table.Tbody>
              </Table>
              </Table.ScrollContainer>}

          <Text fw={600}>Pagos</Text>
          <Table.ScrollContainer minWidth={600}>
            <Table>
              <Table.Tbody>
                {e.pagos.map((p) => (
                  <Table.Tr key={p.id}>
                    <Table.Td>{formatearDia(p.fecha)}</Table.Td>
                    <Table.Td>{p.referencia ?? p.pagador_nombre ?? '—'}</Table.Td>
                    <Table.Td><Badge size="sm" variant="light" color={COLOR_ESTADO_PAGO[p.estado]}>
                      {NOMBRE_ESTADO_PAGO[p.estado]}</Badge></Table.Td>
                    <Table.Td ta="right">{formatearPesos(p.monto_bruto)}</Table.Td>
                    {/* El pago se resuelve desde acá y no solo desde «Todos los
                        pagos». Hace falta para la venta repetida: antes de poder
                        anular la copia hay que marcar duplicado el abono que
                        quedó anotado dos veces, y buscarlo en la lista general
                        obliga a salirse de la venta que se está arreglando. */}
                    <Table.Td ta="right">
                      {p.estado === 'confirmado' && puede('pagos.editar') && (
                        <CambiarEstado pago={p} />)}
                    </Table.Td>
                  </Table.Tr>))}
                {e.pagos.length === 0 && (
                  <Table.Tr><Table.Td><Text size="sm" c="dimmed">Sin pagos todavía.</Text></Table.Td></Table.Tr>)}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>

          <Group justify="space-between">
            <Text fw={600}>Ajustes</Text>
            {puede('ajustes.crear') && (
              <Button size="compact-sm" variant="default" onClick={() => setAjustando(true)}>Nuevo ajuste</Button>)}
          </Group>
          <Table.ScrollContainer minWidth={600}>
            <Table>
              <Table.Tbody>
                {e.ajustes_detalle.map((a) => (
                  <Table.Tr key={a.id}>
                    <Table.Td>{formatearDia(a.fecha)}</Table.Td>
                    <Table.Td>{NOMBRE_AJUSTE[a.tipo]}</Table.Td>
                    <Table.Td>{a.motivo}</Table.Td>
                    <Table.Td ta="right">{formatearPesos(a.monto)}</Table.Td>
                  </Table.Tr>))}
                {e.ajustes_detalle.length === 0 && (
                  <Table.Tr><Table.Td><Text size="sm" c="dimmed">Sin ajustes.</Text></Table.Td></Table.Tr>)}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <ModalAjuste key={String(ajustando)} abierto={ajustando} negocioId={negocioId!}
            cerrar={() => setAjustando(false)} />
        </Stack>)}
    </Modal>)
}

function ModalAjuste({ abierto, negocioId, cerrar }: {
  abierto: boolean; negocioId: number; cerrar: () => void
}) {
  const cq = useQueryClient()
  const [tipo, setTipo] = useState<string | null>('descuento')
  const [monto, setMonto] = useState<number | string>('')
  const [motivo, setMotivo] = useState('')
  const m = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/ventas/{negocio_id}/ajustes', {
      params: { path: { negocio_id: negocioId } },
      body: { tipo: tipo as 'reembolso' | 'cargo' | 'descuento' | 'condonacion', monto: Number(monto), motivo },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', title: 'Ajuste registrado', message: 'El saldo se recalculó.' })
      invalidarTodo(cq); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo registrar el ajuste'),
  })
  return (
    <Modal opened={abierto} onClose={cerrar} title="Nuevo ajuste">
      <Stack>
        <Select label="Tipo" allowDeselect={false} value={tipo} onChange={(v) => setTipo(v === null ? null : String(v))}
          description="El monto va en positivo: el tipo decide si sube o baja la deuda"
          data={Object.entries(NOMBRE_AJUSTE).map(([value, label]) => ({ value, label }))} />
        <NumberInput label="Monto" thousandSeparator="." decimalSeparator="," prefix="$ " min={0}
          allowNegative={false} value={monto} onChange={(v) => setMonto(typeof v === 'bigint' ? Number(v) : v)} />
        <Textarea label="Motivo" required minLength={3} maxLength={400} value={motivo}
          onChange={(e) => setMotivo(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={m.isPending} disabled={!(Number(monto) > 0) || motivo.trim().length < 3}
            onClick={() => m.mutate()}>Registrar</Button>
        </Group>
      </Stack>
    </Modal>)
}

// --------------------------------------------------------- ventas repetidas

/** La misma venta anotada dos veces (RF-040).
 *
 *  La carga de los Excel trajo el mismo negocio dos veces cuando aparecía en
 *  dos hojas del mismo libro: la idempotencia es por `(archivo, hoja, fila)`,
 *  así que el mismo hecho en dos sitios son dos filas. Medido sobre lo cargado:
 *  16 casos y $18.006.000 de más en la cartera.
 *
 *  Esta pantalla NO decide por nadie, y es a propósito. En esas 16 los pagos
 *  están repartidos entre las dos copias, así que cuál se queda y qué se hace
 *  con cada abono es una decisión de quien lleva las cuentas. Lo que hace la
 *  pantalla es poner junto lo que hace falta para decidir: de qué hoja salió
 *  cada copia, qué pagos tiene y cuántos trámites cuelgan de ella.
 */
function VentasRepetidas({ grupos, cargando, abrirVenta }: {
  grupos: Esquemas['VentaRepetida'][] | undefined
  cargando: boolean
  abrirVenta: (id: number) => void
}) {
  const [anulando, setAnulando] = useState<Esquemas['CopiaDeVenta'] | null>(null)

  if (cargando) return <Center h={160}><Loader color="teal" /></Center>
  if (!grupos?.length) {
    return (
      <Alert color="teal" variant="light" title="No hay ventas repetidas">
        Ninguna venta coincide con otra en cliente, servicio, fecha y valor.
      </Alert>)
  }

  const deMas = grupos.reduce((s, g) => s + g.valor_pactado * (g.copias.length - 1), 0)

  return (
    <Stack>
      <Alert color="orange" variant="light" title="Qué es esto y por qué hay que mirarlo">
        <Text size="sm">
          Estas {grupos.length} ventas coinciden con otra en cliente, servicio, fecha y valor:
          es casi seguro la misma venta anotada dos veces al cargar los Excel, porque el mismo
          negocio aparecía en dos hojas del mismo libro. Están inflando la cartera
          en {formatearPesos(deMas)}, que es el número con el que se decide a quién se le cobra.
        </Text>
        <Text size="sm" mt="xs">
          <b>Los pagos se resuelven primero.</b> En varias de estas los abonos quedaron
          repartidos entre las dos copias, así que anular una sin más haría desaparecer plata
          que sí entró. Abra la venta, marque <b>duplicado</b> el abono que esté anotado dos
          veces —o muévalo a la copia que se queda— y entonces anule la otra.
        </Text>
      </Alert>

      {grupos.map((g) => (
        <Card key={`${g.cliente_id}-${g.copias[0].negocio_id}`} withBorder>
          <Group justify="space-between" align="flex-start" mb="sm">
            <div>
              <Text fw={600}>
                <Link to={`/clientes/${g.cliente_id}`}>{g.cliente ?? 'Sin cliente'}</Link>
              </Text>
              <Text size="sm" c="dimmed">
                {g.servicio ?? 'Sin servicio'} · {formatearDia(g.fecha_venta)} · {formatearPesos(g.valor_pactado)}
              </Text>
            </div>
            <Badge color="red" variant="light">{g.copias.length} copias</Badge>
          </Group>

          <Table.ScrollContainer minWidth={620}>
            <Table verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Venta</Table.Th><Table.Th>De dónde salió</Table.Th>
                  <Table.Th ta="right">Pagos</Table.Th><Table.Th ta="right">Trámites</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {g.copias.map((c) => (
                  <Table.Tr key={c.negocio_id}>
                    <Table.Td>#{c.negocio_id}</Table.Td>
                    <Table.Td>
                      <Text size="sm">{c.origen}</Text>
                      {c.origen_fila !== null && c.origen_fila !== undefined && (
                        <Text size="xs" c="dimmed">fila {c.origen_fila}</Text>)}
                    </Table.Td>
                    <Table.Td ta="right">
                      {c.pagos === 0
                        ? <Text size="sm" c="dimmed">ninguno</Text>
                        : <Text size="sm">{c.pagos} · {formatearPesos(c.pagado)}</Text>}
                    </Table.Td>
                    {/* Los trámites importan para decidir: la copia que ya tiene
                        el trámite abierto con su historial es la que conviene
                        conservar. */}
                    <Table.Td ta="right"><Text size="sm">{c.tramites}</Text></Table.Td>
                    <Table.Td ta="right">
                      <Group gap="xs" justify="flex-end" wrap="nowrap">
                        <Button size="compact-sm" variant="subtle"
                          onClick={() => abrirVenta(c.negocio_id)}>Ver y resolver pagos</Button>
                        <Button size="compact-sm" variant="light" color="red"
                          onClick={() => setAnulando(c)}>Anular esta</Button>
                      </Group>
                    </Table.Td>
                  </Table.Tr>))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>))}

      <ModalAnular key={anulando?.negocio_id ?? 'ninguno'} copia={anulando}
        cerrar={() => setAnulando(null)} />
    </Stack>)
}

/** Anular es irreversible desde la pantalla, así que pide el motivo escrito.
 *
 *  El motivo no es trámite: es lo que explica por qué la cartera bajó. Sin él,
 *  el mes entrante nadie puede responder por qué los totales cambiaron, y una
 *  cifra que nadie puede explicar es una cifra en la que nadie confía.
 */
function ModalAnular({ copia, cerrar }: {
  copia: Esquemas['CopiaDeVenta'] | null; cerrar: () => void
}) {
  const cq = useQueryClient()
  const [motivo, setMotivo] = useState('')
  const m = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/ventas/{negocio_id}/anular', {
      params: { path: { negocio_id: copia!.negocio_id } }, body: { motivo },
    })),
    onSuccess: () => {
      notifications.show({
        color: 'teal', title: 'Venta anulada',
        message: 'Sale de la cartera. La fila queda, con quién la anuló y por qué.',
      })
      invalidarTodo(cq); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo anular la venta'),
  })

  return (
    <Modal opened={copia !== null} onClose={cerrar} title={`Anular la venta #${copia?.negocio_id}`}>
      <Stack>
        <Text size="sm">
          La venta deja de contar en la cartera y en los informes. <b>No se borra:</b> la fila
          queda con quién la anuló, cuándo y por qué.
        </Text>
        {!!copia?.pagos && (
          <Alert color="orange" variant="light">
            Esta copia tiene {copia.pagos} pago(s) por {formatearPesos(copia.pagado)}. El sistema
            no va a dejar anularla así: primero marque duplicado el abono repetido, o muévalo a la
            copia que se queda, desde «Ver y resolver pagos».
          </Alert>)}
        <Textarea label="Motivo" autosize minRows={2} value={motivo}
          placeholder="Repetida: la misma venta ya está cargada desde la hoja PAGOS"
          onChange={(e) => setMotivo(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button color="red" disabled={motivo.trim().length < 5} loading={m.isPending}
            onClick={() => m.mutate()}>Anular</Button>
        </Group>
      </Stack>
    </Modal>)
}
