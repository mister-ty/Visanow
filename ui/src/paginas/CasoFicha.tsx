import {
  ActionIcon, Alert, Badge, Button, Card, Center, Checkbox, Grid, Group, Loader, Modal, Select,
  Stack, Table, Text, TextInput, Textarea, Timeline, Title, Tooltip,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  IconAlertTriangle, IconArrowRight, IconCalendarPlus, IconCheck, IconCloudDownload, IconHistory,
  IconNote, IconPencil, IconX,
} from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { Documentos } from '../componentes/Documentos'
import { ModalMensaje } from '../componentes/ModalMensaje'
import { useParams } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { codigoDe, mostrarError } from '../lib/errores'
import { aSelect, porPais, useAsignables, useCatalogos } from '../lib/catalogos'
import { formatearFechaHora } from '../lib/formato'

type Detalle = Esquemas['CasoDetalle']
type Documento = Esquemas['ItemChecklist']

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
  const [escribiendo, setEscribiendo] = useState(false)
  const [registrando, setRegistrando] = useState(false)
  const [reprogramando, setReprogramando] = useState<Esquemas['CitaSalida'] | null>(null)
  const [anotando, setAnotando] = useState<Documento | null>(null)
  const [motivoCambio, setMotivoCambio] = useState('')

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
    mutationFn: (cambios: Esquemas['CasoEdicion']) => exigir(api.PATCH('/api/v1/casos/{caso_id}', {
      params: { path: { caso_id: casoId } }, body: cambios,
    })),
    onSuccess: () => { setMotivoCambio(''); refrescar() },
    onError: (e) => mostrarError(e),
  })

  /** Guarda el dato con el motivo que haya escrito, y lo vacía: el motivo es el
   *  por qué de ESE cambio y así queda en su línea del historial (RF-028). */
  const cambiar = (cambios: Esquemas['CasoEditar']) =>
    editar.mutate({ ...cambios, motivo: motivoCambio.trim() || null })

  const cambiarCita = useMutation({
    mutationFn: ({ id, cambios }: { id: number; cambios: Esquemas['CitaEditar'] }) =>
      exigir(api.PATCH('/api/v1/citas/{cita_id}', {
        params: { path: { cita_id: id } }, body: cambios,
      })),
    onSuccess: () => { notifications.show({ color: 'teal', message: 'Cita actualizada' }); refrescar() },
    onError: (e) => mostrarError(e, 'No se pudo actualizar la cita'),
  })

  // La observación solo viaja cuando se está escribiendo: si fuera siempre,
  // marcar la casilla borraría la nota que alguien dejó ayer.
  const marcar = useMutation({
    mutationFn: ({ item, cumplido, observacion }:
      { item: number; cumplido: boolean; observacion?: string }) =>
      exigir(api.POST('/api/v1/casos/{caso_id}/checklist/{item_id}', {
        params: { path: { caso_id: casoId, item_id: item } }, body: { cumplido, observacion },
      })),
    onSuccess: () => { setAnotando(null); refrescar() },
    onError: (e) => mostrarError(e),
  })

  if (ficha.isPending) return <Center h={200}><Loader color="teal" /></Center>
  if (ficha.isError) return <Alert color="red">No se pudo abrir el trámite.</Alert>
  const c = ficha.data
  const puedeEditar = puede('casos.editar')
  const obligatoriosPendientes = c.checklist.filter((i) => i.obligatorio && !i.cumplido).length
  // Un estado final no se mueve, salvo que de él salga alguna transición. La
  // excepción (cancelado / no continuó / suspendido) es final y aun así se
  // retoma: el cliente que aplazó en marzo vuelve en agosto, y esconder
  // «Mover» ahí dejaba el trámite enterrado para siempre (RF-023).
  const puedeMover = !c.es_final || c.estados_posibles.length > 0

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
        <Group>
          <Button variant="default" onClick={() => setEscribiendo(true)}>Mensaje al cliente</Button>
          {/* El resultado se registra también en un trámite ya cerrado:
              «cancelado» y «no continuó» son dos de los cinco resultados y son
              los de un trámite que terminó en excepción (RF-027, RN-06). */}
          {puedeEditar && (
            <>
              <Button variant="default" onClick={() => setRegistrando(true)}>Registrar resultado</Button>
              {puedeMover && (
                <Button rightSection={<IconArrowRight size={16} />}
                  onClick={() => setMoviendo(true)}>Mover</Button>)}
            </>)}
        </Group>
      </Group>
      {escribiendo && <ModalMensaje casoId={casoId} cerrar={() => setEscribiendo(false)} />}

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
                    onChange={(v) => v && cambiar({ pais_id: Number(v) })} searchable
                    allowDeselect={false} />
                </Grid.Col>
                <Grid.Col span={6}>
                  <Select label="Tipo de visa" size="xs" disabled={!puedeEditar}
                    value={c.tipo_visa_id ? String(c.tipo_visa_id) : null}
                    data={aSelect(porPais(catalogos.data?.tipos_visa, c.pais_id))}
                    onChange={(v) => cambiar({ tipo_visa_id: v ? Number(v) : null })} clearable />
                </Grid.Col>
                <Grid.Col span={6}>
                  <Select label="Modalidad" size="xs" disabled={!puedeEditar}
                    description="Decide qué checklist de documentos se aplica"
                    value={c.modalidad_id ? String(c.modalidad_id) : null}
                    data={aSelect(catalogos.data?.modalidades)}
                    onChange={(v) => cambiar({ modalidad_id: v ? Number(v) : null })} clearable />
                </Grid.Col>
                <Grid.Col span={6}>
                  <Select label="Sede de la cita" size="xs" disabled={!puedeEditar}
                    value={c.sede_id ? String(c.sede_id) : null}
                    data={aSelect(catalogos.data?.sedes)}
                    onChange={(v) => cambiar({ sede_id: v ? Number(v) : null })} clearable searchable />
                </Grid.Col>
                <Grid.Col span={6}>
                  <Select label="Responsable" size="xs" disabled={!puedeEditar}
                    value={c.responsable_id ? String(c.responsable_id) : null}
                    data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))}
                    onChange={(v) => cambiar({ responsable_id: v ? Number(v) : null })}
                    placeholder="sin asignar" clearable />
                </Grid.Col>
                <Grid.Col span={6}>
                  <Colaboradores casoId={c.id} responsableId={c.responsable_id}
                    editable={puedeEditar} />
                </Grid.Col>
                <Grid.Col span={12}>
                  <ProximaAccion caso={c} editable={puedeEditar}
                    guardar={(texto) => cambiar({ proxima_accion: texto })} />
                </Grid.Col>
                {puedeEditar && (
                  <Grid.Col span={12}>
                    {/* El por qué del cambio. Se manda con el siguiente dato que
                        se cambie y queda en su línea del historial: «por qué le
                        cambiaron el responsable a este trámite» (RF-028). */}
                    <TextInput size="xs" label="Por qué se cambia" value={motivoCambio}
                      description="Opcional. Queda en el historial junto al dato que cambie"
                      placeholder="La asesora salió a vacaciones, el cliente cambió de consulado…"
                      onChange={(e) => setMotivoCambio(e.currentTarget.value)} />
                  </Grid.Col>)}
              </Grid>
            </Card>

            <Card withBorder padding="lg">
              <Group justify="space-between" mb="sm">
                <Text fw={600}>Documentos requeridos</Text>
                <Badge variant="light" color={obligatoriosPendientes ? 'yellow' : 'teal'}>
                  {obligatoriosPendientes ? `${obligatoriosPendientes} obligatorio(s) pendiente(s)` : 'completo'}
                </Badge>
              </Group>
              <Stack gap={6}>
                {c.checklist.map((i) => (
                  <Group key={i.item_id} gap={6} align="flex-start" wrap="nowrap">
                    <Checkbox flex={1} checked={i.cumplido} disabled={!puedeEditar || marcar.isPending}
                      onChange={(e) => marcar.mutate({ item: i.item_id, cumplido: e.currentTarget.checked })}
                      label={<Group gap={6}><Text size="sm">{i.nombre}</Text>
                        {i.obligatorio && <Badge size="xs" variant="outline" color="gray">obligatorio</Badge>}
                      </Group>}
                      description={<ComoQuedo documento={i} />} />
                    {puedeEditar && (
                      <Tooltip label={i.observacion ? 'Cambiar la nota' : 'Dejar una nota'}>
                        <ActionIcon size="sm" variant="subtle" color={i.observacion ? 'teal' : 'gray'}
                          aria-label={`Nota de ${i.nombre}`} onClick={() => setAnotando(i)}>
                          <IconNote size={14} />
                        </ActionIcon>
                      </Tooltip>)}
                  </Group>
                ))}
                {c.checklist.length === 0 && (
                  <Text size="sm" c="dimmed">
                    No hay checklist definido para este país, tipo de visa y modalidad.
                  </Text>)}
              </Stack>
            </Card>

            <Card withBorder padding="lg">
              <Text fw={600} mb="sm">Archivos adjuntos</Text>
              <Documentos entidad="caso" entidadId={c.id} puedeEditar={puedeEditar} />
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
                  <Table.ScrollContainer minWidth={600}>
                    <Table verticalSpacing={6}>
                      <Table.Tbody>
                        {c.citas.map((cita) => (
                          <FilaCita key={cita.id} cita={cita} editable={puedeEditar}
                            cambiar={(cambios) => cambiarCita.mutate({ id: cita.id, cambios })}
                            reprogramar={() => setReprogramando(cita)}
                            guardando={cambiarCita.isPending} />))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>)}
            </Card>
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 5 }}>
          <Card withBorder padding="lg">
            <Group gap="xs" mb="sm"><IconHistory size={18} /><Text fw={600}>Historial</Text></Group>
            <Timeline bulletSize={14} lineWidth={2}>
              {historial.data?.map((h, i) => (
                <Timeline.Item key={i} title={<Text size="sm">{h.titulo}</Text>}>
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
      <ModalReprogramar cita={reprogramando} cerrar={() => setReprogramando(null)} hecho={refrescar} />
      <ModalNota key={anotando?.item_id} documento={anotando} guardando={marcar.isPending}
        cerrar={() => setAnotando(null)}
        guardar={(texto) => anotando && marcar.mutate(
          { item: anotando.item_id, cumplido: anotando.cumplido, observacion: texto })} />
    </Stack>
  )
}

/** Quién dijo que el documento estaba, cuándo y con qué nota. El servicio lo
 *  guardaba desde el principio y solo se veía leyendo el historial completo. */
function ComoQuedo({ documento }: { documento: Documento }) {
  if (!documento.cumplido_por && !documento.observacion) return null
  return (
    <>
      {documento.cumplido_por && documento.cumplido_en && (
        <Text size="xs" c="dimmed" component="span" display="block">
          {documento.cumplido_por} · {formatearFechaHora(documento.cumplido_en)}
        </Text>)}
      {documento.observacion && (
        <Text size="xs" component="span" display="block">{documento.observacion}</Text>)}
    </>
  )
}

/** La nota de un documento: «el pasaporte vence en enero, alcanza», «la carta
 *  laboral llega el martes». Es lo que explica por qué el soporte está o no
 *  está, y se escribe aquí para no tener que contarlo en el chat (RF-025). */
function ModalNota({ documento, guardando, guardar, cerrar }: {
  documento: Documento | null
  guardando: boolean
  guardar: (texto: string) => void
  cerrar: () => void
}) {
  // Arranca con la nota que el documento ya tiene. Quien lo abre viene a
  // corregirla, no a escribirla de nuevo; el `key` del padre hace que al pasar
  // a otro documento este formulario vuelva a nacer con la nota de ese.
  const [texto, setTexto] = useState(documento?.observacion ?? '')
  return (
    <Modal opened={documento !== null} onClose={cerrar} title={documento?.nombre ?? ''}>
      <Stack>
        <Textarea label="Nota del documento" autosize minRows={2} value={texto} data-autofocus
          description="Qué falta, qué se revisó o hasta cuándo sirve. Queda en el historial."
          onChange={(e) => setTexto(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={guardando} onClick={() => guardar(texto)}>Guardar</Button>
        </Group>
      </Stack>
    </Modal>)
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

/** Lo que el backend puede pedir antes de dejar avanzar y que se puede llenar
 *  en el mismo paso. Hasta ahora el movimiento moría en una notificación: el
 *  usuario tenía que cerrar, ir a buscar la sede o el resultado en la ficha,
 *  llenarlo y volver a empezar, y por eso el campo `cambios` que el backend
 *  acepta justamente para esto no lo mandaba nadie (RF-023). */
const COMPLETABLES = ['faltan_campos', 'falta_responsable', 'falta_proxima_accion', 'falta_resultado']
const SIN_LLENAR = { sede_id: '', responsable_id: '', proxima_accion: '', resultado: '', resultado_fecha: '' }

function ModalMover({ caso, abierto, cerrar, hecho }: {
  caso: Detalle; abierto: boolean; cerrar: () => void; hecho: () => void
}) {
  const { puede } = useSesion()
  const [destino, setDestino] = useState<string | null>(null)
  const [motivo, setMotivo] = useState('')
  const [forzar, setForzar] = useState(false)
  const [falta, setFalta] = useState<string | null>(null)
  const [datos, setDatos] = useState(SIN_LLENAR)
  const catalogos = useCatalogos()
  const asignables = useAsignables()

  // Cada vez que se abre se empieza de cero: si un intento anterior falló (por
  // ejemplo, faltaba la cita), no debe quedar el estado ya elegido.
  useEffect(() => {
    if (abierto) { setDestino(null); setMotivo(''); setForzar(false); setFalta(null); setDatos(SIN_LLENAR) }
  }, [abierto])

  const mover = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/casos/{caso_id}/estado', {
      params: { path: { caso_id: caso.id } },
      body: {
        codigo_destino: destino!, motivo: motivo || null, forzar,
        cambios: {
          ...(datos.sede_id ? { sede_id: Number(datos.sede_id) } : {}),
          ...(datos.responsable_id ? { responsable_id: Number(datos.responsable_id) } : {}),
          ...(datos.proxima_accion ? { proxima_accion: datos.proxima_accion } : {}),
        },
        ...(datos.resultado
          ? { resultado: datos.resultado as 'aprobada', resultado_fecha: datos.resultado_fecha || null }
          : {}),
      },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Trámite movido' })
      setDestino(null); setMotivo(''); setForzar(false); hecho(); cerrar()
    },
    onError: (e) => {
      // Si lo que falta es un dato del trámite, se pide aquí mismo y se
      // reintenta sin perder el estado que ya se eligió.
      setFalta(COMPLETABLES.includes(codigoDe(e) ?? '') && e instanceof Error ? e.message : null)
      mostrarError(e, 'No se pudo mover')
    },
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
            label="Saltarse el orden del proceso y el checklist (queda como excepción auditada)" />)}
        {falta && (
          <Alert color="yellow" variant="light" title="Falta un dato para poder avanzar">
            <Stack gap="xs">
              <Text size="sm">{falta}</Text>
              <Select label="Sede de la cita" size="xs" searchable clearable
                data={aSelect(catalogos.data?.sedes)} value={datos.sede_id || null}
                onChange={(v) => setDatos({ ...datos, sede_id: v ?? '' })} />
              <Select label="Responsable" size="xs" clearable value={datos.responsable_id || null}
                data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))}
                onChange={(v) => setDatos({ ...datos, responsable_id: v ?? '' })} />
              <TextInput label="Próxima acción" size="xs" value={datos.proxima_accion}
                onChange={(e) => setDatos({ ...datos, proxima_accion: e.currentTarget.value })} />
              <Group grow>
                <Select label="Resultado" size="xs" clearable data={RESULTADOS}
                  value={datos.resultado || null}
                  onChange={(v) => setDatos({ ...datos, resultado: v ?? '' })} />
                <TextInput label="Fecha del resultado" size="xs" type="date"
                  value={datos.resultado_fecha}
                  onChange={(e) => setDatos({ ...datos, resultado_fecha: e.currentTarget.value })} />
              </Group>
              <Text size="xs" c="dimmed">
                Lo que llene aquí se guarda junto con el movimiento. Si lo que falta es la cita,
                agéndela primero en la ficha.
              </Text>
            </Stack>
          </Alert>)}
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


const COLOR_CITA: Record<string, string> = {
  pendiente: 'orange', programada: 'blue', confirmada: 'teal',
  reprogramada: 'yellow', realizada: 'gray', cancelada: 'red',
}

/** Una cita con lo que de verdad se le hace: confirmarla, moverla o cancelarla.
 *  Las acciones dependen de en qué va: una cita ya realizada no se confirma. */
function FilaCita({ cita, editable, cambiar, reprogramar, guardando }: {
  cita: Esquemas['CitaSalida']
  editable: boolean
  cambiar: (cambios: Esquemas['CitaEditar']) => void
  reprogramar: () => void
  guardando: boolean
}) {
  const viva = cita.estado !== 'cancelada' && cita.estado !== 'realizada'
  const sinHora = new Date(cita.inicia_en).getHours() === 0
  return (
    <Table.Tr>
      <Table.Td><Text size="sm" tt="capitalize">{cita.tipo}</Text></Table.Td>
      <Table.Td>
        <Text size="sm">{formatearFechaHora(cita.inicia_en)}</Text>
        {sinHora && <Text size="xs" c="orange">falta la hora</Text>}
      </Table.Td>
      <Table.Td>
        <Badge size="sm" variant="light" color={COLOR_CITA[cita.estado] ?? 'gray'}>{cita.estado}</Badge>
      </Table.Td>
      <Table.Td>
        {editable && viva && (
          <Group gap={4} justify="flex-end" wrap="nowrap">
            {cita.estado !== 'confirmada' && (
              <Tooltip label="El consulado confirmó la cita">
                <ActionIcon size="sm" variant="subtle" color="teal" loading={guardando}
                  aria-label="Confirmar cita" onClick={() => cambiar({ estado: 'confirmada' })}>
                  <IconCheck size={14} />
                </ActionIcon>
              </Tooltip>)}
            <Tooltip label="Cambiar la fecha o la sede">
              <ActionIcon size="sm" variant="subtle" color="gray" aria-label="Reprogramar cita"
                onClick={reprogramar}><IconPencil size={14} /></ActionIcon>
            </Tooltip>
            <Tooltip label="Ya pasó: el solicitante asistió">
              <ActionIcon size="sm" variant="subtle" color="gray" loading={guardando}
                aria-label="Marcar realizada" onClick={() => cambiar({ estado: 'realizada' })}>
                <IconArrowRight size={14} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Cancelar la cita">
              <ActionIcon size="sm" variant="subtle" color="red" loading={guardando}
                aria-label="Cancelar cita" onClick={() => cambiar({ estado: 'cancelada' })}>
                <IconX size={14} />
              </ActionIcon>
            </Tooltip>
          </Group>)}
      </Table.Td>
    </Table.Tr>)
}

/** Mover una cita de fecha o de sede. Queda como «reprogramada», que no es lo
 *  mismo que una cita nueva: el historial conserva que ya hubo una antes. */
function ModalReprogramar({ cita, cerrar, hecho }: {
  cita: Esquemas['CitaSalida'] | null; cerrar: () => void; hecho: () => void
}) {
  const catalogos = useCatalogos()
  const formulario = useForm({
    initialValues: { fecha: '', hora: '08:00', sede_id: '', observaciones: '' },
    validate: { fecha: (v) => (v ? null : 'Elija la fecha nueva') },
  })

  // Al abrir, el formulario arranca con lo que la cita tiene hoy
  useEffect(() => {
    if (!cita) return
    const d = new Date(cita.inicia_en)
    const dos = (n: number) => String(n).padStart(2, '0')
    formulario.setValues({
      fecha: `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}`,
      hora: `${dos(d.getHours())}:${dos(d.getMinutes())}`,
      sede_id: cita.sede_id ? String(cita.sede_id) : '',
      observaciones: cita.observaciones ?? '',
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cita?.id])

  const guardar = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.PATCH('/api/v1/citas/{cita_id}', {
      params: { path: { cita_id: cita!.id } },
      body: { inicia_en: `${v.fecha}T${v.hora}:00-05:00`, estado: 'reprogramada',
              sede_id: v.sede_id ? Number(v.sede_id) : null,
              observaciones: v.observaciones || null },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Cita reprogramada' })
      hecho(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo reprogramar'),
  })

  return (
    <Modal opened={cita !== null} onClose={cerrar}
      title={`Reprogramar la cita de ${cita?.tipo ?? ''}`}>
      <form onSubmit={formulario.onSubmit((v) => guardar.mutate(v))}>
        <Stack>
          <Group grow>
            <TextInput type="date" label="Fecha" data-autofocus {...formulario.getInputProps('fecha')} />
            <TextInput type="time" label="Hora" {...formulario.getInputProps('hora')} />
          </Group>
          <Select label="Sede" data={aSelect(catalogos.data?.sedes)} searchable clearable
            {...formulario.getInputProps('sede_id')} />
          <Textarea label="Por qué se movió" autosize minRows={2}
            placeholder="El consulado la corrió, el cliente pidió otra fecha…"
            {...formulario.getInputProps('observaciones')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={guardar.isPending}>Reprogramar</Button>
          </Group>
        </Stack>
      </form>
    </Modal>)
}


/**
 * Quién más trabaja en este trámite (RF-026).
 *
 * El responsable sigue siendo uno solo a propósito: RN-04 pide que todo trámite
 * activo tenga responsable, y uno con tres dueños no tiene ninguno. Colaborar es
 * otra cosa —acompañar una cita, cubrir una ausencia, atender al cliente
 * mientras el responsable no está— y hasta ahora obligaba a reasignar el
 * trámite, que cambia quién responde por él.
 *
 * Quien tiene alcance limitado **sí ve** los trámites en los que colabora. Esa
 * es toda la gracia: sin eso, el nombre saldría en la ficha y la persona no
 * podría abrirla.
 */
function Colaboradores({ casoId, responsableId, editable }: {
  casoId: number; responsableId?: number | null; editable: boolean
}) {
  const qc = useQueryClient()
  const asignables = useAsignables()
  const [agregando, setAgregando] = useState<string | null>(null)

  const lista = useQuery({
    queryKey: ['caso', casoId, 'colaboradores'],
    queryFn: () => exigir(api.GET('/api/v1/casos/{caso_id}/colaboradores', {
      params: { path: { caso_id: casoId } },
    })),
  })

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['caso', casoId] })
    qc.invalidateQueries({ queryKey: ['casos'] })
  }

  const agregar = useMutation({
    mutationFn: (usuario_id: number) =>
      exigir(api.POST('/api/v1/casos/{caso_id}/colaboradores', {
        params: { path: { caso_id: casoId } }, body: { usuario_id },
      })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Ya puede ver y trabajar este trámite' })
      setAgregando(null)
      refrescar()
    },
    onError: (e) => mostrarError(e, 'No se pudo agregar'),
  })

  const quitar = useMutation({
    mutationFn: (usuario_id: number) =>
      exigir(api.DELETE('/api/v1/casos/{caso_id}/colaboradores/{usuario_id}', {
        params: { path: { caso_id: casoId, usuario_id } },
      })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Deja de colaborar; si su alcance es limitado, deja de ver el trámite' })
      refrescar()
    },
    onError: (e) => mostrarError(e, 'No se pudo quitar'),
  })

  const yaEstan = new Set((lista.data ?? []).map((c) => c.usuario_id))
  const disponibles = (asignables.data ?? [])
    .filter((u) => u.id !== responsableId && !yaEstan.has(u.id))
    .map((u) => ({ value: String(u.id), label: u.nombre }))

  return (
    <Stack gap={6}>
      <Text size="xs" fw={500} c="dimmed">Colaboran</Text>
      <Group gap={6}>
        {(lista.data ?? []).length === 0 && (
          <Text size="xs" c="dimmed">Solo el responsable.</Text>)}
        {(lista.data ?? []).map((c) => (
          <Badge key={c.usuario_id} variant="light" size="lg"
            rightSection={editable && (
              <ActionIcon size="xs" variant="transparent" color="gray"
                aria-label={`Quitar a ${c.nombre}`}
                onClick={() => quitar.mutate(c.usuario_id)}>
                <IconX size={12} />
              </ActionIcon>)}>
            {c.nombre}
          </Badge>))}
      </Group>
      {editable && (
        <Select size="xs" searchable clearable placeholder="Sumar a alguien"
          data={disponibles} value={agregando}
          nothingFoundMessage="Ya están todos"
          onChange={(v) => { setAgregando(v); if (v) agregar.mutate(Number(v)) }} />)}
    </Stack>
  )
}
