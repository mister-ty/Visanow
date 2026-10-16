import {
  Alert, Badge, Button, Card, Center, Group, Loader, Modal, Select, SimpleGrid, Stack,
  Table, Tabs, Text, Textarea, Title, Tooltip,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconCashBanknote, IconInfoCircle } from '@tabler/icons-react'
import { useState } from 'react'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { BotonExportar } from '../componentes/BotonExportar'
import { useAsignables } from '../lib/catalogos'
import { mostrarError } from '../lib/errores'
import { formatearFecha, formatearPesos } from '../lib/formato'

type Comision = Esquemas['ComisionSalida']
type Liquidacion = Esquemas['LiquidacionSalida']

/**
 * Comisiones y cortes (RF-051, RF-052).
 *
 * El motor existía completo —calcula, congela la regla que aplicó, causa al
 * pago total, liquida y marca pagado— y no tenía una sola pantalla. Para quien
 * trabaja, eso es lo mismo que no existir: la comisión se seguía sacando en una
 * hoja aparte, que es exactamente lo que el sistema vino a reemplazar.
 *
 * Lo que esta pantalla tiene que contestar, en este orden:
 *
 *  1. ¿Cuánto le debo a cada una este mes? — la pestaña «Por liquidar».
 *  2. ¿Por qué esa cifra? — la columna «Por qué», que trae la regla congelada
 *     de cada comisión (RN-07). Sin eso, una vendedora que reclama obliga a
 *     reconstruir qué decía la tabla hace tres meses.
 *  3. ¿Este mes ya se pagó? — la pestaña «Cortes hechos», que es la que evita
 *     pagar dos veces.
 */

const COLOR_ESTADO: Record<string, string> = {
  pendiente: 'gray', causada: 'teal', liquidada: 'blue', anulada: 'red',
}

/** El primer día del mes, que es como el backend identifica un periodo. */
const primerDiaDelMes = (desplazamiento = 0): string => {
  const hoy = new Date()
  const d = new Date(hoy.getFullYear(), hoy.getMonth() + desplazamiento, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

const MESES = Array.from({ length: 13 }, (_, i) => {
  const valor = primerDiaDelMes(-i)
  const [anio, mes] = valor.split('-')
  const nombre = new Date(Number(anio), Number(mes) - 1, 1)
    .toLocaleDateString('es-CO', { month: 'long', year: 'numeric' })
  return { value: valor, label: nombre.charAt(0).toUpperCase() + nombre.slice(1) }
})

export function Comisiones() {
  const { puede } = useSesion()
  const asignables = useAsignables()
  const [vendedor, setVendedor] = useState<string | null>(null)
  const [periodo, setPeriodo] = useState<string>(primerDiaDelMes())

  const vendedores = (asignables.data ?? []).map((u) => ({
    value: String(u.id), label: u.nombre,
  }))

  return (
    <Stack>
      <Group justify="space-between">
        <div>
          <Title order={2}>Comisiones</Title>
          <Text size="sm" c="dimmed">
            Lo que se le debe a cada quien, y por qué esa cifra y no otra.
          </Text>
        </div>
        {/* El botón se oculta solo si el servidor no le da `comisiones` a este rol. */}
        <BotonExportar recurso="comisiones" etiqueta="Exportar comisiones" />
      </Group>

      <Card withBorder padding="sm">
        <Group grow align="end">
          <Select label="Vendedora" data={vendedores} clearable searchable
            placeholder="Todas"
            value={vendedor} onChange={(v) => setVendedor(v === null ? null : String(v))} />
          <Select label="Periodo" data={MESES} allowDeselect={false}
            value={periodo} onChange={(v) => v && setPeriodo(String(v))} />
        </Group>
      </Card>

      <Tabs defaultValue="liquidar">
        <Tabs.List>
          <Tabs.Tab value="liquidar">Por liquidar</Tabs.Tab>
          <Tabs.Tab value="todas">Todas las comisiones</Tabs.Tab>
          <Tabs.Tab value="cortes">Cortes hechos</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="liquidar" pt="md">
          <PorLiquidar vendedorId={vendedor} periodo={periodo}
            puedeLiquidar={puede('comisiones.editar')} />
        </Tabs.Panel>
        <Tabs.Panel value="todas" pt="md">
          <TodasLasComisiones vendedorId={vendedor} periodo={periodo} />
        </Tabs.Panel>
        <Tabs.Panel value="cortes" pt="md">
          <Cortes vendedorId={vendedor} periodo={periodo}
            puedeEditar={puede('comisiones.editar')} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}

/** Lo que entraría en el corte: causado, del periodo y sin liquidar. */
function PorLiquidar({ vendedorId, periodo, puedeLiquidar }: {
  vendedorId: string | null; periodo: string; puedeLiquidar: boolean
}) {
  const cq = useQueryClient()
  const [confirmando, setConfirmando] = useState(false)
  const [observaciones, setObservaciones] = useState('')

  const pendientes = useQuery({
    queryKey: ['comisiones', 'pendientes', vendedorId, periodo],
    queryFn: () => exigir(api.GET('/api/v1/comisiones/pendientes', {
      params: { query: { vendedor_id: Number(vendedorId), periodo } },
    })),
    enabled: vendedorId !== null,
    placeholderData: keepPreviousData,
  })

  const liquidar = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/liquidaciones', {
      body: { vendedor_id: Number(vendedorId), periodo,
              observaciones: observaciones.trim() || null },
    })),
    onSuccess: (liq) => {
      notifications.show({
        color: 'teal', title: 'Corte hecho',
        message: `${liq.cantidad} comisión(es) por ${formatearPesos(liq.total)}. `
                 + 'Esas comisiones ya no pueden entrar en otro corte.',
      })
      setConfirmando(false); setObservaciones('')
      cq.invalidateQueries({ queryKey: ['comisiones'] })
      cq.invalidateQueries({ queryKey: ['liquidaciones'] })
    },
    onError: (e) => mostrarError(e, 'No se pudo hacer el corte'),
  })

  if (vendedorId === null) {
    return (
      <Alert color="blue" variant="light" icon={<IconInfoCircle size={18} />}>
        Elija una vendedora arriba para ver qué se le debe este periodo. Un corte
        es por persona y por mes.
      </Alert>
    )
  }
  if (pendientes.isPending) return <Center h={140}><Loader color="teal" /></Center>

  const filas = pendientes.data ?? []
  const total = filas.reduce((t, c) => t + c.monto, 0)

  return (
    <Stack>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Tarjeta titulo="Comisiones por liquidar" valor={String(filas.length)} />
        <Tarjeta titulo="Total del periodo" valor={formatearPesos(total)} color="teal" />
        <Card withBorder padding="sm">
          <Button fullWidth leftSection={<IconCashBanknote size={16} />}
            disabled={!puedeLiquidar || filas.length === 0}
            onClick={() => setConfirmando(true)}>
            Hacer el corte
          </Button>
        </Card>
      </SimpleGrid>

      <TablaComisiones comisiones={filas}
        vacio="No hay comisiones causadas sin liquidar en este periodo. Una comisión
               se causa cuando el cliente termina de pagar la venta." />

      <Modal opened={confirmando} onClose={() => setConfirmando(false)} title="Hacer el corte">
        <Stack>
          <Text size="sm">
            Entran <b>{filas.length}</b> comisión(es) por <b>{formatearPesos(total)}</b>.
          </Text>
          <Alert color="orange" variant="light">
            Las comisiones que entran quedan bloqueadas y no pueden volver a entrar
            en otro corte. Es el registro de que esa plata se va a pagar, no un reporte.
          </Alert>
          <Textarea label="Observaciones" autosize minRows={2}
            placeholder="Por ejemplo: «se paga con la nómina del 30»"
            value={observaciones} onChange={(e) => setObservaciones(e.currentTarget.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirmando(false)}>Cancelar</Button>
            <Button loading={liquidar.isPending} onClick={() => liquidar.mutate()}>
              Confirmar el corte
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}

function TodasLasComisiones({ vendedorId, periodo }: {
  vendedorId: string | null; periodo: string
}) {
  const comisiones = useQuery({
    queryKey: ['comisiones', 'todas', vendedorId, periodo],
    queryFn: () => exigir(api.GET('/api/v1/comisiones', {
      params: { query: {
        ...(vendedorId ? { vendedor_id: Number(vendedorId) } : {}),
        periodo,
      } },
    })),
    placeholderData: keepPreviousData,
  })
  if (comisiones.isPending) return <Center h={140}><Loader color="teal" /></Center>
  return (
    <TablaComisiones comisiones={comisiones.data ?? []} conEstado
      vacio="No hay comisiones en este periodo." />
  )
}

/** Los cortes ya hechos: la pestaña que evita pagar dos veces el mismo mes. */
function Cortes({ vendedorId, periodo, puedeEditar }: {
  vendedorId: string | null; periodo: string; puedeEditar: boolean
}) {
  const cq = useQueryClient()
  const [anulando, setAnulando] = useState<Liquidacion | null>(null)
  const [motivo, setMotivo] = useState('')

  const cortes = useQuery({
    queryKey: ['liquidaciones', vendedorId, periodo],
    queryFn: () => exigir(api.GET('/api/v1/liquidaciones', {
      params: { query: {
        ...(vendedorId ? { vendedor_id: Number(vendedorId) } : {}),
        periodo,
      } },
    })),
    placeholderData: keepPreviousData,
  })

  const refrescar = () => {
    cq.invalidateQueries({ queryKey: ['liquidaciones'] })
    cq.invalidateQueries({ queryKey: ['comisiones'] })
  }

  const pagar = useMutation({
    mutationFn: (id: number) => exigir(api.POST('/api/v1/liquidaciones/{liquidacion_id}/pagada', {
      params: { path: { liquidacion_id: id } },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Corte marcado como pagado' })
      refrescar()
    },
    onError: (e) => mostrarError(e, 'No se pudo marcar como pagado'),
  })

  const anular = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/liquidaciones/{liquidacion_id}/anular', {
      params: { path: { liquidacion_id: anulando!.id } },
      body: { motivo: motivo.trim() },
    })),
    onSuccess: () => {
      notifications.show({
        color: 'teal', message: 'Corte anulado: sus comisiones vuelven a quedar por liquidar',
      })
      setAnulando(null); setMotivo(''); refrescar()
    },
    onError: (e) => mostrarError(e, 'No se pudo anular el corte'),
  })

  if (cortes.isPending) return <Center h={140}><Loader color="teal" /></Center>
  const filas = cortes.data ?? []

  return (
    <Stack>
      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={820}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Vendedora</Table.Th><Table.Th>Periodo</Table.Th>
                <Table.Th>Comisiones</Table.Th><Table.Th>Total</Table.Th>
                <Table.Th>Estado</Table.Th><Table.Th>Pagado</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {filas.map((l) => (
                <Table.Tr key={l.id}>
                  <Table.Td>{l.vendedor ?? '—'}</Table.Td>
                  <Table.Td>{formatearFecha(l.periodo)}</Table.Td>
                  <Table.Td>{l.cantidad}</Table.Td>
                  <Table.Td fw={600}>{formatearPesos(l.total)}</Table.Td>
                  <Table.Td>
                    <Badge variant="light"
                      color={l.estado === 'pagada' ? 'teal' : l.estado === 'anulada' ? 'red' : 'blue'}>
                      {l.estado}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{l.pagada_en ? formatearFecha(l.pagada_en) : '—'}</Table.Td>
                  <Table.Td>
                    {puedeEditar && l.estado === 'abierta' && (
                      <Group gap={4} justify="flex-end" wrap="nowrap">
                        <Button size="compact-sm" variant="default"
                          loading={pagar.isPending}
                          onClick={() => pagar.mutate(l.id)}>Marcar pagado</Button>
                        <Button size="compact-sm" variant="subtle" color="red"
                          onClick={() => setAnulando(l)}>Anular</Button>
                      </Group>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
              {filas.length === 0 && (
                <Table.Tr><Table.Td colSpan={7}>
                  <Text size="sm" c="dimmed" ta="center" py="lg">
                    No hay cortes en este periodo. Mientras no haya uno, lo que
                    aparece en «Por liquidar» está sin pagar.
                  </Text>
                </Table.Td></Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Text size="sm" c="dimmed">{filas.length} corte(s)</Text>

      <Modal opened={anulando !== null} onClose={() => setAnulando(null)} title="Anular el corte">
        <Stack>
          <Text size="sm">
            Las {anulando?.cantidad} comisión(es) de este corte vuelven a quedar por
            liquidar. El corte no se borra: queda anulado y con el motivo.
          </Text>
          <Textarea label="Motivo" autosize minRows={2} data-autofocus
            value={motivo} onChange={(e) => setMotivo(e.currentTarget.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setAnulando(null)}>Cancelar</Button>
            <Button color="red" loading={anular.isPending} disabled={!motivo.trim()}
              onClick={() => anular.mutate()}>Anular</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}

function TablaComisiones({ comisiones, vacio, conEstado = false }: {
  comisiones: Comision[]; vacio: string; conEstado?: boolean
}) {
  return (
    <Card withBorder padding={0}>
      <Table.ScrollContainer minWidth={900}>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Venta</Table.Th><Table.Th>Vendedora</Table.Th>
              <Table.Th>Base</Table.Th><Table.Th>%</Table.Th>
              <Table.Th>Comisión</Table.Th>
              {conEstado && <Table.Th>Estado</Table.Th>}
              <Table.Th>Por qué</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {comisiones.map((c) => (
              <Table.Tr key={c.id}>
                <Table.Td>#{c.negocio_id}</Table.Td>
                <Table.Td>{c.vendedor ?? '—'}</Table.Td>
                <Table.Td>{formatearPesos(c.base_calculo)}</Table.Td>
                <Table.Td>
                  {c.porcentaje_aplicado !== null && c.porcentaje_aplicado !== undefined
                    ? `${c.porcentaje_aplicado}%` : '—'}
                  {c.escalon === 'meta' && (
                    <Badge ml={6} size="xs" variant="light" color="teal">meta</Badge>)}
                </Table.Td>
                <Table.Td fw={600}>{formatearPesos(c.monto)}</Table.Td>
                {conEstado && (
                  <Table.Td>
                    <Badge variant="light" color={COLOR_ESTADO[c.estado] ?? 'gray'}>
                      {c.estado}
                    </Badge>
                  </Table.Td>
                )}
                <Table.Td>
                  {/* La regla queda congelada en cada comisión (RN-07): por eso
                      el cálculo se puede explicar meses después sin reconstruir
                      qué decía la tabla ese día. */}
                  {c.explicacion ? (
                    <Tooltip label={c.explicacion} multiline w={320} withArrow>
                      <Text size="xs" c="dimmed" lineClamp={2}>{c.explicacion}</Text>
                    </Tooltip>
                  ) : <Text size="xs" c="dimmed">—</Text>}
                </Table.Td>
              </Table.Tr>
            ))}
            {comisiones.length === 0 && (
              <Table.Tr><Table.Td colSpan={conEstado ? 7 : 6}>
                <Text size="sm" c="dimmed" ta="center" py="lg">{vacio}</Text>
              </Table.Td></Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  )
}

const Tarjeta = ({ titulo, valor, color }: {
  titulo: string; valor: string; color?: string
}) => (
  <Card withBorder padding="sm">
    <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{titulo}</Text>
    <Text size="lg" fw={700} c={color}>{valor}</Text>
  </Card>
)
