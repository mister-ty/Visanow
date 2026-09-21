import {
  ActionIcon, Alert, Badge, Button, Card, Code, CopyButton, Group, Menu, Modal, Select, Stack, Switch,
  Table, Text, TextInput, Title, Tooltip,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconCheck, IconCopy, IconDots, IconLock, IconPlus, IconShieldCheck } from '@tabler/icons-react'
import { useState } from 'react'
import { api, exigir, type Esquemas, type Usuario } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { mostrarError } from '../lib/errores'
import { formatearFechaHora, NOMBRES_ALCANCE, NOMBRES_ROL } from '../lib/formato'

type Temporal = Esquemas['PasswordTemporalSalida']

const opcionesAlcance = Object.entries(NOMBRES_ALCANCE).map(([value, label]) => ({ value, label }))

export function Usuarios() {
  const { yo, puede } = useSesion()
  const clienteQuery = useQueryClient()
  const [creando, setCreando] = useState(false)
  const [editando, setEditando] = useState<Usuario | null>(null)
  const [temporal, setTemporal] = useState<{ titulo: string; dato: Temporal } | null>(null)

  const usuarios = useQuery({ queryKey: ['usuarios'], queryFn: () => exigir(api.GET('/api/v1/usuarios')) })
  const roles = useQuery({ queryKey: ['roles'], queryFn: () => exigir(api.GET('/api/v1/roles')) })
  const opcionesRol = (roles.data ?? []).map((r) => ({ value: r.codigo, label: NOMBRES_ROL[r.codigo] ?? r.nombre }))
  const refrescar = () => clienteQuery.invalidateQueries({ queryKey: ['usuarios'] })

  const restablecer = useMutation({
    mutationFn: (u: Usuario) => exigir(api.POST('/api/v1/usuarios/{usuario_id}/restablecer-password',
      { params: { path: { usuario_id: u.id } } })),
    onSuccess: (dato) => { refrescar(); setTemporal({ titulo: 'Contraseña restablecida', dato }) },
    onError: (e) => mostrarError(e),
  })
  const reiniciarMfa = useMutation({
    mutationFn: (u: Usuario) => exigir(api.POST('/api/v1/usuarios/{usuario_id}/reiniciar-mfa',
      { params: { path: { usuario_id: u.id } } })),
    onSuccess: (dato) => { refrescar(); setTemporal({ titulo: 'Doble factor reiniciado', dato }) },
    onError: (e) => mostrarError(e),
  })

  const confirmar = (titulo: string, texto: string, accion: () => void) =>
    modals.openConfirmModal({
      title: titulo, children: <Text size="sm">{texto}</Text>, onConfirm: accion,
      labels: { confirm: 'Sí, continuar', cancel: 'Cancelar' }, confirmProps: { color: 'red' },
    })

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Usuarios</Title>
        {puede('usuarios.crear') && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setCreando(true)}>Nuevo usuario</Button>
        )}
      </Group>

      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={760}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Nombre</Table.Th><Table.Th>Perfil</Table.Th><Table.Th>Estado</Table.Th>
                <Table.Th>Doble factor</Table.Th><Table.Th>Último ingreso</Table.Th><Table.Th w={48} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {usuarios.data?.map((u) => (
                <Table.Tr key={u.id}>
                  <Table.Td>
                    <Text size="sm" fw={500}>{u.nombre}</Text>
                    <Text size="xs" c="dimmed">{u.email}</Text>
                  </Table.Td>
                  <Table.Td><Badge variant="light">{NOMBRES_ROL[u.rol] ?? u.rol}</Badge></Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {u.activo ? <Badge color="teal" variant="dot">Activo</Badge> : <Badge color="gray" variant="dot">Inactivo</Badge>}
                      {u.bloqueado && <Tooltip label="Bloqueado por intentos fallidos. Restablecer la contraseña lo desbloquea.">
                        <Badge color="red" variant="light" leftSection={<IconLock size={12} />}>Bloqueado</Badge></Tooltip>}
                      {u.debe_cambiar_password && <Badge color="yellow" variant="light">Contraseña temporal</Badge>}
                    </Group>
                  </Table.Td>
                  <Table.Td>{u.mfa_habilitado
                    ? <IconShieldCheck size={18} color="var(--mantine-color-teal-7)" aria-label="Activo" />
                    : <Text size="xs" c="dimmed">No activo</Text>}</Table.Td>
                  <Table.Td><Text size="sm">{formatearFechaHora(u.ultimo_acceso)}</Text></Table.Td>
                  <Table.Td>
                    {puede('usuarios.editar') && (
                      <Menu position="bottom-end" withinPortal>
                        <Menu.Target><ActionIcon variant="subtle" color="gray" aria-label="Acciones">
                          <IconDots size={16} /></ActionIcon></Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Item onClick={() => setEditando(u)}>Editar</Menu.Item>
                          <Menu.Item onClick={() => confirmar('Restablecer contraseña',
                            `${u.nombre} recibirá una contraseña temporal y se cerrarán sus sesiones abiertas.`,
                            () => restablecer.mutate(u))}>Restablecer contraseña</Menu.Item>
                          {u.mfa_habilitado && (
                            <Menu.Item onClick={() => confirmar('Reiniciar doble factor',
                              `Para cuando ${u.nombre} pierde el teléfono. Por seguridad también se le reinicia la ` +
                              'contraseña: recibirá una temporal y tendrá que activar el doble factor de nuevo.',
                              () => reiniciarMfa.mutate(u))}>Reiniciar doble factor</Menu.Item>
                          )}
                        </Menu.Dropdown>
                      </Menu>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      <FormularioNuevo abierto={creando} cerrar={() => setCreando(false)} opcionesRol={opcionesRol}
        creado={(dato) => { refrescar(); setTemporal({ titulo: 'Usuario creado', dato }) }} />
      <FormularioEditar usuario={editando} cerrar={() => setEditando(null)} opcionesRol={opcionesRol}
        esUstedMisma={editando?.id === yo?.id} guardado={refrescar} />
      <ContrasenaTemporal temporal={temporal} cerrar={() => setTemporal(null)} />
    </Stack>
  )
}

function FormularioNuevo({ abierto, cerrar, opcionesRol, creado }: {
  abierto: boolean; cerrar: () => void; opcionesRol: { value: string; label: string }[]
  creado: (dato: Temporal) => void
}) {
  const formulario = useForm({
    initialValues: { nombre: '', email: '', rol: '', alcance: 'todos' as Esquemas['UsuarioCrear']['alcance'] },
    validate: {
      nombre: (v) => (v.trim().length >= 2 ? null : 'Escriba el nombre'),
      email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : 'Escriba un correo válido'),
      rol: (v) => (v ? null : 'Elija un perfil'),
    },
  })
  const crear = useMutation({
    mutationFn: (datos: typeof formulario.values) => exigir(api.POST('/api/v1/usuarios', { body: datos })),
    onSuccess: (dato) => { formulario.reset(); cerrar(); creado(dato) },
    onError: (e) => mostrarError(e, 'No se pudo crear'),
  })
  return (
    <Modal opened={abierto} onClose={cerrar} title="Nuevo usuario">
      <form onSubmit={formulario.onSubmit((v) => crear.mutate(v))}>
        <Stack>
          <TextInput label="Nombre" data-autofocus {...formulario.getInputProps('nombre')} />
          <TextInput label="Correo" type="email" {...formulario.getInputProps('email')} />
          <Select label="Perfil" data={opcionesRol} {...formulario.getInputProps('rol')} />
          <Select label="Qué casos ve" data={opcionesAlcance} allowDeselect={false}
            description="El filtro por casos asignados se aplica cuando existan los trámites (28/09)."
            {...formulario.getInputProps('alcance')} />
          <Text size="xs" c="dimmed">Recibirá una contraseña temporal que deberá cambiar al primer ingreso.</Text>
          <Group justify="flex-end"><Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={crear.isPending}>Crear</Button></Group>
        </Stack>
      </form>
    </Modal>
  )
}

function FormularioEditar({ usuario, cerrar, opcionesRol, esUstedMisma, guardado }: {
  usuario: Usuario | null; cerrar: () => void; opcionesRol: { value: string; label: string }[]
  esUstedMisma: boolean; guardado: () => void
}) {
  const valores = usuario
    ? { nombre: usuario.nombre, rol: usuario.rol, activo: usuario.activo,
        alcance: usuario.alcance as Esquemas['UsuarioEditar']['alcance'] }
    : { nombre: '', rol: '', activo: true, alcance: 'todos' as Esquemas['UsuarioEditar']['alcance'] }
  const formulario = useForm({ initialValues: valores })
  const [cargado, setCargado] = useState<number | null>(null)
  if (usuario && cargado !== usuario.id) { formulario.setValues(valores); setCargado(usuario.id) }

  const guardar = useMutation({
    mutationFn: (datos: typeof valores) => exigir(api.PATCH('/api/v1/usuarios/{usuario_id}',
      { params: { path: { usuario_id: usuario!.id } }, body: datos })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Cambios guardados' })
      guardado(); cerrar(); setCargado(null)
    },
    onError: (e) => mostrarError(e, 'No se pudo guardar'),
  })
  return (
    <Modal opened={usuario !== null} onClose={() => { cerrar(); setCargado(null) }} title="Editar usuario">
      <form onSubmit={formulario.onSubmit((v) => guardar.mutate(v))}>
        <Stack>
          <TextInput label="Nombre" {...formulario.getInputProps('nombre')} />
          <Select label="Perfil" data={opcionesRol} disabled={esUstedMisma} allowDeselect={false}
            description={esUstedMisma ? 'Su propio perfil lo cambia otra administradora.' : undefined}
            {...formulario.getInputProps('rol')} />
          <Select label="Qué casos ve" data={opcionesAlcance} allowDeselect={false} {...formulario.getInputProps('alcance')} />
          <Switch label="Activo" disabled={esUstedMisma} description={esUstedMisma ? undefined
            : 'Desactivar cierra su sesión de inmediato. No se borra: su historial se conserva.'}
            {...formulario.getInputProps('activo', { type: 'checkbox' })} />
          <Group justify="flex-end"><Button variant="default" onClick={() => { cerrar(); setCargado(null) }}>Cancelar</Button>
            <Button type="submit" loading={guardar.isPending}>Guardar</Button></Group>
        </Stack>
      </form>
    </Modal>
  )
}

/** La contraseña temporal se muestra una sola vez: el sistema no la guarda en claro. */
function ContrasenaTemporal({ temporal, cerrar }: { temporal: { titulo: string; dato: Temporal } | null; cerrar: () => void }) {
  return (
    <Modal opened={temporal !== null} onClose={cerrar} title={temporal?.titulo} closeOnClickOutside={false}>
      {temporal && (
        <Stack>
          <Text size="sm">Contraseña temporal de <b>{temporal.dato.usuario.nombre}</b>:</Text>
          <Group gap="xs">
            <Code fz="lg" style={{ flex: 1 }} ta="center">{temporal.dato.password_temporal}</Code>
            <CopyButton value={temporal.dato.password_temporal}>
              {({ copied, copy }) => (
                <ActionIcon variant="light" color={copied ? 'teal' : 'gray'} size="lg" onClick={copy}
                  aria-label="Copiar">{copied ? <IconCheck size={16} /> : <IconCopy size={16} />}</ActionIcon>
              )}
            </CopyButton>
          </Group>
          <Alert color="yellow" variant="light">
            Se muestra una sola vez. Entréguela por un canal distinto al correo, por ejemplo por WhatsApp o
            en persona. Al primer ingreso tendrá que cambiarla.
          </Alert>
          <Button onClick={cerrar}>Ya la entregué</Button>
        </Stack>
      )}
    </Modal>
  )
}
