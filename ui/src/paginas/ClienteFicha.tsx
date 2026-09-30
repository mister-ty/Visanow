import {
  ActionIcon, Alert, Anchor, Badge, Button, Card, Center, Checkbox, Group, Loader, Modal, Select,
  SimpleGrid, Stack, Table, Text, Textarea, TextInput, Timeline, Title, Tooltip,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  IconArchive, IconBrandWhatsapp, IconCalendarEvent, IconEye, IconHistory, IconMail, IconMessage2,
  IconPencil, IconPhone, IconPlaneDeparture, IconPlus, IconUsersGroup,
} from '@tabler/icons-react'
import { useState } from 'react'
import { Link as Enlace, useNavigate, useParams } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { AvisoDuplicados, type Coincidencia } from '../componentes/AvisoDuplicados'
import { mostrarError } from '../lib/errores'
import { formatearFechaHora } from '../lib/formato'
import { aSelect, type Opcion, porPais, useAsignables, useCatalogos } from '../lib/catalogos'

type Detalle = Esquemas['ClienteDetalle']
type Solicitante = Esquemas['SolicitanteSalida']

const RELACIONES = ['titular', 'cónyuge', 'hijo', 'hija', 'padre', 'madre', 'otro']

export function ClienteFicha() {
  const { id } = useParams()
  const clienteId = Number(id)
  const { puede } = useSesion()
  const clienteQuery = useQueryClient()
  const [editando, setEditando] = useState(false)
  const [nuevoGrupo, setNuevoGrupo] = useState(false)
  const [agregarA, setAgregarA] = useState<{ grupo_id?: number; cliente_id?: number } | null>(null)
  const [tramitando, setTramitando] = useState<Solicitante | null>(null)
  const [anotando, setAnotando] = useState(false)
  const catalogosFicha = useCatalogos()

  // Una sola consulta trae el cliente, su familia, sus trámites, sus próximas
  // citas y su cronología (RF-005). Antes esto eran tres archivos distintos.
  const ficha = useQuery({
    queryKey: ['cliente', clienteId],
    queryFn: () => exigir(api.GET('/api/v1/clientes/{cliente_id}/ficha', {
      params: { path: { cliente_id: clienteId } },
    })),
  })
  const parecidos = useQuery({
    queryKey: ['cliente', clienteId, 'duplicados'],
    queryFn: () => exigir(api.GET('/api/v1/clientes/{cliente_id}/duplicados', {
      params: { path: { cliente_id: clienteId } },
    })),
    enabled: ficha.isSuccess,
  })
  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ['cliente', clienteId] })

  const archivar = useMutation({
    mutationFn: (archivado: boolean) => exigir(api.POST('/api/v1/clientes/{cliente_id}/archivar', {
      params: { path: { cliente_id: clienteId }, query: { archivado } },
    })),
    onSuccess: () => { refrescar(); clienteQuery.invalidateQueries({ queryKey: ['clientes'] }) },
    onError: (e) => mostrarError(e),
  })

  const fusionar = useMutation({
    mutationFn: (c: Coincidencia) => exigir(api.POST('/api/v1/clientes/{cliente_id}/fusionar', {
      params: { path: { cliente_id: clienteId } },
      body: { absorbido_id: c.cliente_id, criterio: (c.criterios[0] ?? 'manual') as 'manual' },
    })),
    onSuccess: (r) => {
      const movidos = Object.entries(r.movidos).map(([t, n]) => `${n} ${t}`).join(', ')
      notifications.show({ color: 'teal', title: 'Fichas unidas',
        message: movidos ? `Se trasladaron ${movidos}.` : 'No había registros que trasladar.' })
      refrescar()
      clienteQuery.invalidateQueries({ queryKey: ['clientes'] })
      clienteQuery.invalidateQueries({ queryKey: ['cliente', clienteId, 'duplicados'] })
    },
    onError: (e) => mostrarError(e, 'No se pudo fusionar'),
  })

  if (ficha.isPending) return <Center h={200}><Loader color="teal" /></Center>
  if (ficha.isError) return <Alert color="red">No se pudo abrir la ficha. {String(ficha.error)}</Alert>
  const f = ficha.data
  const c = f.cliente

  return (
    <Stack maw={980}>
      <Group justify="space-between" align="flex-start">
        <div>
          <Group gap="xs">
            <Title order={2}>{c.nombre}</Title>
            {c.archivado && <Badge color="gray" variant="light">Archivado</Badge>}
          </Group>
          <Text size="sm" c="dimmed">Cliente desde {formatearFechaHora(c.creado_en)}</Text>
        </div>
        <Group>
          {puede('clientes.editar') && (
            <>
              <Button variant="light" leftSection={<IconMessage2 size={16} />}
                onClick={() => setAnotando(true)}>Registrar contacto</Button>
              <Button variant="default" leftSection={<IconPencil size={16} />}
                onClick={() => setEditando(true)}>Editar</Button>
              <Tooltip label={c.archivado ? 'Vuelve a las listas' : 'Sale de las listas; no se borra nada'}>
                <Button variant="default" leftSection={<IconArchive size={16} />}
                  loading={archivar.isPending} onClick={() => archivar.mutate(!c.archivado)}>
                  {c.archivado ? 'Desarchivar' : 'Archivar'}
                </Button>
              </Tooltip>
            </>
          )}
        </Group>
      </Group>

      <Resumen resumen={f.resumen} />

      <Card withBorder padding="lg">
        <Group gap="xl">
          <Dato titulo="Documento" valor={c.numero_documento ? `${c.tipo_documento ?? ''} ${c.numero_documento}`.trim() : null} />
          <Dato titulo="Teléfono" valor={c.telefono} />
          <Dato titulo="Correo" valor={c.email} />
          <Dato titulo="Ciudad" valor={c.ciudad} />
          <Dato titulo="País" valor={nombreDe(catalogosFicha.data?.paises, c.pais_id)} />
          <Dato titulo="Llegó por" valor={nombreDe(catalogosFicha.data?.canales, c.canal_id)} />
          <Dato titulo="Consentimiento" valor={c.consentimiento ? 'Autorizado' : 'Sin autorizar'} />
        </Group>
        {c.observaciones && <Text size="sm" mt="md">{c.observaciones}</Text>}
      </Card>

      {!!parecidos.data?.length && (
        <AvisoDuplicados coincidencias={parecidos.data} accion={(coincidencia) =>
          puede('clientes.eliminar') ? (
            <Button size="compact-sm" variant="light" color="red" loading={fusionar.isPending}
              onClick={() => modals.openConfirmModal({
                title: 'Unir las dos fichas',
                children: (
                  <Text size="sm">
                    Todo lo de <b>{coincidencia.nombre}</b> (grupos, solicitantes, oportunidades, ventas y tareas)
                    pasa a <b>{c.nombre}</b>, y esa ficha queda archivada. Queda registro de qué se unió.
                    No se puede deshacer.
                  </Text>),
                labels: { confirm: 'Sí, unir', cancel: 'Cancelar' },
                confirmProps: { color: 'red' },
                onConfirm: () => fusionar.mutate(coincidencia),
              })}>Unir a esta ficha</Button>
          ) : null} />
      )}

      <Card withBorder padding="lg">
        <Group justify="space-between" mb="sm">
          <Group gap="xs"><IconUsersGroup size={18} /><Text fw={600}>Grupos y solicitantes</Text></Group>
          {puede('solicitantes.crear') && (
            <Group gap="xs">
              <Button size="compact-sm" variant="light"
                onClick={() => setAgregarA({ cliente_id: clienteId })}>Agregar persona</Button>
              <Button size="compact-sm" variant="light" leftSection={<IconPlus size={14} />}
                onClick={() => setNuevoGrupo(true)}>Nuevo grupo</Button>
            </Group>
          )}
        </Group>

        {c.grupos.length === 0 && c.solicitantes.length === 0 && (
          <Text size="sm" c="dimmed">
            Todavía no hay personas registradas. Un grupo sirve cuando la familia viaja junta: se cobra una sola
            venta, pero cada persona lleva su propio trámite.
          </Text>
        )}

        {c.grupos.map((g) => (
          <Card key={g.id} withBorder padding="sm" mt="sm" bg="gray.0">
            <Group justify="space-between" mb="xs">
              <Text size="sm" fw={600}>{g.nombre}</Text>
              <Group gap="xs">
                <Badge variant="light" size="sm">{g.solicitantes.length} persona(s)</Badge>
                {puede('solicitantes.crear') && (
                  <Button size="compact-xs" variant="subtle"
                    onClick={() => setAgregarA({ grupo_id: g.id })}>Agregar</Button>
                )}
              </Group>
            </Group>
            <TablaSolicitantes solicitantes={g.solicitantes} tramitar={setTramitando}
              puedeTramitar={puede('casos.crear')} />
          </Card>
        ))}

        {(() => {
          const sueltos = c.solicitantes.filter((s) => !s.grupo_id)
          return sueltos.length > 0 && (
            <Card withBorder padding="sm" mt="sm">
              <Text size="sm" fw={600} mb="xs">Sin grupo</Text>
              <TablaSolicitantes solicitantes={sueltos} tramitar={setTramitando}
                puedeTramitar={puede('casos.crear')} />
            </Card>
          )
        })()}
      </Card>

      {f.ve_tramites && <TarjetaTramites tramites={f.tramites} citas={f.citas} />}

      <Cronologia sucesos={f.cronologia} />

      <FormularioNota clienteId={clienteId} tramites={f.tramites} abierto={anotando}
        cerrar={() => setAnotando(false)} guardado={refrescar} />
      <FormularioEditar cliente={c} abierto={editando} cerrar={() => setEditando(false)} guardado={refrescar} />
      <FormularioGrupo clienteId={clienteId} abierto={nuevoGrupo} cerrar={() => setNuevoGrupo(false)} creado={refrescar} />
      <FormularioSolicitante destino={agregarA} cerrar={() => setAgregarA(null)} creado={refrescar} />
      <FormularioTramite solicitante={tramitando} cerrar={() => setTramitando(null)} />
    </Stack>
  )
}

/** Un id de catálogo no le dice nada a nadie: se muestra el nombre. */
const nombreDe = (opciones: Opcion[] | undefined, id: number | null | undefined) =>
  (id ? opciones?.find((o) => o.id === id)?.nombre : null) ?? null

const Dato = ({ titulo, valor }: { titulo: string; valor: string | null | undefined }) => (
  <div>
    <Text size="xs" c="dimmed">{titulo}</Text>
    <Text size="sm">{valor || '—'}</Text>
  </div>
)

function TablaSolicitantes({ solicitantes, tramitar, puedeTramitar }: {
  solicitantes: Solicitante[]; tramitar: (s: Solicitante) => void; puedeTramitar: boolean
}) {
  const ver = useMutation({
    mutationFn: (id: number) => exigir(api.GET('/api/v1/solicitantes/{solicitante_id}/pasaporte', {
      params: { path: { solicitante_id: id } },
    })),
    onSuccess: (r) => modals.open({
      title: 'Pasaporte',
      children: (
        <Stack>
          <Text size="xl" ff="monospace" ta="center">{r.pasaporte}</Text>
          <Alert color="gray" variant="light">
            Esta consulta quedó registrada: se guarda quién vio el pasaporte y cuándo.
          </Alert>
        </Stack>),
    }),
    onError: (e) => mostrarError(e),
  })

  return (
    <Table verticalSpacing={6}>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Persona</Table.Th><Table.Th>Relación</Table.Th>
          <Table.Th>Documento</Table.Th><Table.Th>Pasaporte</Table.Th><Table.Th w={130} />
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {solicitantes.map((s) => (
          <Table.Tr key={s.id}>
            <Table.Td><Text size="sm">{s.nombre}</Text></Table.Td>
            <Table.Td><Text size="sm" c="dimmed">{s.relacion_con_cliente ?? '—'}</Text></Table.Td>
            <Table.Td><Text size="sm">{s.numero_documento ?? '—'}</Text></Table.Td>
            <Table.Td>
              {s.pasaporte ? (
                <Group gap={4}>
                  <Text size="sm" ff="monospace">{s.pasaporte}</Text>
                  <Tooltip label="Ver completo (queda registrado)">
                    <ActionIcon size="sm" variant="subtle" color="gray" aria-label="Ver pasaporte"
                      loading={ver.isPending} onClick={() => ver.mutate(s.id)}>
                      <IconEye size={14} />
                    </ActionIcon>
                  </Tooltip>
                </Group>
              ) : <Text size="sm" c="dimmed">—</Text>}
            </Table.Td>
            <Table.Td>
              {puedeTramitar && (
                <Button size="compact-xs" variant="light" leftSection={<IconPlaneDeparture size={12} />}
                  onClick={() => tramitar(s)}>Nuevo trámite</Button>)}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}

function FormularioEditar({ cliente, abierto, cerrar, guardado }: {
  cliente: Detalle; abierto: boolean; cerrar: () => void; guardado: () => void
}) {
  const formulario = useForm({
    initialValues: {
      nombre: cliente.nombre, tipo_documento: cliente.tipo_documento ?? '',
      numero_documento: cliente.numero_documento ?? '', telefono: cliente.telefono ?? '',
      email: cliente.email ?? '', ciudad: cliente.ciudad ?? '',
      consentimiento: cliente.consentimiento, observaciones: cliente.observaciones ?? '',
      pais_id: cliente.pais_id ? String(cliente.pais_id) : '',
      canal_id: cliente.canal_id ? String(cliente.canal_id) : '',
    },
  })
  const catalogos = useCatalogos()
  const guardar = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.PATCH('/api/v1/clientes/{cliente_id}', {
      params: { path: { cliente_id: cliente.id } },
      body: {
        ...Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x === '' ? null : x])),
        // Los desplegables devuelven texto; la API espera el id numérico
        pais_id: v.pais_id ? Number(v.pais_id) : null,
        canal_id: v.canal_id ? Number(v.canal_id) : null,
      } as never,
    })),
    onSuccess: () => { notifications.show({ color: 'teal', message: 'Cambios guardados' }); guardado(); cerrar() },
    onError: (e) => mostrarError(e, 'No se pudo guardar'),
  })
  return (
    <Modal opened={abierto} onClose={cerrar} title="Editar cliente" size="lg">
      <form onSubmit={formulario.onSubmit((v) => guardar.mutate(v))}>
        <Stack>
          <TextInput label="Nombre completo" {...formulario.getInputProps('nombre')} />
          <Group grow>
            <TextInput label="Tipo de documento" {...formulario.getInputProps('tipo_documento')} />
            <TextInput label="Número de documento" {...formulario.getInputProps('numero_documento')} />
          </Group>
          <Group grow>
            <TextInput label="Teléfono" {...formulario.getInputProps('telefono')} />
            <TextInput label="Correo" type="email" {...formulario.getInputProps('email')} />
          </Group>
          <Group grow>
            <TextInput label="Ciudad" {...formulario.getInputProps('ciudad')} />
            <Select label="País" data={aSelect(catalogos.data?.paises)} searchable clearable
              {...formulario.getInputProps('pais_id')} />
          </Group>
          <Select label="¿Por dónde llegó?" data={aSelect(catalogos.data?.canales)} clearable
            description="Sirve para saber qué canal trae más clientes"
            {...formulario.getInputProps('canal_id')} />
          <TextInput label="Observaciones" {...formulario.getInputProps('observaciones')} />
          <Checkbox label="Autorizó el tratamiento de sus datos personales"
            {...formulario.getInputProps('consentimiento', { type: 'checkbox' })} />
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={guardar.isPending}>Guardar</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

function FormularioGrupo({ clienteId, abierto, cerrar, creado }: {
  clienteId: number; abierto: boolean; cerrar: () => void; creado: () => void
}) {
  const formulario = useForm({ initialValues: { nombre: '', observaciones: '' } })
  const crear = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.POST('/api/v1/grupos', {
      body: { nombre: v.nombre, cliente_contacto_id: clienteId, observaciones: v.observaciones || null },
    })),
    onSuccess: () => { formulario.reset(); creado(); cerrar() },
    onError: (e) => mostrarError(e, 'No se pudo crear el grupo'),
  })
  return (
    <Modal opened={abierto} onClose={cerrar} title="Nuevo grupo">
      <form onSubmit={formulario.onSubmit((v) => crear.mutate(v))}>
        <Stack>
          <TextInput label="Nombre del grupo" placeholder="Familia Basante Díaz" data-autofocus
            description="Este cliente queda como contacto del grupo."
            {...formulario.getInputProps('nombre')} />
          <TextInput label="Observaciones" {...formulario.getInputProps('observaciones')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={crear.isPending}>Crear grupo</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

function FormularioSolicitante({ destino, cerrar, creado }: {
  destino: { grupo_id?: number; cliente_id?: number } | null; cerrar: () => void; creado: () => void
}) {
  const formulario = useForm({
    initialValues: { nombre: '', tipo_documento: '', numero_documento: '', pasaporte: '',
                     nacionalidad: '', relacion_con_cliente: '' },
    validate: { nombre: (v) => (v.trim().length >= 2 ? null : 'Escriba el nombre') },
  })
  const crear = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.POST('/api/v1/solicitantes', {
      body: { ...destino, ...Object.fromEntries(Object.entries(v).filter(([, x]) => x !== '')) } as never,
    })),
    onSuccess: () => { formulario.reset(); creado(); cerrar() },
    onError: (e) => mostrarError(e, 'No se pudo agregar'),
  })
  return (
    <Modal opened={destino !== null} onClose={cerrar} title="Agregar persona al trámite">
      <form onSubmit={formulario.onSubmit((v) => crear.mutate(v))}>
        <Stack>
          <TextInput label="Nombre completo" data-autofocus {...formulario.getInputProps('nombre')} />
          <Group grow>
            <TextInput label="Tipo de documento" {...formulario.getInputProps('tipo_documento')} />
            <TextInput label="Número de documento" {...formulario.getInputProps('numero_documento')} />
          </Group>
          <Group grow>
            <TextInput label="Pasaporte" description="Se guarda cifrado"
              {...formulario.getInputProps('pasaporte')} />
            <Select label="Relación" data={RELACIONES} clearable {...formulario.getInputProps('relacion_con_cliente')} />
          </Group>
          <TextInput label="Nacionalidad" {...formulario.getInputProps('nacionalidad')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={crear.isPending}>Agregar</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

export { ClienteFicha as default }


/** Un trámite se abre sobre una persona, no sobre el cliente: la familia compra
 *  junta pero cada quien tiene su pasaporte y su propio resultado. */
function FormularioTramite({ solicitante, cerrar }: { solicitante: Solicitante | null; cerrar: () => void }) {
  const navegar = useNavigate()
  const catalogos = useCatalogos()
  const asignables = useAsignables()
  const formulario = useForm({
    initialValues: { pais_id: '', tipo_visa_id: '', modalidad_id: '', sede_id: '',
                     responsable_id: '', proxima_accion: 'Pedir documentos al cliente' },
    validate: { pais_id: (v) => (v ? null : 'Elija el país del trámite') },
  })
  const crear = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.POST('/api/v1/casos', {
      body: { solicitante_id: solicitante!.id, pais_id: Number(v.pais_id),
              tipo_visa_id: v.tipo_visa_id ? Number(v.tipo_visa_id) : null,
              modalidad_id: v.modalidad_id ? Number(v.modalidad_id) : null,
              sede_id: v.sede_id ? Number(v.sede_id) : null,
              responsable_id: v.responsable_id ? Number(v.responsable_id) : null,
              proxima_accion: v.proxima_accion || null },
    })),
    onSuccess: (caso) => {
      notifications.show({ color: 'teal', message: 'Trámite creado' })
      formulario.reset()
      cerrar()
      navegar('/casos/' + caso.id)
    },
    onError: (e) => mostrarError(e, 'No se pudo crear el trámite'),
  })
  const pais = formulario.values.pais_id ? Number(formulario.values.pais_id) : undefined
  return (
    <Modal opened={solicitante !== null} onClose={cerrar}
      title={'Nuevo trámite de ' + (solicitante?.nombre ?? '')}>
      <form onSubmit={formulario.onSubmit((v) => crear.mutate(v))}>
        <Stack>
          <Select label="País" data={aSelect(catalogos.data?.paises)} searchable data-autofocus
            {...formulario.getInputProps('pais_id')} />
          <Select label="Tipo de visa" data={aSelect(porPais(catalogos.data?.tipos_visa, pais))} clearable
            {...formulario.getInputProps('tipo_visa_id')} />
          <Select label="Modalidad" data={aSelect(catalogos.data?.modalidades)} clearable
            description="Decide qué checklist de documentos se aplica"
            {...formulario.getInputProps('modalidad_id')} />
          <Select label="Sede de la cita" data={aSelect(catalogos.data?.sedes)} searchable clearable
            {...formulario.getInputProps('sede_id')} />
          <Select label="Responsable"
            data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))}
            clearable {...formulario.getInputProps('responsable_id')} />
          <TextInput label="Próxima acción" {...formulario.getInputProps('proxima_accion')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={crear.isPending}>Crear trámite</Button>
          </Group>
        </Stack>
      </form>
    </Modal>)
}

const COLOR_RIESGO = { alto: 'red', medio: 'yellow', bajo: 'gray', ninguno: 'gray' } as const

/** Lo primero que se necesita saber al abrir la ficha, sin leer nada más. */
function Resumen({ resumen }: { resumen: Esquemas['ResumenFicha'] }) {
  const sinContacto = resumen.dias_sin_contacto
  const nunca = sinContacto === null || sinContacto === undefined
  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
      <Cifra titulo="Personas" valor={String(resumen.personas)} />
      <Cifra titulo="Trámites abiertos" valor={`${resumen.tramites_abiertos} de ${resumen.tramites_total}`}
        color={resumen.tramites_abiertos > 0 ? 'teal' : undefined} />
      <Cifra titulo="Próxima cita"
        valor={resumen.proxima_cita ? formatearFechaHora(resumen.proxima_cita) : 'Sin cita'}
        color={resumen.proxima_cita ? 'teal' : undefined} />
      <Cifra titulo="Último contacto"
        valor={nunca ? 'Sin registro' : sinContacto === 0 ? 'Hoy' : `Hace ${sinContacto} día(s)`}
        color={!nunca && sinContacto > 15 ? 'orange' : undefined} />
    </SimpleGrid>
  )
}

const Cifra = ({ titulo, valor, color }: { titulo: string; valor: string; color?: string }) => (
  <Card withBorder padding="sm">
    <Text size="xs" c="dimmed">{titulo}</Text>
    <Text size="sm" fw={600} c={color}>{valor}</Text>
  </Card>
)

/** Los trámites de toda la familia y las citas que vienen, juntos: es la
 *  pregunta que el cliente hace por teléfono, «¿en qué va lo mío?». */
function TarjetaTramites({ tramites, citas }: {
  tramites: Esquemas['CasoSalida'][]; citas: Esquemas['CitaProxima'][]
}) {
  const navegar = useNavigate()
  return (
    <Card withBorder padding="lg">
      <Group gap="xs" mb="sm"><IconPlaneDeparture size={18} /><Text fw={600}>Trámites</Text></Group>

      {tramites.length === 0 ? (
        <Text size="sm" c="dimmed">
          Ninguna de estas personas tiene trámite abierto. Se abre desde la tabla de personas.
        </Text>
      ) : (
        <Table verticalSpacing={6} highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Persona</Table.Th><Table.Th>Destino</Table.Th><Table.Th>Estado</Table.Th>
              <Table.Th>Responsable</Table.Th><Table.Th>Próxima acción</Table.Th><Table.Th>Sin mover</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {tramites.map((t) => (
              <Table.Tr key={t.id} style={{ cursor: 'pointer' }} onClick={() => navegar(`/casos/${t.id}`)}>
                <Table.Td><Text size="sm">{t.solicitante}</Text></Table.Td>
                <Table.Td><Text size="sm" c="dimmed">{t.pais ?? '—'}</Text></Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    <Badge variant="light" color={t.es_final ? 'gray' : 'teal'}>{t.estado_nombre}</Badge>
                    {t.resultado && (
                      <Badge size="xs" variant="light" color={t.resultado === 'aprobada' ? 'teal' : 'red'}>
                        {t.resultado}
                      </Badge>)}
                  </Group>
                </Table.Td>
                <Table.Td>
                  {t.responsable
                    ? <Text size="sm">{t.responsable}</Text>
                    : <Badge size="sm" color="orange" variant="light">sin asignar</Badge>}
                </Table.Td>
                <Table.Td><Text size="sm" c="dimmed">{t.proxima_accion ?? '—'}</Text></Table.Td>
                <Table.Td>
                  <Text size="sm" c={COLOR_RIESGO[t.riesgo]}>{t.dias_sin_movimiento} día(s)</Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {citas.length > 0 && (
        <>
          <Group gap="xs" mt="lg" mb="xs">
            <IconCalendarEvent size={16} /><Text fw={600} size="sm">Próximas citas</Text>
          </Group>
          <Stack gap={6}>
            {citas.map((x) => (
              <Group key={x.id} gap="xs" wrap="nowrap">
                <Badge variant="light" color="teal">{formatearFechaHora(x.inicia_en)}</Badge>
                <Text size="sm">{x.solicitante}</Text>
                <Text size="sm" c="dimmed">{x.tipo}{x.sede ? ` · ${x.sede}` : ''}</Text>
              </Group>
            ))}
          </Stack>
        </>
      )}
    </Card>
  )
}

const ICONO_SUCESO: Record<string, typeof IconMessage2> = {
  llamada: IconPhone, whatsapp: IconBrandWhatsapp, correo: IconMail,
  reunion: IconUsersGroup, nota: IconMessage2, sistema: IconHistory,
}

/** Lo que el sistema registró y lo que la gente anotó, en una sola línea de
 *  tiempo: la historia del cliente, que hoy vive en la memoria de quien
 *  atendió la llamada. */
function Cronologia({ sucesos }: { sucesos: Esquemas['SucesoSalida'][] }) {
  const [todos, setTodos] = useState(false)
  const visibles = todos ? sucesos : sucesos.slice(0, 8)
  return (
    <Card withBorder padding="lg">
      <Group gap="xs" mb="md"><IconHistory size={18} /><Text fw={600}>Cronología</Text></Group>
      {sucesos.length === 0 ? (
        <Text size="sm" c="dimmed">
          Todavía no hay nada registrado. Cada llamada, mensaje o cambio de estado queda aquí.
        </Text>
      ) : (
        <>
          <Timeline active={-1} bulletSize={22} lineWidth={2} color="teal">
            {visibles.map((s, i) => {
              const Icono = ICONO_SUCESO[s.tipo] ?? IconMessage2
              return (
                <Timeline.Item key={`${s.cuando}-${i}`} bullet={<Icono size={12} />}
                  title={<Text size="sm" fw={600}>{s.titulo}</Text>}>
                  {s.detalle && <Text size="sm" c="dimmed">{s.detalle}</Text>}
                  <Group gap={4} mt={2}>
                    <Text size="xs" c="dimmed">
                      {formatearFechaHora(s.cuando)}{s.usuario ? ` · ${s.usuario}` : ''}
                    </Text>
                    {s.caso_id && (
                      <Anchor size="xs" component={Enlace} to={`/casos/${s.caso_id}`}>· ver el trámite</Anchor>
                    )}
                  </Group>
                </Timeline.Item>
              )
            })}
          </Timeline>
          {sucesos.length > 8 && (
            <Button variant="subtle" size="compact-sm" mt="sm" onClick={() => setTodos(!todos)}>
              {todos ? 'Ver menos' : `Ver los ${sucesos.length} sucesos`}
            </Button>
          )}
        </>
      )}
    </Card>
  )
}

const TIPOS_CONTACTO = [
  { value: 'llamada', label: 'Llamada' }, { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'correo', label: 'Correo' }, { value: 'reunion', label: 'Reunión' },
  { value: 'nota', label: 'Nota interna' },
]

/** RF-012: la llamada que hoy se anota en un cuaderno, o no se anota. Puede ir
 *  contra el cliente o contra uno de sus trámites. */
function FormularioNota({ clienteId, tramites, abierto, cerrar, guardado }: {
  clienteId: number; tramites: Esquemas['CasoSalida'][]
  abierto: boolean; cerrar: () => void; guardado: () => void
}) {
  const formulario = useForm({
    initialValues: { tipo: 'llamada', asunto: '', cuerpo: '', caso_id: '' },
    validate: { asunto: (v, t) => (v.trim() || t.cuerpo.trim() ? null : 'Escriba al menos el asunto') },
  })
  const guardar = useMutation({
    mutationFn: (v: typeof formulario.values) => {
      const nota = { tipo: v.tipo as 'llamada', asunto: v.asunto.trim() || null, cuerpo: v.cuerpo.trim() || null }
      return v.caso_id
        ? exigir(api.POST('/api/v1/casos/{caso_id}/notas', {
          params: { path: { caso_id: Number(v.caso_id) } }, body: nota,
        }))
        : exigir(api.POST('/api/v1/clientes/{cliente_id}/notas', {
          params: { path: { cliente_id: clienteId } }, body: nota,
        }))
    },
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Contacto registrado' })
      formulario.reset()
      cerrar()
      guardado()
    },
    onError: (e) => mostrarError(e, 'No se pudo registrar'),
  })

  return (
    <Modal opened={abierto} onClose={cerrar} title="Registrar un contacto">
      <form onSubmit={formulario.onSubmit((v) => guardar.mutate(v))}>
        <Stack>
          <Select label="Tipo" data={TIPOS_CONTACTO} allowDeselect={false} data-autofocus
            {...formulario.getInputProps('tipo')} />
          {tramites.length > 0 && (
            <Select label="¿Es sobre un trámite?" placeholder="No, es del cliente en general" clearable
              data={tramites.map((t) => ({ value: String(t.id), label: `${t.solicitante} — ${t.estado_nombre}` }))}
              {...formulario.getInputProps('caso_id')} />
          )}
          <TextInput label="Asunto" placeholder="Llamada de seguimiento"
            {...formulario.getInputProps('asunto')} />
          <Textarea label="Qué se habló" autosize minRows={3} maxRows={8}
            placeholder="Lo que quede escrito aquí es lo que va a leer quien atienda la próxima llamada."
            {...formulario.getInputProps('cuerpo')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={guardar.isPending}>Registrar</Button>
          </Group>
        </Stack>
      </form>
    </Modal>)
}
