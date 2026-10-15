import {
  ActionIcon, Alert, Anchor, Badge, Button, Card, Center, Checkbox, Group, Loader, Modal, Select,
  SimpleGrid, Stack, Table, Text, Textarea, TextInput, Timeline, Title, Tooltip,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useDebouncedValue } from '@mantine/hooks'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  IconArchive, IconArrowsExchange, IconBrandWhatsapp, IconCalendarEvent, IconEye, IconHistory,
  IconMail, IconMessage2, IconPencil, IconPhone, IconPlaneDeparture, IconPlus, IconUsersGroup,
} from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { Link as Enlace, useNavigate, useParams } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { AvisoDuplicados, type Coincidencia } from '../componentes/AvisoDuplicados'
import { CamposCliente, CLIENTE_VACIO } from '../componentes/CamposCliente'
import { Documentos } from '../componentes/Documentos'
import { mostrarError } from '../lib/errores'
import { formatearFechaHora, formatearPesos } from '../lib/formato'
import { aSelect, type Opcion, porPais, useAsignables, useCatalogos } from '../lib/catalogos'

type Detalle = Esquemas['ClienteDetalle']
type Solicitante = Esquemas['SolicitanteSalida']
type Grupo = Esquemas['GrupoSalida']

const RELACIONES = ['titular', 'cónyuge', 'hijo', 'hija', 'padre', 'madre', 'otro']
/** RF-003 nombra estas dos clases de grupo y son las dos que acepta la API. */
const TIPOS_GRUPO = [
  { value: 'familiar', label: 'Familiar' },
  { value: 'viaje', label: 'De viaje' },
]

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
  const [editandoPersona, setEditandoPersona] = useState<Solicitante | null>(null)
  const [moviendo, setMoviendo] = useState<Solicitante | null>(null)
  const [uniendo, setUniendo] = useState<Solicitante | null>(null)
  const [editandoGrupo, setEditandoGrupo] = useState<Grupo | null>(null)
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
  // Unir dos personas mueve trámites: lo autoriza quien puede eliminarlas, que
  // hoy es solo la administradora (RF-002).
  const puedeUnir = puede('solicitantes.eliminar') && c.solicitantes.length > 1

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

      <Dinero dinero={f.dinero} />

      {f.ve_oportunidades && f.oportunidades.length > 0 && (
        <Card withBorder padding="lg">
          <Text fw={600} mb="sm">Oportunidades</Text>
          <Table.ScrollContainer minWidth={620}>
            <Table verticalSpacing={6}>
              <Table.Thead><Table.Tr>
                <Table.Th>Servicio</Table.Th><Table.Th>País</Table.Th>
                <Table.Th>Estado</Table.Th><Table.Th>Próxima acción</Table.Th>
              </Table.Tr></Table.Thead>
              <Table.Tbody>
                {f.oportunidades.map((o) => (
                  <Table.Tr key={o.id}>
                    <Table.Td><Text size="sm">{o.servicio ?? '—'}</Text></Table.Td>
                    <Table.Td><Text size="sm">{o.pais ?? '—'}</Text></Table.Td>
                    <Table.Td><Badge variant="light">{o.estado}</Badge></Table.Td>
                    <Table.Td><Text size="sm" c="dimmed">{o.proxima_accion ?? '—'}</Text></Table.Td>
                  </Table.Tr>))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>)}

      {f.ve_trabajo && (f.tareas.length > 0 || f.alertas.length > 0) && (
        <Card withBorder padding="lg">
          <Text fw={600} mb="sm">Pendientes</Text>
          <Stack gap={6}>
            {f.alertas.map((a) => (
              <Group key={`a${a.id}`} gap={8} wrap="nowrap">
                <Badge size="sm" variant="light"
                  color={a.severidad === 'alta' ? 'red' : a.severidad === 'media' ? 'yellow' : 'gray'}>
                  {a.severidad}
                </Badge>
                <Text size="sm" style={{ flex: 1 }}>{a.mensaje}</Text>
                {a.estado === 'resuelta' && <Text size="xs" c="dimmed">resuelta</Text>}
              </Group>))}
            {f.tareas.map((t) => (
              <Group key={`t${t.id}`} gap={8} wrap="nowrap">
                <Badge size="sm" variant="outline" color="gray">tarea</Badge>
                <Text size="sm" style={{ flex: 1 }}
                  td={['hecha', 'cancelada'].includes(t.estado) ? 'line-through' : undefined}>
                  {t.titulo}
                </Text>
                {t.responsable && <Text size="xs" c="dimmed">{t.responsable}</Text>}
              </Group>))}
          </Stack>
        </Card>)}

      <Card withBorder padding="lg">
        <Text fw={600} mb="sm">Archivos adjuntos</Text>
        <Documentos entidad="cliente" entidadId={c.id} puedeEditar={puede('clientes.editar')} />
      </Card>

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
              <div>
                <Text size="sm" fw={600}>{g.nombre}</Text>
                {/* Quién contrata es parte de RF-003 y la tarjeta no lo decía:
                    con dos grupos en la ficha no se sabía a nombre de quién iba
                    cada uno. */}
                <Text size="xs" c="dimmed">Contrata {g.contacto_nombre ?? '—'}</Text>
              </div>
              <Group gap="xs">
                <Badge variant="light" size="sm" color={g.tipo === 'viaje' ? 'indigo' : 'teal'}>
                  {g.tipo === 'viaje' ? 'De viaje' : 'Familiar'}
                </Badge>
                <Badge variant="light" size="sm">{g.solicitantes.length} persona(s)</Badge>
                {puede('solicitantes.editar') && (
                  <Tooltip label="Corregir el nombre o quién contrata">
                    <ActionIcon size="sm" variant="subtle" color="gray" aria-label="Editar grupo"
                      onClick={() => setEditandoGrupo(g)}><IconPencil size={13} /></ActionIcon>
                  </Tooltip>)}
                {puede('solicitantes.crear') && (
                  <Button size="compact-xs" variant="subtle"
                    onClick={() => setAgregarA({ grupo_id: g.id })}>Agregar</Button>
                )}
              </Group>
            </Group>
            <TablaSolicitantes solicitantes={g.solicitantes} tramitar={setTramitando}
              puedeTramitar={puede('casos.crear')} puedeEditar={puede('solicitantes.editar')}
              editar={setEditandoPersona} mover={setMoviendo}
              unir={setUniendo} puedeUnir={puedeUnir} tramites={f.ve_tramites ? f.tramites : undefined} />
          </Card>
        ))}

        {(() => {
          const sueltos = c.solicitantes.filter((s) => !s.grupo_id)
          return sueltos.length > 0 && (
            <Card withBorder padding="sm" mt="sm">
              <Text size="sm" fw={600} mb="xs">Sin grupo</Text>
              <TablaSolicitantes solicitantes={sueltos} tramitar={setTramitando}
                puedeTramitar={puede('casos.crear')} puedeEditar={puede('solicitantes.editar')}
                editar={setEditandoPersona} mover={setMoviendo}
                unir={setUniendo} puedeUnir={puedeUnir} tramites={f.ve_tramites ? f.tramites : undefined} />
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
      <FormularioSolicitante destino={agregarA} clienteId={clienteId}
        cerrar={() => setAgregarA(null)} creado={refrescar} />
      <FormularioTramite solicitante={tramitando} cerrar={() => setTramitando(null)} />
      <FormularioEditarPersona solicitante={editandoPersona}
        cerrar={() => setEditandoPersona(null)} guardado={refrescar} />
      {/* La `key` remonta el formulario al cambiar de persona: sin eso se vería
          por un instante el grupo de la anterior. */}
      <FormularioMover key={moviendo?.id ?? 'ninguno'} solicitante={moviendo} clienteId={clienteId}
        grupos={c.grupos} cerrar={() => setMoviendo(null)} guardado={refrescar} />
      <FormularioEditarGrupo grupo={editandoGrupo} cerrar={() => setEditandoGrupo(null)}
        guardado={refrescar} />
      <FormularioUnirPersonas key={uniendo?.id ?? 'ninguna'} conservada={uniendo}
        personas={c.solicitantes} cerrar={() => setUniendo(null)} guardado={refrescar} />
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

function TablaSolicitantes({ solicitantes, tramitar, puedeTramitar, puedeEditar, editar, mover,
                             unir, puedeUnir, tramites }: {
  solicitantes: Solicitante[]
  tramitar: (s: Solicitante) => void
  unir: (s: Solicitante) => void
  puedeUnir: boolean
  /** Los trámites del cliente, para contar los de cada persona. `undefined`
   *  cuando a quien mira no se le muestran: la columna entonces no sale, para
   *  no enseñar un cero que se leería como «esta persona no tiene trámites». */
  tramites?: Esquemas['CasoSalida'][]
  puedeTramitar: boolean
  puedeEditar: boolean
  editar: (s: Solicitante) => void
  mover: (s: Solicitante) => void
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
    <Table.ScrollContainer minWidth={720}>
      <Table verticalSpacing={6}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Persona</Table.Th><Table.Th>Relación</Table.Th>
            <Table.Th>Documento</Table.Th><Table.Th>Pasaporte</Table.Th>
            {tramites && <Table.Th>Trámites</Table.Th>}
            <Table.Th w={160} />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {solicitantes.map((s) => (
            <Table.Tr key={s.id}>
              <Table.Td>
                <Text size="sm">{s.nombre}</Text>
                {/* Los datos propios de la persona. Existían en la base y no se
                    veían en ninguna pantalla (RF-004). */}
                {(s.fecha_nacimiento || s.telefono || s.email) && (
                  <Text size="xs" c="dimmed">
                    {[s.fecha_nacimiento, s.telefono, s.email].filter(Boolean).join(' · ')}
                  </Text>)}
              </Table.Td>
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
              {tramites && (
                <Table.Td>
                  {/* Cada persona con los suyos, aunque la venta y el pago sean
                      del grupo (RF-004). */}
                  <Text size="sm">{tramites.filter((t) => t.solicitante_id === s.id).length}</Text>
                </Table.Td>)}
              <Table.Td>
                <Group gap={4} justify="flex-end" wrap="nowrap">
                  {puedeEditar && (
                    <>
                      <Tooltip label="Corregir sus datos">
                        <ActionIcon size="sm" variant="subtle" color="gray" aria-label="Editar persona"
                          onClick={() => editar(s)}><IconPencil size={13} /></ActionIcon>
                      </Tooltip>
                      <Tooltip label={s.grupo_id ? 'Sacar del grupo o pasarlo a otro' : 'Meterlo en un grupo'}>
                        <ActionIcon size="sm" variant="subtle" color="gray" aria-label="Mover de grupo"
                          onClick={() => mover(s)}><IconArrowsExchange size={13} /></ActionIcon>
                      </Tooltip>
                    </>)}
                  {puedeUnir && (
                    <Tooltip label="Unir a esta persona otra repetida">
                      <ActionIcon size="sm" variant="subtle" color="gray" aria-label="Unir personas"
                        onClick={() => unir(s)}><IconUsersGroup size={13} /></ActionIcon>
                    </Tooltip>)}
                  {puedeTramitar && (
                    <Button size="compact-xs" variant="light" leftSection={<IconPlaneDeparture size={12} />}
                      onClick={() => tramitar(s)}>Nuevo trámite</Button>)}
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  )
}

function FormularioEditar({ cliente, abierto, cerrar, guardado }: {
  cliente: Detalle; abierto: boolean; cerrar: () => void; guardado: () => void
}) {
  const formulario = useForm({
    initialValues: {
      ...CLIENTE_VACIO,
      nombre: cliente.nombre, tipo_documento: cliente.tipo_documento ?? '',
      numero_documento: cliente.numero_documento ?? '', telefono: cliente.telefono ?? '',
      email: cliente.email ?? '', ciudad: cliente.ciudad ?? '',
      consentimiento: cliente.consentimiento, observaciones: cliente.observaciones ?? '',
      pais_id: cliente.pais_id ? String(cliente.pais_id) : '',
      canal_id: cliente.canal_id ? String(cliente.canal_id) : '',
    },
  })
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
          <CamposCliente formulario={formulario} />
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
  const formulario = useForm({
    initialValues: { nombre: '', tipo: 'familiar', observaciones: '' },
  })
  const crear = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.POST('/api/v1/grupos', {
      body: { nombre: v.nombre, cliente_contacto_id: clienteId,
              tipo: v.tipo as 'familiar', observaciones: v.observaciones || null },
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
          <Select label="¿Qué clase de grupo es?" data={TIPOS_GRUPO} allowDeselect={false}
            description="La familia renueva junta y viaja con menores; el grupo de viaje es una vez"
            {...formulario.getInputProps('tipo')} />
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

function FormularioSolicitante({ destino, clienteId, cerrar, creado }: {
  destino: { grupo_id?: number; cliente_id?: number } | null; clienteId: number
  cerrar: () => void; creado: () => void
}) {
  const formulario = useForm({
    initialValues: { nombre: '', tipo_documento: '', numero_documento: '', pasaporte: '',
                     fecha_nacimiento: '', telefono: '', email: '',
                     nacionalidad: '', relacion_con_cliente: '' },
    validate: { nombre: (v) => (v.trim().length >= 2 ? null : 'Escriba el nombre') },
  })
  const [datos] = useDebouncedValue(formulario.values, 400)
  const [confirmado, setConfirmado] = useState(false)

  // El pasaporte entra en la detección ANTES de guardar (RF-002). Hasta ahora
  // solo se comparaba cuando la ficha ya existía: al registrar, lo único que
  // avisaba era el índice único con un «ese pasaporte ya está», que no dice de
  // quién es ni deja ver la ficha parecida.
  //
  // Se excluye esta misma ficha: el solicitante casi siempre se llama igual que
  // el cliente del que cuelga, y avisarlo sería pedir confirmación de que una
  // persona no es ella misma.
  const posibles = useQuery({
    queryKey: ['duplicados-persona', clienteId, datos.nombre, datos.numero_documento,
               datos.pasaporte, datos.telefono, datos.email],
    queryFn: () => exigir(api.POST('/api/v1/clientes/verificar-duplicados', {
      body: { nombre: datos.nombre, numero_documento: datos.numero_documento || undefined,
              pasaporte: datos.pasaporte || undefined, telefono: datos.telefono || undefined,
              email: datos.email || undefined, excluir_id: clienteId },
    })),
    enabled: destino !== null && datos.nombre.trim().length >= 3,
  })
  const hayFuerte = (posibles.data ?? []).some((c) => c.confianza === 'alta')

  const crear = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.POST('/api/v1/solicitantes', {
      body: { ...destino, ...Object.fromEntries(Object.entries(v).filter(([, x]) => x !== '')) } as never,
    })),
    onSuccess: () => { formulario.reset(); setConfirmado(false); creado(); cerrar() },
    onError: (e) => mostrarError(e, 'No se pudo agregar'),
  })
  return (
    <Modal opened={destino !== null} onClose={cerrar} title="Agregar persona al trámite" size="lg">
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
          {/* Datos de la persona, no del cliente: el consulado cita a cada
              quien por su cuenta, así que el teléfono y el correo del hijo que
              estudia afuera no son los de la mamá que contrata (RF-004). */}
          <Group grow>
            <TextInput label="Fecha de nacimiento" type="date"
              {...formulario.getInputProps('fecha_nacimiento')} />
            <TextInput label="Nacionalidad" {...formulario.getInputProps('nacionalidad')} />
          </Group>
          <Group grow>
            <TextInput label="Teléfono" placeholder="3105177800"
              description="El de esta persona, si es distinto al del cliente"
              {...formulario.getInputProps('telefono')} />
            <TextInput label="Correo" type="email" {...formulario.getInputProps('email')} />
          </Group>

          <AvisoDuplicados coincidencias={posibles.data} cargando={posibles.isFetching} />
          {hayFuerte && (
            <Checkbox color="red" checked={confirmado} onChange={(e) => setConfirmado(e.currentTarget.checked)}
              label="Revisé las fichas parecidas y confirmo que es una persona distinta" />
          )}

          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={crear.isPending}
              disabled={hayFuerte && !confirmado}>Agregar</Button>
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
        <Table.ScrollContainer minWidth={840}>
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
        </Table.ScrollContainer>
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


/** Corregir los datos de una persona. El pasaporte se deja en blanco si no se
 *  va a cambiar: llega enmascarado y reenviarlo así lo dañaría. */
function FormularioEditarPersona({ solicitante, cerrar, guardado }: {
  solicitante: Solicitante | null; cerrar: () => void; guardado: () => void
}) {
  const formulario = useForm({
    initialValues: { nombre: '', tipo_documento: '', numero_documento: '', pasaporte: '',
                     fecha_nacimiento: '', telefono: '', email: '',
                     nacionalidad: '', relacion_con_cliente: '', observaciones: '' },
  })
  useEffect(() => {
    if (!solicitante) return
    formulario.setValues({
      nombre: solicitante.nombre, tipo_documento: solicitante.tipo_documento ?? '',
      numero_documento: solicitante.numero_documento ?? '', pasaporte: '',
      fecha_nacimiento: solicitante.fecha_nacimiento ?? '',
      telefono: solicitante.telefono ?? '', email: solicitante.email ?? '',
      nacionalidad: solicitante.nacionalidad ?? '',
      relacion_con_cliente: solicitante.relacion_con_cliente ?? '',
      observaciones: solicitante.observaciones ?? '',
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [solicitante?.id])

  const guardar = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.PATCH('/api/v1/solicitantes/{solicitante_id}', {
      params: { path: { solicitante_id: solicitante!.id } },
      body: Object.fromEntries(
        Object.entries(v).filter(([k, x]) => k !== 'pasaporte' || x !== '')
          .map(([k, x]) => [k, x === '' ? null : x])) as never,
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Datos corregidos' })
      guardado(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo guardar'),
  })

  return (
    <Modal opened={solicitante !== null} onClose={cerrar} title="Corregir los datos de la persona">
      <form onSubmit={formulario.onSubmit((v) => guardar.mutate(v))}>
        <Stack>
          <TextInput label="Nombre completo" data-autofocus {...formulario.getInputProps('nombre')} />
          <Group grow>
            <TextInput label="Tipo de documento" {...formulario.getInputProps('tipo_documento')} />
            <TextInput label="Número de documento" {...formulario.getInputProps('numero_documento')} />
          </Group>
          <TextInput label="Pasaporte" placeholder="Déjelo vacío si no cambia"
            description="Se guarda cifrado. Escribirlo aquí reemplaza el que estaba."
            {...formulario.getInputProps('pasaporte')} />
          <Group grow>
            <TextInput label="Nacionalidad" {...formulario.getInputProps('nacionalidad')} />
            <Select label="Relación" data={RELACIONES} clearable
              {...formulario.getInputProps('relacion_con_cliente')} />
          </Group>
          {/* Los datos propios de la persona (RF-004). Existían en la API desde
              el principio y no había dónde escribirlos: hoy no hay ni un
              solicitante con fecha de nacimiento, que es lo primero que pide el
              consulado para un menor. */}
          <Group grow>
            <TextInput label="Fecha de nacimiento" type="date"
              {...formulario.getInputProps('fecha_nacimiento')} />
            <TextInput label="Teléfono" {...formulario.getInputProps('telefono')} />
          </Group>
          <TextInput label="Correo" type="email"
            description="El de esta persona, si es distinto al del cliente"
            {...formulario.getInputProps('email')} />
          <TextInput label="Observaciones" {...formulario.getInputProps('observaciones')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={guardar.isPending}>Guardar</Button>
          </Group>
        </Stack>
      </form>
    </Modal>)
}

/** Mover a alguien entre el cliente y sus grupos. Nadie puede quedar suelto:
 *  un solicitante sin grupo y sin cliente sería un trámite de nadie. */
function FormularioMover({ solicitante, clienteId, grupos, cerrar, guardado }: {
  solicitante: Solicitante | null; clienteId: number; grupos: Grupo[]
  cerrar: () => void; guardado: () => void
}) {
  // El componente se remonta por su `key` cuando cambia la persona, así que el
  // valor inicial basta y no hace falta un efecto que lo sincronice.
  const [destino, setDestino] = useState<string>(
    solicitante?.grupo_id ? String(solicitante.grupo_id) : 'cliente')

  const mover = useMutation({
    mutationFn: () => exigir(api.PATCH('/api/v1/solicitantes/{solicitante_id}', {
      params: { path: { solicitante_id: solicitante!.id } },
      body: destino === 'cliente'
        ? { grupo_id: null, cliente_id: clienteId }
        : { grupo_id: Number(destino) },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Persona movida' })
      guardado(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo mover'),
  })

  const opciones = [
    { value: 'cliente', label: 'Sin grupo (cuelga del cliente)' },
    ...grupos.map((g) => ({ value: String(g.id), label: g.nombre })),
  ]

  return (
    <Modal opened={solicitante !== null} onClose={cerrar}
      title={`Mover a ${solicitante?.nombre ?? ''}`}>
      <Stack>
        <Select label="¿Dónde queda?" data={opciones} value={destino} allowDeselect={false}
          onChange={(v) => setDestino(v ?? 'cliente')} data-autofocus
          description="Sus trámites se mueven con la persona: no se pierde nada." />
        {grupos.length === 0 && (
          <Alert color="gray" variant="light">
            Todavía no hay grupos. Cree uno desde «Nuevo grupo» para poder mover personas.
          </Alert>)}
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={mover.isPending} onClick={() => mover.mutate()}>Mover</Button>
        </Group>
      </Stack>
    </Modal>)
}

/**
 * Unir dos registros de la misma persona (RF-002).
 *
 * La misma persona entra dos veces —una al cotizar, de memoria, y otra cuando
 * llega el pasaporte— y cada copia se queda con un pedazo de la historia. Antes
 * la única salida era borrar una, que es perder su trámite.
 *
 * Solo entre personas del mismo cliente: a través de clientes movería los
 * trámites de una ficha a otra y la primera se quedaría sin ellos.
 */
function FormularioUnirPersonas({ conservada, personas, cerrar, guardado }: {
  conservada: Solicitante | null; personas: Solicitante[]
  cerrar: () => void; guardado: () => void
}) {
  const [absorbida, setAbsorbida] = useState<string | null>(null)
  const candidatas = personas.filter((s) => s.id !== conservada?.id)

  const unir = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/solicitantes/{solicitante_id}/fusionar', {
      params: { path: { solicitante_id: conservada!.id } },
      body: { absorbido_id: Number(absorbida), criterio: 'manual' },
    })),
    onSuccess: (r) => {
      const movidos = Object.entries(r.movidos).map(([t, n]) => `${n} ${t}`).join(', ')
      notifications.show({ color: 'teal', title: 'Personas unidas',
        message: movidos ? `Se trasladaron ${movidos}.` : 'No había registros que trasladar.' })
      guardado(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudieron unir'),
  })

  return (
    <Modal opened={conservada !== null} onClose={cerrar}
      title={`Unir otra persona a ${conservada?.nombre ?? ''}`}>
      <Stack>
        <Select label="¿Cuál es la repetida?" data-autofocus
          data={candidatas.map((s) => ({ value: String(s.id), label: s.nombre }))}
          value={absorbida} onChange={(v) => setAbsorbida(v === null ? null : String(v))}
          description="Sus trámites, sus documentos y su pasaporte pasan a la persona que queda" />
        {candidatas.length === 0 && (
          <Alert color="gray" variant="light">Esta ficha solo tiene una persona.</Alert>)}
        <Alert color="yellow" variant="light">
          La repetida queda archivada y sale de la ficha. Queda registro de qué se unió y por qué,
          pero no se puede deshacer.
        </Alert>
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button color="red" disabled={!absorbida} loading={unir.isPending}
            onClick={() => unir.mutate()}>Unir</Button>
        </Group>
      </Stack>
    </Modal>)
}

/** Corregir el grupo. «Quién contrata» es el verbo que pide RF-003 y hasta
 *  ahora quedaba fijo en quien lo creó. */
function FormularioEditarGrupo({ grupo, cerrar, guardado }: {
  grupo: Grupo | null; cerrar: () => void; guardado: () => void
}) {
  const formulario = useForm({
    initialValues: { nombre: '', tipo: 'familiar', cliente_contacto_id: '', observaciones: '' },
  })
  useEffect(() => {
    if (grupo) formulario.setValues({
      nombre: grupo.nombre, tipo: grupo.tipo,
      cliente_contacto_id: String(grupo.cliente_contacto_id),
      observaciones: grupo.observaciones ?? '',
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grupo?.id])

  // Quién contrata se busca escribiendo: son casi novecientas personas y un
  // desplegable con todas no se puede usar.
  const [texto, setTexto] = useState('')
  const [busqueda] = useDebouncedValue(texto, 300)
  const candidatos = useQuery({
    queryKey: ['clientes', 'contacto-de-grupo', busqueda],
    queryFn: () => exigir(api.GET('/api/v1/clientes', {
      params: { query: { texto: busqueda || undefined, tamano: 20 } },
    })),
    enabled: grupo !== null,
  })
  // El contacto actual va siempre, aunque la búsqueda no lo traiga: si no, el
  // desplegable se vería vacío y guardar lo cambiaría sin que nadie lo pidiera.
  const opciones = [
    ...(grupo ? [{ value: String(grupo.cliente_contacto_id),
                   label: grupo.contacto_nombre ?? 'El contacto de ahora' }] : []),
    ...(candidatos.data?.items ?? [])
      .filter((c) => c.id !== grupo?.cliente_contacto_id)
      .map((c) => ({ value: String(c.id), label: c.nombre })),
  ]

  const guardar = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.PATCH('/api/v1/grupos/{grupo_id}', {
      params: { path: { grupo_id: grupo!.id } },
      body: { nombre: v.nombre, tipo: v.tipo as 'familiar',
              cliente_contacto_id: Number(v.cliente_contacto_id),
              observaciones: v.observaciones || null },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Grupo corregido' })
      guardado(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo guardar'),
  })

  return (
    <Modal opened={grupo !== null} onClose={cerrar} title="Corregir el grupo">
      <form onSubmit={formulario.onSubmit((v) => guardar.mutate(v))}>
        <Stack>
          <TextInput label="Nombre del grupo" data-autofocus {...formulario.getInputProps('nombre')} />
          <Select label="¿Qué clase de grupo es?" data={TIPOS_GRUPO} allowDeselect={false}
            {...formulario.getInputProps('tipo')} />
          <Select label="Quién contrata" data={opciones} searchable allowDeselect={false}
            description="El grupo pasa a la ficha de quien contrate, con sus personas"
            searchValue={texto} onSearchChange={setTexto}
            nothingFoundMessage={busqueda ? 'Ningún cliente con ese nombre' : undefined}
            {...formulario.getInputProps('cliente_contacto_id')} />
          <TextInput label="Observaciones" {...formulario.getInputProps('observaciones')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={guardar.isPending}>Guardar</Button>
          </Group>
        </Stack>
      </form>
    </Modal>)
}


/**
 * La plata del cliente, o solo si está al día, según quién pregunte (RF-005).
 *
 * Operaciones necesita saber si el cliente pagó el anticipo para arrancar el
 * trámite, y no tiene por qué ver cuánto (respuesta de la administradora del
 * 29/09). Por eso el servidor manda `ve_montos`: la pantalla no decide esto,
 * lo obedece. Y cuando no los ve, se dice —«no se le muestran»— en vez de
 * enseñar ceros, que se leerían como «este cliente no ha pagado nada».
 */
function Dinero({ dinero }: { dinero: Esquemas['DineroEnFicha'] }) {
  const { ve_montos, al_dia, ventas, pagos, total_pactado, total_pagado, saldo } = dinero
  if (ventas.length === 0 && al_dia === null) return null

  return (
    <Card withBorder padding="lg">
      <Group justify="space-between" mb="sm">
        <Text fw={600}>Ventas y pagos</Text>
        {al_dia !== null && (
          <Badge variant="light" color={al_dia ? 'teal' : 'red'}>
            {al_dia ? 'Al día' : 'Tiene saldo vencido'}
          </Badge>)}
      </Group>

      {ve_montos && total_pactado !== null && (
        <Group gap="xl" mb="sm">
          <div><Text size="xs" c="dimmed">Pactado</Text>
            <Text fw={600}>{formatearPesos(total_pactado)}</Text></div>
          <div><Text size="xs" c="dimmed">Pagado</Text>
            <Text fw={600}>{formatearPesos(total_pagado ?? 0)}</Text></div>
          <div><Text size="xs" c="dimmed">Saldo</Text>
            <Text fw={600} c={(saldo ?? 0) > 0 ? 'red' : undefined}>
              {formatearPesos(saldo ?? 0)}</Text></div>
        </Group>)}

      {ventas.length > 0 && (
        <Table.ScrollContainer minWidth={ve_montos ? 620 : 420}>
          <Table verticalSpacing={6}>
            <Table.Thead><Table.Tr>
              <Table.Th>Servicio</Table.Th><Table.Th>Fecha</Table.Th>
              <Table.Th>Personas</Table.Th>
              {ve_montos && <><Table.Th>Pactado</Table.Th><Table.Th>Saldo</Table.Th></>}
              <Table.Th>Estado</Table.Th>
            </Table.Tr></Table.Thead>
            <Table.Tbody>
              {ventas.map((v) => (
                <Table.Tr key={v.id}>
                  <Table.Td><Text size="sm">{v.servicio ?? '—'}</Text></Table.Td>
                  <Table.Td><Text size="sm">{v.fecha_venta}</Text></Table.Td>
                  <Table.Td><Text size="sm">{v.personas}</Text></Table.Td>
                  {ve_montos && (
                    <><Table.Td><Text size="sm">{formatearPesos(v.valor_pactado)}</Text></Table.Td>
                      <Table.Td><Text size="sm" c={v.saldo > 0 ? 'red' : undefined}>
                        {formatearPesos(v.saldo)}</Text></Table.Td></>)}
                  <Table.Td><Badge variant="light" size="sm">{v.estado_financiero}</Badge></Table.Td>
                </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>)}

      {!ve_montos && ventas.length > 0 && (
        <Text size="xs" c="dimmed" mt={6}>
          Los montos no se le muestran a su perfil. Lo que sí puede ver es si el cliente
          está al día, que es lo que hace falta para arrancar un trámite.
        </Text>)}

      {ve_montos && pagos.length > 0 && (
        <>
          <Text fw={600} size="sm" mt="md" mb={6}>Últimos pagos</Text>
          <Stack gap={4}>
            {pagos.slice(0, 8).map((p) => (
              <Group key={p.id} gap={10} wrap="nowrap">
                <Text size="sm" style={{ minWidth: 92 }}>{p.fecha}</Text>
                <Text size="sm" fw={500}>{formatearPesos(p.monto)}</Text>
                <Text size="xs" c="dimmed">{p.medio ?? ''}</Text>
                {p.referencia && <Text size="xs" c="dimmed">· {p.referencia}</Text>}
              </Group>))}
          </Stack>
        </>)}
    </Card>
  )
}
