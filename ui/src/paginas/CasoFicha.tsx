import {
  Alert, Badge, Button, Card, Center, Checkbox, Grid, Group, Loader, Modal, Select, Stack, Table,
  Text, TextInput, Textarea, Timeline, Title,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  IconAlertTriangle, IconArrowRight, IconCalendarPlus, IconCloudDownload, IconHistory,
} from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { mostrarError } from '../lib/errores'
import { aSelect, porPais, useAsignables, useCatalogos } from '../lib/catalogos'
import { formatearFechaHora } from '../lib/formato'

type Detalle = Esquemas['CasoDetalle']

const TIPOS_CITA = [
  { value: 'cas', label: 'CAS (huellas y foto)' }, { value: 'biometria', label: 'Biometría' },
  { value: 'entrevista', label: 'Entrevista' }, { value: 'radicacion', label: 'Radicación' },
  { value: 'preparacion', label: 'Preparación' }, { value: 'entrega', label: 'Entrega' },
  { value: 'otra', label: 'Otra' },
]
const RESULTADOS = [
  { value: 'aprobada', label: 'Aprobada' }, { value: 'negada', label: 'Negada' },
  { value: 'proceso_administrativo', label: 'Proceso administrativo' },
  { value: 'cancelado', label: 'Cancelado' }, { value: 'no_continuo', label: 'No continuó' },
]

export function CasoFicha() {
  const { id } = useParams()
  const casoId = Number(id)
  const { puede } = useSesion()
  const clienteQuery = useQueryClient()
  const [moviendo, setMoviendo] = useState(false)
  const [agendando, setAgendando] = useState(false)
  const [registrando, setRegistrando] = useState(false)

  const ficha = useQuery({
    queryKey: ['caso', casoId],
    queryFn: () => exigir(api.GET('/api/v1/casos/{caso_id}', { params: { path: { caso_id: casoId } } })),
  })
  const historial = useQuery({
    queryKey: ['caso', casoId, 'historial'],
    queryFn: () => exigir(api.GET('/api/v1/casos/{caso_id}/historial',
      { params: { path: { caso_id: casoId } } })),
    enabled: ficha.isSuccess,
  })
  const catalogos = useCatalogos()
  const asignables = useAsignables()
  const refrescar = () => {
    clienteQuery.invalidateQueries({ queryKey: ['caso', casoId] })
    clienteQuery.invalidateQueries({ queryKey: ['casos'] })
    clienteQuery.invalidateQueries({ queryKey: ['casos-resumen'] })
  }

  const editar = useMutation({
    mutationFn: (cambios: Esquemas['CasoEditar']) => exigir(api.PATCH('/api/v1/casos/{caso_id}', {
      params: { path: { caso_id: casoId } }, body: cambios,
    })),
    onSuccess: () => refrescar(),
    onError: (e) => mostrarError(e),
  })

  const marcar = useMutation({
    mutationFn: ({ item, cumplido }: { item: number; cumplido: boolean }) =>
      exigir(api.POST('/api/v1/casos/{caso_id}/checklist/{item_id}', {
        params: { path: { caso_id: casoId, item_id: item } }, body: { cumplido },
      })),
    onSuccess: () => refrescar(),
    onError: (e) => mostrarError(e),
  })

  if (ficha.isPending) return <Center h={200}><Loader color="teal" /></Center>
  if (ficha.isError) return <Alert color="red">No se pudo abrir el trámite.</Alert>
  const c = ficha.data
  const puedeEditar = puede('casos.editar')
  const obligatoriosPendientes = c.checklist.filter((i) => i.obligatorio && !i.cumplido).length

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <div>
          <Group gap="xs">
            <Title order={2}>{c.solicitante}</Title>
            <Badge size="lg" variant="light" color={c.es_final ? 'gray' : 'teal'}>{c.estado_nombre}</Badge>
            {c.fuente !== 'manual' && (
              <Badge variant="light" leftSection={<IconCloudDownload size={12} />}>
                SaaS {c.id_externo}
              </Badge>)}
            {c.riesgo === 'alto' && (
              <Badge color="red" variant="light" leftSection={<IconAlertTriangle size={12} />}>
                {c.dias_sin_movimiento} días sin movimiento
              </Badge>)}
          </Group>
          <Text size="sm" c="dimmed">
            Creado el {formatearFechaHora(c.creado_en)}
            {c.sin_venta && ' · sin venta registrada'}
          </Text>
        </div>
        {puedeEditar && !c.es_final && (
          <Group>
            <Button variant="default" onClick={() => setRegistrando(true)}>Registrar resultado</Button>
            <Button rightSection={<IconArrowRight size={16} />} onClick={() => setMoviendo(true)}>Mover</Button>
          </Group>)}
      </Group>

      {c.resultado && (
        <Alert color={c.resultado === 'aprobada' ? 'teal' : c.resultado === 'negada' ? 'red' : 'yellow'}
          variant="light" title={`Resultado: ${RESULTADOS.find((r) => r.value === c.resultado)?.label}`}>
          {c.resultado_fecha} {c.resultado_nota && `· ${c.resultado_nota}`}
          {!c.es_final && ' — el trámite sigue abierto: falta cerrar el servicio.'}
        </Alert>)}

      <Grid>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Stack>
            <Card withBorder padding="lg">
              <Text fw={600} mb="sm">Datos del trámite</Text>
              <Grid gap="xs">
                <Grid.Col span={6}>
                  <Select label="País" size="xs" disabled={!puedeEditar}
                    value={c.pais_id ? String(c.pais_id) : null} data={aSelect(catalogos.data?.paises)}
                    onChange={(v) => v && editar.mutate({ pais_id: Number(v) })} searchable
                    allowDeselect={false} />
                </Grid.Col>
                <Grid.Col span={6}>
                  <Select label="Tipo de visa" size="xs" disabled={!puedeEditar}
                    value={c.tipo_visa_id ? String(c.tipo_visa_id) : null}
                    data={aSelect(porPais(catalogos.data?.tipos_visa, c.pais_id))}
                    onChange={(v) => editar.mutate({ tipo_visa_id: v ? Number(v) : null })} clearable />
                </Grid.Col>
                <Grid.Col span={6}>
                  <Select label="Sede de la cita" size="xs" disabled={!puedeEditar}
                    value={c.sede_id ? String(c.sede_id) : null}
                    data={aSelect(catalogos.data?.sedes)}
                    onChange={(v) => editar.mutate({ sede_id: v ? Number(v) : null })} clearable searchable />
                </Grid.Col>
                <Grid.Col span={6}>
                  <Select label="Responsable" size="xs" disabled={!puedeEditar}
                    value={c.responsable_id ? String(c.responsable_id) : null}
                    data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))}
                    onChange={(v) => editar.mutate({ responsable_id: v ? Number(v) : null })}
                    placeholder="sin asignar" clearable />
                </Grid.Col>
                <Grid.Col span={12}>
                  <ProximaAccion caso={c} editable={puedeEditar}
                    guardar={(texto) => editar.mutate({ proxima_accion: texto })} />
                </Grid.Col>
              </Grid>
            </Card>

            <Card withBorder padding="lg">
              <Group justify="space-between" mb="sm">
                <Text fw={600}>Documentos</Text>
                <Badge variant="light" color={obligatoriosPendientes ? 'yellow' : 'teal'}>
                  {obligatoriosPendientes ? `${obligatoriosPendientes} obligatorio(s) pendiente(s)` : 'completo'}
                </Badge>
              </Group>
              <Stack gap={6}>
                {c.checklist.map((i) => (
                  <Checkbox key={i.item_id} checked={i.cumplido} disabled={!puedeEditar || marcar.isPending}
                    onChange={(e) => marcar.mutate({ item: i.item_id, cumplido: e.currentTarget.checked })}
                    label={<Group gap={6}><Text size="sm">{i.nombre}</Text>
                      {i.obligatorio && <Badge size="xs" variant="outline" color="gray">obligatorio</Badge>}
                    </Group>} />
                ))}
                {c.checklist.length === 0 && (
                  <Text size="sm" c="dimmed">No hay checklist definido para este país y tipo de visa.</Text>)}
              </Stack>
            </Card>

            <Card withBorder padding="lg">
              <Group justify="space-between" mb="sm">
                <Text fw={600}>Citas</Text>
                {puedeEditar && (
                  <Button size="compact-sm" variant="light" leftSection={<IconCalendarPlus size={14} />}
                    onClick={() => setAgendando(true)}>Agendar</Button>)}
              </Group>
              {c.citas.length === 0
                ? <Text size="sm" c="dimmed">Sin citas agendadas.</Text>
                : (
                  <Table verticalSpacing={6}>
                    <Table.Tbody>
                      {c.citas.map((cita) => (
                        <Table.Tr key={cita.id}>
                          <Table.Td><Text size="sm" tt="capitalize">{cita.tipo}</Text></Table.Td>
                          <Table.Td><Text size="sm">{formatearFechaHora(cita.inicia_en)}</Text></Table.Td>
                          <Table.Td><Badge size="sm" variant="light">{cita.estado}</Badge></Table.Td>
                        </Table.Tr>))}
                    </Table.Tbody>
                  </Table>)}
            </Card>
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 5 }}>
          <Card withBorder padding="lg">
            <Group gap="xs" mb="sm"><IconHistory size={18} /><Text fw={600}>Historial</Text></Group>
            <Timeline bulletSize={14} lineWidth={2}>
              {historial.data?.map((h, i) => (
                <Timeline.Item key={i} title={<Text size="sm">{titulo(h)}</Text>}>
                  <Text size="xs" c="dimmed">
                    {formatearFechaHora(h.ocurrido_en)}{h.usuario && ` · ${h.usuario}`}
                  </Text>
                  {h.observacion && <Text size="xs" mt={2}>{h.observacion}</Text>}
                </Timeline.Item>))}
            </Timeline>
          </Card>
        </Grid.Col>
      </Grid>

      <ModalMover caso={c} abierto={moviendo} cerrar={() => setMoviendo(false)} hecho={refrescar} />
      <ModalCita casoId={casoId} abierto={agendando} cerrar={() => setAgendando(false)} hecho={refrescar} />
      <ModalResultado casoId={casoId} abierto={registrando} cerrar={() => setRegistrando(false)} hecho={refrescar} />
    </Stack>
  )
}

function titulo(h: Esquemas['HistorialSalida']): string {
  if (h.campo === 'creado') return 'Trámite creado'
  if (h.campo === 'estado') return `Estado: ${h.valor_anterior} → ${h.valor_nuevo}`
  if (h.campo === 'excepcion') return `Excepción: ${h.valor_anterior} → ${h.valor_nuevo}`
  if (h.campo.startsWith('checklist:')) return `Documento ${h.campo.split(':')[1]}: ${h.valor_nuevo}`
  if (h.campo.startsWith('cita_')) return `Cita ${h.campo.replace('cita_', '').replace('_', ' ')}`
  return `${h.campo}: ${h.valor_anterior ?? '—'} → ${h.valor_nuevo ?? '—'}`
}

function ProximaAccion({ caso, editable, guardar }: {
  caso: Detalle; editable: boolean; guardar: (t: string) => void
}) {
  const [texto, setTexto] = useState(caso.proxima_accion ?? '')
  return (
    <Group align="flex-end" gap="xs">
      <TextInput flex={1} size="xs" label="Próxima acción" disabled={!editable} value={texto}
        description="Todo trámite abierto tiene que tener claro cuál es el siguiente paso"
        onChange={(e) => setTexto(e.currentTarget.value)} />
      {editable && texto !== (caso.proxima_accion ?? '') && (
        <Button size="compact-sm" onClick={() => guardar(texto)}>Guardar</Button>)}
    </Group>)
}

function ModalMover({ caso, abierto, cerrar, hecho }: {
  caso: Detalle; abierto: boolean; cerrar: () => void; hecho: () => void
}) {
  const { puede } = useSesion()
  const [destino, setDestino] = useState<string | null>(null)
  const [motivo, setMotivo] = useState('')
  const [forzar, setForzar] = useState(false)
  const catalogos = useCatalogos()

  // Cada vez que se abre se empieza de cero: si un intento anterior falló (por
  // ejemplo, faltaba la cita), no debe quedar el estado ya elegido.
  useEffect(() => {
    if (abierto) { setDestino(null); setMotivo(''); setForzar(false) }
  }, [abierto])

  const mover = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/casos/{caso_id}/estado', {
      params: { path: { caso_id: caso.id } },
      body: { codigo_destino: destino!, motivo: motivo || null, forzar },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Trámite movido' })
      setDestino(null); setMotivo(''); setForzar(false); hecho(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo mover'),
  })

  const opciones = forzar
    ? (catalogos.data?.estados_operativos ?? [])
        .filter((e) => e.nombre !== caso.estado_nombre && e.codigo)
        .map((e) => ({ value: e.codigo!, label: e.nombre }))
    : caso.estados_posibles.map((e) => ({ value: e.codigo, label: e.nombre }))

  return (
    <Modal opened={abierto} onClose={cerrar} title={`Mover «${caso.estado_nombre}» a…`}>
      <Stack>
        <Select label="Nuevo estado" data={opciones} value={destino} allowDeselect={false}
          onChange={(v) => setDestino(v as string | null)} data-autofocus
          description={forzar ? 'Cualquier estado' : 'Solo los estados a los que se puede pasar desde aquí'} />
        <Textarea label="Motivo" value={motivo} onChange={(e) => setMotivo(e.currentTarget.value)}
          description="Obligatorio para cancelar, suspender o saltarse el orden" autosize minRows={2} />
        {puede('casos.excepcion') && (
          <Checkbox color="red" checked={forzar} onChange={(e) => setForzar(e.currentTarget.checked)}
            label="Saltarse el orden del proceso (queda como excepción en el historial)" />)}
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={mover.isPending} disabled={!destino} onClick={() => mover.mutate()}>Mover</Button>
        </Group>
      </Stack>
    </Modal>)
}

function ModalCita({ casoId, abierto, cerrar, hecho }: {
  casoId: number; abierto: boolean; cerrar: () => void; hecho: () => void
}) {
  const catalogos = useCatalogos()
  const formulario = useForm({
    initialValues: { tipo: 'entrevista', fecha: '', hora: '08:00', sede_id: '', observaciones: '' },
    validate: { fecha: (v) => (v ? null : 'Elija la fecha') },
  })
  const agendar = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.POST('/api/v1/casos/{caso_id}/citas', {
      params: { path: { caso_id: casoId } },
      body: { tipo: v.tipo as 'entrevista', inicia_en: `${v.fecha}T${v.hora}:00-05:00`,
              zona_horaria: 'America/Bogota',
              sede_id: v.sede_id ? Number(v.sede_id) : undefined,
              observaciones: v.observaciones || undefined },
    })),
    onSuccess: () => { formulario.reset(); hecho(); cerrar() },
    onError: (e) => mostrarError(e, 'No se pudo agendar'),
  })
  return (
    <Modal opened={abierto} onClose={cerrar} title="Agendar cita">
      <form onSubmit={formulario.onSubmit((v) => agendar.mutate(v))}>
        <Stack>
          <Select label="Tipo" data={TIPOS_CITA} {...formulario.getInputProps('tipo')} allowDeselect={false} />
          <Group grow>
            <TextInput label="Fecha" type="date" {...formulario.getInputProps('fecha')} />
            <TextInput label="Hora" type="time" {...formulario.getInputProps('hora')} />
          </Group>
          <Select label="Sede" data={aSelect(catalogos.data?.sedes)} searchable clearable
            {...formulario.getInputProps('sede_id')} />
          <TextInput label="Observaciones" {...formulario.getInputProps('observaciones')} />
          <Text size="xs" c="dimmed">La hora se guarda con su zona horaria (Bogotá) y se muestra en la del usuario.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={agendar.isPending}>Agendar</Button>
          </Group>
        </Stack>
      </form>
    </Modal>)
}

function ModalResultado({ casoId, abierto, cerrar, hecho }: {
  casoId: number; abierto: boolean; cerrar: () => void; hecho: () => void
}) {
  const formulario = useForm({ initialValues: { resultado: '', fecha: '', nota: '' } })
  const registrar = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.POST('/api/v1/casos/{caso_id}/resultado', {
      params: { path: { caso_id: casoId } },
      body: { resultado: v.resultado as 'aprobada', fecha: v.fecha || null, nota: v.nota || null },
    })),
    onSuccess: () => { formulario.reset(); hecho(); cerrar() },
    onError: (e) => mostrarError(e),
  })
  return (
    <Modal opened={abierto} onClose={cerrar} title="Registrar resultado">
      <form onSubmit={formulario.onSubmit((v) => registrar.mutate(v))}>
        <Stack>
          <Select label="Resultado" data={RESULTADOS} data-autofocus allowDeselect={false}
            {...formulario.getInputProps('resultado')} />
          <TextInput label="Fecha" type="date" {...formulario.getInputProps('fecha')} />
          <Textarea label="Nota" autosize minRows={2} {...formulario.getInputProps('nota')} />
          <Alert color="gray" variant="light">
            El resultado del consulado y el cierre del servicio son cosas distintas: una visa negada puede
            quedar finalizada cuando se entregue el pasaporte.
          </Alert>
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={registrar.isPending}
              disabled={!formulario.values.resultado}>Registrar</Button>
          </Group>
        </Stack>
      </form>
    </Modal>)
}
