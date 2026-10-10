import {
  Alert, Badge, Button, Card, Center, Group, Loader, Modal, NumberInput, Select, SimpleGrid, Stack,
  Switch, Table, Tabs, Text, TextInput, Textarea, Title,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconPlus } from '@tabler/icons-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { BotonExportar } from '../componentes/BotonExportar'
import { useSesion } from '../auth/sesion'
import { useAsignables } from '../lib/catalogos'
import { mostrarError } from '../lib/errores'
import { formatearPesos } from '../lib/formato'

type Pago = Esquemas['PagoSalida']

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

  const sinAsignar = useQuery({
    queryKey: ['pagos', 'sin-asignar-conteo'],
    queryFn: () => exigir(api.GET('/api/v1/pagos', { params: { query: { sin_asignar: true, tamano: 1 } } })),
  })

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Pagos y cartera</Title>
          <Text size="sm" c="dimmed">Quién debe, cuánto y desde cuándo; y los pagos que aún no tienen dueño.</Text>
        </div>
        {puede('pagos.crear') && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setRegistrando(true)}>
            Registrar pago
          </Button>)}
      </Group>

      <Tabs defaultValue="cartera" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="cartera">Cartera</Tabs.Tab>
          <Tabs.Tab value="bandeja"
            rightSection={sinAsignar.data?.total ? <Badge size="sm" color="orange">{sinAsignar.data.total}</Badge> : null}>
            Pagos sin identificar
          </Tabs.Tab>
          <Tabs.Tab value="pagos">Todos los pagos</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="cartera" pt="md"><Cartera abrirVenta={setVentaAbierta} /></Tabs.Panel>
        <Tabs.Panel value="bandeja" pt="md">
          <TablaPagos soloSinAsignar abrirVenta={setVentaAbierta} />
        </Tabs.Panel>
        <Tabs.Panel value="pagos" pt="md"><TablaPagos abrirVenta={setVentaAbierta} /></Tabs.Panel>
      </Tabs>

      <ModalPago abierto={registrando} cerrar={() => setRegistrando(false)} />
      <ModalEstadoFinanciero negocioId={ventaAbierta} cerrar={() => setVentaAbierta(null)} />
    </Stack>
  )
}

// ------------------------------------------------------------------ cartera

function Cartera({ abrirVenta }: { abrirVenta: (id: number) => void }) {
  const asignables = useAsignables()
  const [soloVencida, setSoloVencida] = useState(false)
  const [vendedor, setVendedor] = useState<string | null>(null)
  const [moraMinima, setMoraMinima] = useState<number | string>('')

  const resumen = useQuery({
    queryKey: ['cartera-resumen'],
    queryFn: () => exigir(api.GET('/api/v1/cartera/resumen')),
  })
  const porEstado = useQuery({
    queryKey: ['cartera-por-estado'],
    queryFn: () => exigir(api.GET('/api/v1/cartera/por-estado')),
  })
  const consulta = {
    solo_vencida: soloVencida,
    ...(vendedor ? { vendedor_id: Number(vendedor) } : {}),
    ...(moraMinima !== '' ? { desde_dias: Number(moraMinima) } : {}),
    tamano: 100,
  }
  const cartera = useQuery({
    queryKey: ['cartera', consulta],
    queryFn: () => exigir(api.GET('/api/v1/cartera', { params: { query: consulta } })),
    placeholderData: keepPreviousData,
  })

  const r = resumen.data
  return (
    <Stack>
      {/* Vendido, cobrado y cartera por separado: son tres preguntas distintas */}
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Tarjeta titulo="Vendido" valor={r?.vendido} />
        <Tarjeta titulo="Cobrado" valor={r?.cobrado} />
        <Tarjeta titulo="Cartera (saldo)" valor={r?.cartera} sub={`${r?.ventas_con_saldo ?? 0} venta(s) con saldo`} />
        <Tarjeta titulo="Vencido" valor={r?.vencido} color="red" />
      </SimpleGrid>

      {porEstado.data && porEstado.data.length > 0 && (
        <Group gap="xs">
          {porEstado.data.map((e) => (
            <Badge key={e.estado} variant="light" color="gray" size="lg">
              {e.estado}: {e.cuantas} · {formatearPesos(e.saldo)}
            </Badge>))}
        </Group>)}

      <Group align="flex-end">
        <Select label="Vendedor" w={200} clearable value={vendedor}
          onChange={(v) => setVendedor(v === null ? null : String(v))}
          data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))} />
        <NumberInput label="Mora de más de (días)" w={180} min={0} allowDecimal={false}
          value={moraMinima} onChange={(v) => setMoraMinima(typeof v === 'bigint' ? Number(v) : v)} />
        <Switch mb={8} label="Solo lo vencido" checked={soloVencida}
          onChange={(e) => setSoloVencida(e.currentTarget.checked)} />
        <div style={{ marginLeft: 'auto' }}>
          <BotonExportar lista="cartera" permiso="pagos.exportar" filtros={{
            solo_vencida: soloVencida, vendedor_id: vendedor ? Number(vendedor) : undefined,
            desde_dias: moraMinima !== '' ? Number(moraMinima) : undefined }} />
        </div>
      </Group>

      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={980}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Cliente</Table.Th><Table.Th>Servicio</Table.Th><Table.Th>Vendedor</Table.Th>
                <Table.Th ta="right">Pactado</Table.Th><Table.Th ta="right">Pagado</Table.Th>
                <Table.Th ta="right">Saldo</Table.Th><Table.Th ta="right">Vencido</Table.Th>
                <Table.Th ta="right">Por vencer</Table.Th><Table.Th>Mora</Table.Th>
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
                    {f.dias_vencido > 0
                      ? <Badge color="red" variant="light">{f.dias_vencido} d</Badge>
                      : <Text size="sm" c="dimmed">al día</Text>}
                  </Table.Td>
                </Table.Tr>))}
              {cartera.data?.items.length === 0 && (
                <Table.Tr><Table.Td colSpan={9}>
                  <Text size="sm" c="dimmed" ta="center" py="lg">No hay ventas con saldo con esos filtros.</Text>
                </Table.Td></Table.Tr>)}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Text size="sm" c="dimmed">
        {cartera.data?.total ?? 0} venta(s) · saldo {formatearPesos(cartera.data?.suma_saldo)}
      </Text>
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

function TablaPagos({ soloSinAsignar, abrirVenta }: {
  soloSinAsignar?: boolean; abrirVenta: (id: number) => void
}) {
  const { puede } = useSesion()
  const [asignando, setAsignando] = useState<Pago | null>(null)
  const pagos = useQuery({
    queryKey: ['pagos', { soloSinAsignar: !!soloSinAsignar }],
    queryFn: () => exigir(api.GET('/api/v1/pagos', {
      params: { query: { sin_asignar: !!soloSinAsignar, tamano: 100 } },
    })),
    placeholderData: keepPreviousData,
  })

  if (pagos.isPending) return <Center h={120}><Loader color="teal" /></Center>
  return (
    <Stack>
      {soloSinAsignar && (
        <Alert color="orange" variant="light">
          Estos pagos entraron sin saberse de qué venta son. Mientras no tengan dueño no bajan ningún saldo.
        </Alert>)}
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
                    {soloSinAsignar ? 'No hay pagos por identificar.' : 'Todavía no hay pagos registrados.'}
                  </Text>
                </Table.Td></Table.Tr>)}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <ModalAsignar key={asignando?.id ?? 'ninguno'} pago={asignando} cerrar={() => setAsignando(null)} />
    </Stack>
  )
}

function invalidarTodo(cq: ReturnType<typeof useQueryClient>) {
  for (const k of ['pagos', 'cartera', 'cartera-resumen', 'cartera-por-estado', 'estado-financiero']) {
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
            : <Table>
                <Table.Tbody>
                  {e.cuotas.map((c) => (
                    <Table.Tr key={c.numero}>
                      <Table.Td>{c.numero}. {c.concepto}</Table.Td>
                      <Table.Td>vence {formatearDia(c.fecha_pactada)}</Table.Td>
                      <Table.Td ta="right">{formatearPesos(c.monto)}</Table.Td>
                    </Table.Tr>))}
                </Table.Tbody>
              </Table>}

          <Text fw={600}>Pagos</Text>
          <Table>
            <Table.Tbody>
              {e.pagos.map((p) => (
                <Table.Tr key={p.id}>
                  <Table.Td>{formatearDia(p.fecha)}</Table.Td>
                  <Table.Td>{p.referencia ?? p.pagador_nombre ?? '—'}</Table.Td>
                  <Table.Td><Badge size="sm" variant="light" color={COLOR_ESTADO_PAGO[p.estado]}>
                    {NOMBRE_ESTADO_PAGO[p.estado]}</Badge></Table.Td>
                  <Table.Td ta="right">{formatearPesos(p.monto_bruto)}</Table.Td>
                </Table.Tr>))}
              {e.pagos.length === 0 && (
                <Table.Tr><Table.Td><Text size="sm" c="dimmed">Sin pagos todavía.</Text></Table.Td></Table.Tr>)}
            </Table.Tbody>
          </Table>

          <Group justify="space-between">
            <Text fw={600}>Ajustes</Text>
            {puede('ajustes.crear') && (
              <Button size="compact-sm" variant="default" onClick={() => setAjustando(true)}>Nuevo ajuste</Button>)}
          </Group>
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
