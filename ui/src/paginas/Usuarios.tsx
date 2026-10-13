import {
  ActionIcon, Alert, Badge, Button, Card, Checkbox, Code, CopyButton, Divider, Group, Menu,
  Modal, Select, SimpleGrid, Stack, Switch, Table, Text, TextInput, Title, Tooltip,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  IconCheck, IconCopy, IconDots, IconKey, IconLock, IconPlus, IconShieldCheck,
} from '@tabler/icons-react'
import { useState } from 'react'
import { api, exigir, type Esquemas, type Rol, type Usuario } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { mostrarError } from '../lib/errores'
import { formatearFechaHora, NOMBRES_ALCANCE, NOMBRES_ROL } from '../lib/formato'

type Temporal = Esquemas['PasswordTemporalSalida']
type Permiso = Esquemas['PermisoSalida']

const opcionesAlcance = Object.entries(NOMBRES_ALCANCE).map(([value, label]) => ({ value, label }))

/** Quien lo tenga puede reescribir la matriz, y con eso alcanzar cualquier otro
 *  permiso. Se marca aparte en la pantalla para que no se preste sin pensarlo. */
const LLAVE_MAESTRA = 'usuarios.permisos'

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

      <Permisos roles={roles.data} recargarRoles={() => clienteQuery.invalidateQueries({ queryKey: ['roles'] })} />

      <FormularioNuevo abierto={creando} cerrar={() => setCreando(false)} opcionesRol={opcionesRol}
        creado={(dato) => { refrescar(); setTemporal({ titulo: 'Usuario creado', dato }) }} />
      <FormularioEditar usuario={editando} cerrar={() => setEditando(null)} opcionesRol={opcionesRol}
        esUstedMisma={editando?.id === yo?.id} guardado={refrescar} />
      <ContrasenaTemporal temporal={temporal} cerrar={() => setTemporal(null)} />
    </Stack>
  )
}

/** Qué puede hacer cada perfil (RF-077). Hasta hoy esto solo se podía cambiar
 *  editando código Python y volviendo a desplegar. */
function Permisos({ roles, recargarRoles }: { roles: Rol[] | undefined; recargarRoles: () => void }) {
  const { puede, yo } = useSesion()
  const [editando, setEditando] = useState<Rol | null>(null)
  const editable = puede(LLAVE_MAESTRA)

  // El catálogo cambia solo cuando se despliega una versión nueva.
  const catalogo = useQuery({
    queryKey: ['permisos'],
    queryFn: () => exigir(api.GET('/api/v1/permisos')),
    staleTime: 10 * 60 * 1000,
  })

  return (
    <>
      <Title order={3} mt="lg">Qué puede hacer cada perfil</Title>
      <Alert color="blue" variant="light">
        Cambiar un perfil alcanza <b>de inmediato</b> a todas las personas que lo tengan, aunque
        estén trabajando en ese momento.{' '}
        {editable
          ? 'Cada cambio queda en la auditoría con lo que el perfil podía hacer antes y lo que puede hacer ahora.'
          : 'Solo quien tenga «cambiar qué puede hacer cada rol» puede modificarlo; aquí se consulta.'}
      </Alert>

      {editable && catalogo.isError && (
        <Alert color="yellow" variant="light">
          No se pudo cargar la lista de permisos, así que por ahora no se puede cambiar nada.
          Vuelva a cargar la página.
        </Alert>
      )}

      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={640}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Perfil</Table.Th><Table.Th>Permisos</Table.Th>
                <Table.Th>Módulos</Table.Th>{editable && <Table.Th w={140} />}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {roles?.map((r) => (
                <Table.Tr key={r.id}>
                  <Table.Td>
                    <Group gap={6}>
                      <Text size="sm" fw={500}>{NOMBRES_ROL[r.codigo] ?? r.nombre}</Text>
                      {r.permisos.includes(LLAVE_MAESTRA) && (
                        <Tooltip label="Puede cambiar los permisos de cualquier perfil, incluido el suyo">
                          <Badge color="grape" variant="light" leftSection={<IconKey size={12} />}>
                            Gestiona permisos
                          </Badge>
                        </Tooltip>
                      )}
                      {r.codigo === yo?.rol && <Badge variant="outline" color="gray">Su perfil</Badge>}
                    </Group>
                  </Table.Td>
                  <Table.Td><Text size="sm">{r.permisos.length}</Text></Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed">
                      {[...new Set(r.permisos.map((p) => p.split('.')[0]))].sort().join(', ') || '—'}
                    </Text>
                  </Table.Td>
                  {editable && (
                    <Table.Td>
                      <Button variant="light" size="xs" onClick={() => setEditando(r)}
                        loading={catalogo.isPending} disabled={!catalogo.data}>Cambiar</Button>
                    </Table.Td>
                  )}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      {editando && catalogo.data && (
        <FormularioPermisos rol={editando} catalogo={catalogo.data}
          cerrar={() => setEditando(null)} guardado={recargarRoles} />
      )}
    </>
  )
}

/** Las casillas de un perfil, agrupadas por módulo para poder leerlas. */
function FormularioPermisos({ rol, catalogo, cerrar, guardado }: {
  rol: Rol; catalogo: Permiso[]; cerrar: () => void; guardado: () => void
}) {
  const { yo } = useSesion()
  const [marcados, setMarcados] = useState<string[]>(rol.permisos)

  const porModulo = new Map<string, Permiso[]>()
  for (const p of catalogo) porModulo.set(p.modulo, [...(porModulo.get(p.modulo) ?? []), p])

  const guardar = useMutation({
    mutationFn: () => exigir(api.PUT('/api/v1/roles/{rol_id}/permisos', {
      params: { path: { rol_id: rol.id } }, body: { permisos: marcados },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'El perfil quedó cambiado, y ya rige para todos' })
      guardado()
      cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo guardar'),
  })

  // Quitarse a sí misma la llave deja la instalación sin dueña: el backend lo
  // rechaza, pero decirlo antes ahorra el intento y explica por qué.
  const seQuitaLaLlave = rol.codigo === yo?.rol
    && rol.permisos.includes(LLAVE_MAESTRA) && !marcados.includes(LLAVE_MAESTRA)

  return (
    <Modal opened onClose={cerrar} size="xl" title={`Permisos de ${NOMBRES_ROL[rol.codigo] ?? rol.nombre}`}>
      <Stack>
        <Text size="sm" c="dimmed">
          Lo que quede marcado es lo que el perfil podrá hacer. Lo que desmarque se le quita a
          todas las personas que tengan este perfil, en el momento de guardar.
        </Text>

        {seQuitaLaLlave && (
          <Alert color="red" variant="light">
            No puede quitarse a usted misma «cambiar qué puede hacer cada rol»: se quedaría sin
            forma de devolvérselo y habría que arreglarlo por fuera del sistema. Pídale el cambio
            a otra administradora.
          </Alert>
        )}

        <Checkbox.Group value={marcados} onChange={setMarcados}>
          <Stack gap="xs">
            {[...porModulo.entries()].map(([modulo, permisos]) => (
              <div key={modulo}>
                <Divider my="xs" labelPosition="left"
                  label={modulo.charAt(0).toUpperCase() + modulo.slice(1)} />
                <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="xs">
                  {permisos.map((p) => (
                    <Checkbox key={p.codigo} value={p.codigo} label={p.nombre}
                      description={p.codigo}
                      color={p.codigo === LLAVE_MAESTRA ? 'grape' : undefined} />
                  ))}
                </SimpleGrid>
              </div>
            ))}
          </Stack>
        </Checkbox.Group>

        <Group justify="space-between">
          <Text size="xs" c="dimmed">{marcados.length} de {catalogo.length} permisos</Text>
          <Group>
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button onClick={() => guardar.mutate()} loading={guardar.isPending}
              disabled={seQuitaLaLlave}>Guardar</Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
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
