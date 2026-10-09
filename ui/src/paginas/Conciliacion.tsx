import {
  Alert, Badge, Button, Card, Center, Group, Loader, Modal, NumberInput, Select, SimpleGrid, Stack,
  Table, Text, TextInput, Textarea, Title,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconWand } from '@tabler/icons-react'
import { useState } from 'react'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { mostrarError } from '../lib/errores'
import { formatearFechaHora, formatearPesos } from '../lib/formato'

type Movimiento = Esquemas['MovimientoSalida']
type Estado = Movimiento['estado']

const ESTADOS: Estado[] = ['sin_conciliar', 'conciliado', 'parcial', 'duplicado', 'reversado', 'descartado']
const NOMBRE: Record<Estado, string> = {
  sin_conciliar: 'Sin conciliar', conciliado: 'Conciliado', parcial: 'Parcial',
  duplicado: 'Duplicado', reversado: 'Reversado', descartado: 'Descartado',
}
const COLOR: Record<Estado, string> = {
  sin_conciliar: 'orange', conciliado: 'teal', parcial: 'yellow',
  duplicado: 'gray', reversado: 'gray', descartado: 'gray',
}

// El movimiento trae la fecha como AAAA-MM-DD. Se parte el texto: pasarla por
// Date la corre un día atrás en Bogotá (medianoche UTC).
const dia = (d: string | null | undefined) => (d ? d.split('-').reverse().join('/') : '—')

function invalidar(cq: ReturnType<typeof useQueryClient>) {
  // Conciliar puede crear un pago, así que también mueve la cartera.
  for (const k of ['conciliacion', 'pagos', 'cartera', 'cartera-resumen', 'cartera-por-estado', 'estado-financiero']) {
    cq.invalidateQueries({ queryKey: [k] })
  }
}

/** Conciliación bancaria (RF-044): cuadrar el extracto del banco contra los pagos.
 *  Los candidatos los busca el backend por valor y fecha, nunca por nombre: quien
 *  consigna muchas veces no es el cliente y un cruce falso deja una venta como
 *  pagada con plata de otro. */
export function Conciliacion() {
  const { puede } = useSesion()
  const cq = useQueryClient()
  const [estado, setEstado] = useState<Estado>('sin_conciliar')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [abierto, setAbierto] = useState<Movimiento | null>(null)

  const rango = { ...(desde ? { desde } : {}), ...(hasta ? { hasta } : {}) }
  const resumen = useQuery({
    queryKey: ['conciliacion', 'resumen', rango],
    queryFn: () => exigir(api.GET('/api/v1/conciliacion/resumen', { params: { query: rango } })),
  })
  const consulta = { estado, ...rango, tamano: 100 }
  const movimientos = useQuery({
    queryKey: ['conciliacion', 'movimientos', consulta],
    queryFn: () => exigir(api.GET('/api/v1/conciliacion/movimientos', { params: { query: consulta } })),
    placeholderData: keepPreviousData,
  })

  const cruzar = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/conciliacion/cruzar', { body: rango })),
    onSuccess: (r) => {
      notifications.show({
        color: 'teal', title: 'Cruce automático',
        message: `${r.cuadrados} cuadrado(s). ${r.ambiguos} con más de un candidato y ${r.sin_candidato} sin candidato quedan para revisar a mano.`,
      })
      invalidar(cq)
    },
    onError: (e) => mostrarError(e, 'No se pudo cruzar'),
  })
  const confirmarCruce = () => modals.openConfirmModal({
    title: 'Cruzar lo que no tiene duda',
    children: (
      <Text size="sm">
        Se cuadran solos los movimientos con un único pago del mismo valor y el mismo día. Si hay dos
        pagos posibles, no se toca nada. Se puede deshacer movimiento por movimiento.
      </Text>),
    labels: { confirm: 'Cruzar', cancel: 'Cancelar' },
    onConfirm: () => cruzar.mutate(),
  })

  const r = resumen.data
  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Conciliación bancaria</Title>
          <Text size="sm" c="dimmed">Cuadrar el extracto del banco contra los pagos registrados.</Text>
        </div>
        {puede('pagos.editar') && (
          <Button leftSection={<IconWand size={16} />} loading={cruzar.isPending} onClick={confirmarCruce}>
            Cruzar lo que no tiene duda</Button>)}
      </Group>

      <SimpleGrid cols={{ base: 2, md: 6 }}>
        {ESTADOS.map((e) => (
          <Card key={e} withBorder padding="sm" onClick={() => setEstado(e)}
            style={{ cursor: 'pointer', borderColor: e === estado ? 'var(--mantine-color-teal-6)' : undefined }}>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{NOMBRE[e]}</Text>
            <Text size="xl" fw={700}>{r?.[e].cuantos ?? '—'}</Text>
            <Text size="xs" c="dimmed">{formatearPesos(r?.[e].total)}</Text>
          </Card>))}
      </SimpleGrid>

      <Group align="flex-end">
        <TextInput label="Desde" type="date" value={desde} onChange={(e) => setDesde(e.currentTarget.value)} />
        <TextInput label="Hasta" type="date" value={hasta} onChange={(e) => setHasta(e.currentTarget.value)} />
        <Select label="Estado" w={200} allowDeselect={false} value={estado}
          onChange={(v) => v && setEstado(v as Estado)}
          data={ESTADOS.map((e) => ({ value: e, label: NOMBRE[e] }))} />
      </Group>

      {movimientos.isPending ? <Center h={120}><Loader color="teal" /></Center> : (
        <Card withBorder padding={0}>
          <Table.ScrollContainer minWidth={900}>
            <Table verticalSpacing="sm" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Fecha</Table.Th><Table.Th>Banco</Table.Th><Table.Th>Descripción</Table.Th>
                  <Table.Th>Referencia</Table.Th><Table.Th ta="right">Valor</Table.Th>
                  <Table.Th>Estado</Table.Th><Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {movimientos.data?.items.map((m) => (
                  <Table.Tr key={m.id}>
                    <Table.Td>{dia(m.fecha)}</Table.Td>
                    <Table.Td>{m.banco}</Table.Td>
                    <Table.Td>{m.descripcion ?? '—'}
                      {m.motivo_descarte && <Text size="xs" c="dimmed">{m.motivo_descarte}</Text>}
                      {m.cliente && m.negocio_id && (
                        <Text size="xs" c="dimmed">Pago de {m.cliente}</Text>)}</Table.Td>
                    <Table.Td>{m.referencia ?? '—'}</Table.Td>
                    <Table.Td ta="right" fw={600}>{formatearPesos(m.valor)}</Table.Td>
                    <Table.Td><Badge variant="light" color={COLOR[m.estado]}>{NOMBRE[m.estado]}</Badge>
                      {m.conciliado_en && (
                        <Text size="xs" c="dimmed">{formatearFechaHora(m.conciliado_en)}</Text>)}</Table.Td>
                    <Table.Td ta="right">
                      {puede('pagos.ver') && (
                        <Button size="compact-sm" variant={m.estado === 'sin_conciliar' ? 'filled' : 'default'}
                          onClick={() => setAbierto(m)}>
                          {m.estado === 'sin_conciliar' ? 'Revisar' : 'Ver'}</Button>)}
                    </Table.Td>
                  </Table.Tr>))}
                {movimientos.data?.items.length === 0 && (
                  <Table.Tr><Table.Td colSpan={7}>
                    <Text size="sm" c="dimmed" ta="center" py="lg">
                      No hay movimientos {NOMBRE[estado].toLowerCase()} en ese rango.</Text>
                  </Table.Td></Table.Tr>)}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>)}
      <Text size="sm" c="dimmed">
        {movimientos.data?.total ?? 0} movimiento(s) · {formatearPesos(movimientos.data?.suma)}
      </Text>

      <ModalMovimiento key={abierto?.id ?? 'ninguno'} movimiento={abierto} cerrar={() => setAbierto(null)} />
    </Stack>
  )
}

type Accion = 'duplicado' | 'reversado' | 'descartar' | null

/** Un movimiento: sus candidatos y todo lo que se puede hacer con él. */
function ModalMovimiento({ movimiento, cerrar }: { movimiento: Movimiento | null; cerrar: () => void }) {
  const { puede } = useSesion()
  const cq = useQueryClient()
  const editar = puede('pagos.editar')
  const pendiente = movimiento?.estado === 'sin_conciliar'
  const [accion, setAccion] = useState<Accion>(null)
  const [texto, setTexto] = useState('')
  const [original, setOriginal] = useState<number | string>('')
  const [venta, setVenta] = useState<string | null>(null)

  const sugerencias = useQuery({
    queryKey: ['conciliacion', 'candidatos', movimiento?.id],
    queryFn: () => exigir(api.GET('/api/v1/conciliacion/movimientos/{movimiento_id}/candidatos', {
      params: { path: { movimiento_id: movimiento!.id } },
    })),
    enabled: pendiente,
  })
  const cartera = useQuery({
    queryKey: ['cartera', 'para-asignar'],
    queryFn: () => exigir(api.GET('/api/v1/cartera', { params: { query: { tamano: 100 } } })),
    enabled: pendiente && editar,
  })

  const id = movimiento?.id ?? 0
  const ruta = (r: 'conciliar' | 'parcial' | 'duplicado' | 'reversado' | 'descartar' | 'deshacer') =>
    `/api/v1/conciliacion/movimientos/{movimiento_id}/${r}` as const
  const ok = (mensaje: string) => {
    notifications.show({ color: 'teal', title: 'Movimiento actualizado', message: mensaje })
    invalidar(cq); cerrar()
  }
  const conciliar = useMutation({
    mutationFn: (cuerpo: { pago_id?: number; negocio_id?: number }) => exigir(
      api.POST(ruta('conciliar'), { params: { path: { movimiento_id: id } }, body: cuerpo })),
    onSuccess: () => ok('Quedó cuadrado contra el pago.'),
    onError: (e) => mostrarError(e, 'No se pudo conciliar'),
  })
  const parcial = useMutation({
    mutationFn: (pago_id: number) => exigir(
      api.POST(ruta('parcial'), { params: { path: { movimiento_id: id } }, body: { pago_id } })),
    onSuccess: () => ok('Quedó marcado como parcial: sigue pendiente de completar.'),
    onError: (e) => mostrarError(e, 'No se pudo marcar como parcial'),
  })
  const marcar = useMutation({
    mutationFn: () => {
      const p = { params: { path: { movimiento_id: id } } }
      if (accion === 'duplicado') {
        return exigir(api.POST(ruta('duplicado'), { ...p, body: { duplicado_de_id: Number(original) } }))
      }
      if (accion === 'reversado') return exigir(api.POST(ruta('reversado'), { ...p, body: { motivo: texto } }))
      return exigir(api.POST(ruta('descartar'), { ...p, body: { motivo: texto } }))
    },
    onSuccess: () => ok('Quedó marcado; la línea sigue en el extracto.'),
    onError: (e) => mostrarError(e),
  })
  const deshacer = useMutation({
    mutationFn: () => exigir(api.POST(ruta('deshacer'), { params: { path: { movimiento_id: id } } })),
    onSuccess: () => ok('Volvió a la bandeja. Si se había creado un pago, ese pago no se borra.'),
    onError: (e) => mostrarError(e, 'No se pudo deshacer'),
  })

  const m = movimiento
  const puedeEnviar = accion === 'duplicado' ? Number(original) > 0 : texto.trim().length >= 3
  return (
    <Modal opened={m !== null} onClose={cerrar} size="xl" title="Movimiento del banco">
      {m && (
        <Stack>
          <Group justify="space-between">
            <div>
              <Text fw={700} size="lg">{formatearPesos(m.valor)}</Text>
              <Text size="sm" c="dimmed">{m.banco} · {dia(m.fecha)} · {m.descripcion ?? 'sin descripción'}</Text>
              {m.referencia && <Text size="sm" c="dimmed">Referencia {m.referencia}</Text>}
            </div>
            <Badge size="lg" variant="light" color={COLOR[m.estado]}>{NOMBRE[m.estado]}</Badge>
          </Group>
          {(m.nota_cliente || m.nota_abono) && (
            <Text size="sm">{[m.nota_cliente, m.nota_abono].filter(Boolean).join(' · ')}</Text>)}
          {m.pago_id && (
            <Text size="sm">
              Cuadrado contra el pago #{m.pago_id}
              {m.negocio_id && m.cliente ? ` de ${m.cliente}` : ' (sin venta asignada)'}.
            </Text>)}
          {m.duplicado_de_id && <Text size="sm">Repetido del movimiento #{m.duplicado_de_id}.</Text>}

          {pendiente && (
            <>
              <Text fw={600}>Pagos que calzan por valor y fecha</Text>
              {sugerencias.isPending && <Center h={60}><Loader color="teal" size="sm" /></Center>}
              {sugerencias.data && sugerencias.data.candidatos.length === 0 && (
                <Alert color="orange" variant="light">
                  Ningún pago registrado calza con este valor y esta fecha. Si el cliente avisó que
                  consignó, se puede crear el pago desde acá contra su venta.
                </Alert>)}
              {sugerencias.data && sugerencias.data.candidatos.length > 0 && (
                <>
                  {!sugerencias.data.sin_duda && (
                    <Alert color="yellow" variant="light">
                      No hay un único candidato exacto: elija con cuidado. El nombre de quien consignó
                      no sirve para decidir, muchas veces no es el cliente.
                    </Alert>)}
                  <Table>
                    <Table.Tbody>
                      {sugerencias.data.candidatos.map((c) => (
                        <Table.Tr key={c.pago_id}>
                          <Table.Td>
                            {c.cliente && c.negocio_id
                              ? <Text size="sm">{c.cliente}</Text>
                              : <Text size="sm" c="dimmed">Pago sin identificar</Text>}
                            <Text size="xs" c="dimmed">Pago #{c.pago_id} · {dia(c.fecha)}</Text>
                          </Table.Td>
                          <Table.Td ta="right">{formatearPesos(c.monto)}</Table.Td>
                          <Table.Td>
                            {c.exacto
                              ? <Badge color="teal" variant="light">Exacto</Badge>
                              : <Badge color="gray" variant="light">
                                  {c.dias_de_diferencia} día(s) de diferencia</Badge>}
                          </Table.Td>
                          <Table.Td>
                            {editar && (
                              <Group gap="xs" justify="flex-end" wrap="nowrap">
                                <Button size="compact-sm" loading={conciliar.isPending}
                                  onClick={() => conciliar.mutate({ pago_id: c.pago_id })}>Conciliar</Button>
                                <Button size="compact-sm" variant="default" loading={parcial.isPending}
                                  onClick={() => parcial.mutate(c.pago_id)}>Cubre una parte</Button>
                              </Group>)}
                          </Table.Td>
                        </Table.Tr>))}
                    </Table.Tbody>
                  </Table>
                </>)}

              {editar && (
                <Group align="flex-end" wrap="nowrap">
                  <Select style={{ flex: 1 }} label="O crear el pago contra una venta" searchable clearable
                    placeholder="Busque por cliente" value={venta}
                    onChange={(v) => setVenta(v === null ? null : String(v))}
                    description="El pago nace con la fecha y el valor de este movimiento"
                    nothingFoundMessage="Ninguna venta con saldo coincide"
                    data={(cartera.data?.items ?? []).map((f) => ({
                      value: String(f.negocio_id),
                      label: `${f.cliente} · ${f.servicio} · saldo ${formatearPesos(f.saldo)}`,
                    }))} />
                  <Button disabled={!venta} loading={conciliar.isPending}
                    onClick={() => conciliar.mutate({ negocio_id: Number(venta) })}>Crear y conciliar</Button>
                </Group>)}

              {editar && (
                <Group gap="xs">
                  <Button size="compact-sm" variant="default" onClick={() => setAccion('duplicado')}>
                    Es un duplicado</Button>
                  <Button size="compact-sm" variant="default" onClick={() => setAccion('reversado')}>
                    Se devolvió</Button>
                  <Button size="compact-sm" variant="default" onClick={() => setAccion('descartar')}>
                    No es de un cliente</Button>
                </Group>)}

              {accion && (
                <Stack gap="xs">
                  {accion === 'duplicado'
                    ? <NumberInput label="Número del movimiento bueno" description="El que sí cuenta; este queda como su repetido"
                        allowDecimal={false} min={1} value={original}
                        onChange={(v) => setOriginal(typeof v === 'bigint' ? Number(v) : v)} />
                    : <Textarea label={accion === 'reversado' ? 'Motivo de la devolución' : 'Por qué no es plata de un cliente'}
                        required minLength={3} value={texto} onChange={(e) => setTexto(e.currentTarget.value)} />}
                  <Group justify="flex-end">
                    <Button variant="default" onClick={() => setAccion(null)}>Cancelar</Button>
                    <Button color="red" disabled={!puedeEnviar} loading={marcar.isPending}
                      onClick={() => marcar.mutate()}>Confirmar</Button>
                  </Group>
                </Stack>)}
            </>)}

          {!pendiente && editar && (
            <Group justify="flex-end">
              <Button color="orange" variant="light" loading={deshacer.isPending}
                onClick={() => deshacer.mutate()}>Deshacer y devolver a la bandeja</Button>
            </Group>)}
        </Stack>)}
    </Modal>)
}
