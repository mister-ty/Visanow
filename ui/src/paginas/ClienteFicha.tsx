import {
  ActionIcon, Alert, Badge, Button, Card, Center, Checkbox, Group, Loader, Modal, Select, Stack,
  Table, Text, TextInput, Title, Tooltip,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconArchive, IconEye, IconPencil, IconPlus, IconUsersGroup } from '@tabler/icons-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { AvisoDuplicados, type Coincidencia } from '../componentes/AvisoDuplicados'
import { mostrarError } from '../lib/errores'
import { formatearFechaHora } from '../lib/formato'

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

  const ficha = useQuery({
    queryKey: ['cliente', clienteId],
    queryFn: () => exigir(api.GET('/api/v1/clientes/{cliente_id}', {
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
  const c = ficha.data

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

      <Card withBorder padding="lg">
        <Group gap="xl">
          <Dato titulo="Documento" valor={c.numero_documento ? `${c.tipo_documento ?? ''} ${c.numero_documento}`.trim() : null} />
          <Dato titulo="Teléfono" valor={c.telefono} />
          <Dato titulo="Correo" valor={c.email} />
          <Dato titulo="Ciudad" valor={c.ciudad} />
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
            <TablaSolicitantes solicitantes={g.solicitantes} />
          </Card>
        ))}

        {(() => {
          const sueltos = c.solicitantes.filter((s) => !s.grupo_id)
          return sueltos.length > 0 && (
            <Card withBorder padding="sm" mt="sm">
              <Text size="sm" fw={600} mb="xs">Sin grupo</Text>
              <TablaSolicitantes solicitantes={sueltos} />
            </Card>
          )
        })()}
      </Card>

      <FormularioEditar cliente={c} abierto={editando} cerrar={() => setEditando(false)} guardado={refrescar} />
      <FormularioGrupo clienteId={clienteId} abierto={nuevoGrupo} cerrar={() => setNuevoGrupo(false)} creado={refrescar} />
      <FormularioSolicitante destino={agregarA} cerrar={() => setAgregarA(null)} creado={refrescar} />
    </Stack>
  )
}

const Dato = ({ titulo, valor }: { titulo: string; valor: string | null | undefined }) => (
  <div>
    <Text size="xs" c="dimmed">{titulo}</Text>
    <Text size="sm">{valor || '—'}</Text>
  </div>
)

function TablaSolicitantes({ solicitantes }: { solicitantes: Solicitante[] }) {
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
          <Table.Th>Documento</Table.Th><Table.Th>Pasaporte</Table.Th>
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
    },
  })
  const guardar = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.PATCH('/api/v1/clientes/{cliente_id}', {
      params: { path: { cliente_id: cliente.id } },
      body: Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x === '' ? null : x])) as never,
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
          <TextInput label="Ciudad" {...formulario.getInputProps('ciudad')} />
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
