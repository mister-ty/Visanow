import {
  Alert, Badge, Button, Card, Center, Group, Loader, Modal, Select, SimpleGrid, Stack, Switch, Table,
  Tabs, Text, TextInput, Title,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { mostrarError } from '../lib/errores'
import { aInstanteBogota, formatearFechaHora } from '../lib/formato'

type Alerta = Esquemas['AlertaSalida']
type TipoAlerta = Esquemas['TipoAlertaSalida']
type Severidad = Alerta['severidad']

const COLOR_SEVERIDAD: Record<Severidad, string> = { alta: 'red', media: 'yellow', baja: 'gray' }
const NOMBRE_SEVERIDAD: Record<Severidad, string> = { alta: 'Alta', media: 'Media', baja: 'Baja' }
const NOMBRE_ESTADO: Record<Alerta['estado'], string> = {
  nueva: 'Nueva', vista: 'Vista', resuelta: 'Resuelta', pospuesta: 'Pospuesta',
}
const NOMBRE_UNIDAD: Record<string, string> = { horas: 'hora(s)', dias: 'día(s)', dias_habiles: 'día(s) hábil(es)' }

/** Centro de alertas (RF-061, RF-062). */
export function Alertas() {
  const { puede } = useSesion()
  const cq = useQueryClient()

  // Nada en el servidor llama a /alertas/generar por sí solo. Mientras no haya
  // un proceso programado, abrir esta pantalla lo dispara: es idempotente (la
  // clave de deduplicación impide repetir y una alerta resuelta no renace), así
  // que correrlo en cada apertura es seguro. Solo quien puede crear alertas.
  const generada = useRef(false)
  const generar = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/alertas/generar', { body: {} })),
    onSuccess: () => {
      cq.invalidateQueries({ queryKey: ['alertas'] })
    },
    onError: (e) => mostrarError(e, 'No se pudieron actualizar las alertas'),
  })
  const puedeGenerar = puede('alertas.crear')
  const { mutate: lanzarGeneracion } = generar
  useEffect(() => {
    if (puedeGenerar && !generada.current) {
      generada.current = true
      lanzarGeneracion()
    }
  }, [puedeGenerar, lanzarGeneracion])

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Alertas</Title>
          <Text size="sm" c="dimmed">Lo que requiere atención, lo grave primero.</Text>
        </div>
        {puedeGenerar && (
          <Button variant="default" loading={generar.isPending} onClick={() => generar.mutate()}>
            Buscar alertas nuevas</Button>)}
      </Group>
      <Tabs defaultValue="bandeja" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="bandeja">Bandeja</Tabs.Tab>
          <Tabs.Tab value="tipos">Tipos de alerta</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="bandeja" pt="md"><Bandeja /></Tabs.Panel>
        <Tabs.Panel value="tipos" pt="md"><Tipos /></Tabs.Panel>
      </Tabs>
    </Stack>
  )
}

function Bandeja() {
  const [severidad, setSeveridad] = useState<string | null>(null)
  const [soloAbiertas, setSoloAbiertas] = useState(true)
  const [posponiendo, setPosponiendo] = useState<Alerta | null>(null)

  const resumen = useQuery({
    queryKey: ['alertas', 'resumen'],
    queryFn: () => exigir(api.GET('/api/v1/alertas/resumen')),
  })
  const consulta = {
    solo_abiertas: soloAbiertas, tamano: 100,
    ...(severidad ? { severidad: severidad as Severidad } : {}),
  }
  const alertas = useQuery({
    queryKey: ['alertas', 'lista', consulta],
    queryFn: () => exigir(api.GET('/api/v1/alertas', { params: { query: consulta } })),
    placeholderData: keepPreviousData,
  })
  const r = resumen.data

  return (
    <Stack>
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Contador titulo="Abiertas" valor={r?.total} />
        <Contador titulo="Altas" valor={r?.alta} color="red" />
        <Contador titulo="Medias" valor={r?.media} color="yellow" />
        <Contador titulo="Bajas" valor={r?.baja} />
      </SimpleGrid>
      <Group align="flex-end">
        <Select label="Severidad" w={160} clearable value={severidad} onChange={(v) => setSeveridad(v === null ? null : String(v))}
          data={Object.entries(NOMBRE_SEVERIDAD).map(([value, label]) => ({ value, label }))} />
        <Switch mb={8} label="Solo abiertas" checked={soloAbiertas}
          onChange={(e) => setSoloAbiertas(e.currentTarget.checked)} />
      </Group>

      {alertas.isPending ? <Center h={120}><Loader color="teal" /></Center> : (
        <Card withBorder padding={0}>
          <Table.ScrollContainer minWidth={820}>
            <Table verticalSpacing="sm" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Alerta</Table.Th><Table.Th>Severidad</Table.Th><Table.Th>Generada</Table.Th>
                  <Table.Th>Estado</Table.Th><Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {alertas.data?.items.map((a) => (
                  <FilaAlerta key={a.id} alerta={a} posponer={() => setPosponiendo(a)} />))}
                {alertas.data?.items.length === 0 && (
                  <Table.Tr><Table.Td colSpan={5}>
                    <Text size="sm" c="dimmed" ta="center" py="lg">No hay alertas con esos filtros.</Text>
                  </Table.Td></Table.Tr>)}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>)}
      <Text size="sm" c="dimmed">{alertas.data?.total ?? 0} alerta(s)</Text>
      <ModalPosponer key={posponiendo?.id ?? 'ninguna'} alerta={posponiendo} cerrar={() => setPosponiendo(null)} />
    </Stack>
  )
}

function Contador({ titulo, valor, color }: { titulo: string; valor: number | undefined; color?: string }) {
  return (
    <Card withBorder padding="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{titulo}</Text>
      <Text size="xl" fw={700} c={valor ? color : undefined}>{valor ?? '—'}</Text>
    </Card>)
}

function FilaAlerta({ alerta: a, posponer }: { alerta: Alerta; posponer: () => void }) {
  const { puede } = useSesion()
  const cq = useQueryClient()
  const cambiar = useMutation({
    mutationFn: (estado: 'vista' | 'resuelta') => exigir(api.PATCH('/api/v1/alertas/{alerta_id}', {
      params: { path: { alerta_id: a.id } }, body: { estado },
    })),
    onSuccess: () => cq.invalidateQueries({ queryKey: ['alertas'] }),
    onError: (e) => mostrarError(e, 'No se pudo cambiar la alerta'),
  })
  const abierta = a.estado !== 'resuelta'
  return (
    <Table.Tr style={!abierta ? { opacity: 0.6 } : undefined}>
      <Table.Td>
        <Text size="sm" fw={500}>{a.tipo_nombre}</Text>
        <Text size="sm">{a.mensaje}</Text>
        {a.caso_id && <Text size="xs" component={Link} to={`/casos/${a.caso_id}`}>Ver trámite</Text>}
      </Table.Td>
      <Table.Td><Badge variant="light" color={COLOR_SEVERIDAD[a.severidad]}>{NOMBRE_SEVERIDAD[a.severidad]}</Badge></Table.Td>
      <Table.Td>{formatearFechaHora(a.generada_en)}</Table.Td>
      <Table.Td>
        {NOMBRE_ESTADO[a.estado]}
        {a.estado === 'pospuesta' && a.pospuesta_hasta && (
          <Text size="xs" c="dimmed">hasta {formatearFechaHora(a.pospuesta_hasta)}</Text>)}
      </Table.Td>
      <Table.Td>
        {abierta && puede('alertas.editar') && (
          <Group gap="xs" justify="flex-end" wrap="nowrap">
            {a.estado === 'nueva' && (
              <Button size="compact-sm" variant="default" loading={cambiar.isPending}
                onClick={() => cambiar.mutate('vista')}>Marcar vista</Button>)}
            <Button size="compact-sm" variant="default" onClick={posponer}>Posponer</Button>
            <Button size="compact-sm" loading={cambiar.isPending}
              onClick={() => cambiar.mutate('resuelta')}>Resolver</Button>
          </Group>)}
      </Table.Td>
    </Table.Tr>)
}

/** Posponer exige fecha: una alerta pospuesta «para después» no vuelve nunca. */
function ModalPosponer({ alerta, cerrar }: { alerta: Alerta | null; cerrar: () => void }) {
  const cq = useQueryClient()
  const [hasta, setHasta] = useState('')
  const m = useMutation({
    mutationFn: () => exigir(api.PATCH('/api/v1/alertas/{alerta_id}', {
      params: { path: { alerta_id: alerta!.id } },
      body: { estado: 'pospuesta', hasta: aInstanteBogota(hasta) },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', title: 'Alerta pospuesta', message: 'Vuelve a la bandeja al cumplirse el plazo.' })
      cq.invalidateQueries({ queryKey: ['alertas'] }); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo posponer'),
  })
  return (
    <Modal opened={alerta !== null} onClose={cerrar} title="Posponer alerta">
      <Stack>
        <Text size="sm">{alerta?.mensaje}</Text>
        <TextInput label="Posponer hasta" type="datetime-local" required value={hasta}
          description="Hora de Bogotá. Debe ser una fecha futura" onChange={(e) => setHasta(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button disabled={!hasta} loading={m.isPending} onClick={() => m.mutate()}>Posponer</Button>
        </Group>
      </Stack>
    </Modal>)
}

/**
 * La matriz con la que nacen las alertas (RF-062).
 *
 * Es editable, no un informe: el día que «2 horas» resulten pocas para avisar
 * de un lead sin contactar, eso se cambia acá y no en la base de datos. Lo que
 * no se deja tocar es el código ni la entidad —identifican la consulta que
 * evalúa el tipo, y cambiarlos lo dejaría configurado pero sin nadie que lo
 * mire—, así que no aparecen en el formulario.
 */
function Tipos() {
  const { puede } = useSesion()
  const qc = useQueryClient()
  const [editando, setEditando] = useState<TipoAlerta | null>(null)
  const editable = puede('catalogos.editar')

  const tipos = useQuery({
    queryKey: ['alertas', 'tipos'],
    queryFn: () => exigir(api.GET('/api/v1/alertas/tipos')),
  })

  const apagar = useMutation({
    mutationFn: ({ codigo, activo }: { codigo: string; activo: boolean }) =>
      exigir(api.PATCH('/api/v1/alertas/tipos/{codigo}', {
        params: { path: { codigo } }, body: { activo },
      })),
    onSuccess: (_d, v) => {
      notifications.show({
        color: 'teal',
        message: v.activo
          ? 'Vuelve a generar alertas de este tipo'
          : 'Deja de generar alertas nuevas; las que ya hay siguen en la bandeja',
      })
      qc.invalidateQueries({ queryKey: ['alertas'] })
    },
    onError: (e) => mostrarError(e, 'No se pudo cambiar'),
  })

  if (tipos.isPending) return <Center h={120}><Loader color="teal" /></Center>
  return (
    <Stack>
      <Alert color="blue" variant="light">
        Esta es la matriz con la que se generan las alertas.{' '}
        {editable
          ? 'Cambiar una fila cambia cuándo avisa, a quién y con qué urgencia, desde la próxima vez que se busquen alertas.'
          : 'Solo la administradora puede cambiarla.'}{' '}
        Un tipo «sin regla» está configurado pero todavía no hay quien lo evalúe, así que no genera nada.
      </Alert>
      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={980}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Tipo</Table.Th><Table.Th>Sobre</Table.Th><Table.Th>Anticipación</Table.Th>
                <Table.Th>Repeticiones</Table.Th><Table.Th>Severidad</Table.Th><Table.Th>Canal</Table.Th>
                <Table.Th>Le llega a</Table.Th><Table.Th>Estado</Table.Th>
                {editable && <Table.Th />}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {tipos.data?.map((t) => (
                <Table.Tr key={t.id}>
                  <Table.Td><Text size="sm" fw={500}>{t.nombre}</Text><Text size="xs" c="dimmed">{t.codigo}</Text></Table.Td>
                  <Table.Td>{t.entidad}</Table.Td>
                  <Table.Td>{t.anticipacion_valor} {NOMBRE_UNIDAD[t.anticipacion_unidad]}</Table.Td>
                  <Table.Td>{t.repeticiones.length ? t.repeticiones.join(', ') : '—'}</Table.Td>
                  <Table.Td><Badge variant="light" color={COLOR_SEVERIDAD[t.severidad]}>{NOMBRE_SEVERIDAD[t.severidad]}</Badge></Table.Td>
                  <Table.Td>{t.canal}</Table.Td>
                  <Table.Td>{t.destinatario_rol ?? '—'}</Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {editable
                        ? <Switch size="xs" checked={t.activo} label={t.activo ? 'Activo' : 'Inactivo'}
                            onChange={(e) => apagar.mutate({ codigo: t.codigo, activo: e.currentTarget.checked })} />
                        : <Badge variant="light" color={t.activo ? 'teal' : 'gray'}>{t.activo ? 'Activo' : 'Inactivo'}</Badge>}
                      {!t.tiene_regla && <Badge variant="light" color="orange">Sin regla</Badge>}
                    </Group>
                  </Table.Td>
                  {editable && (
                    <Table.Td>
                      <Button size="xs" variant="light" onClick={() => setEditando(t)}>Ajustar</Button>
                    </Table.Td>)}
                </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      {editando && <AjustarTipo tipo={editando} cerrar={() => setEditando(null)} />}
    </Stack>)
}

/** El formulario de una fila de la matriz. */
function AjustarTipo({ tipo, cerrar }: { tipo: TipoAlerta; cerrar: () => void }) {
  const qc = useQueryClient()
  const [valor, setValor] = useState(String(tipo.anticipacion_valor))
  const [unidad, setUnidad] = useState(tipo.anticipacion_unidad)
  const [severidad, setSeveridad] = useState(tipo.severidad)
  const [canal, setCanal] = useState(tipo.canal)
  const [rol, setRol] = useState(tipo.destinatario_rol_id ? String(tipo.destinatario_rol_id) : null)
  const [reps, setReps] = useState(tipo.repeticiones.join(', '))

  const roles = useQuery({
    queryKey: ['roles'],
    queryFn: () => exigir(api.GET('/api/v1/roles')),
    staleTime: 10 * 60 * 1000,
  })

  const guardar = useMutation({
    mutationFn: () => exigir(api.PATCH('/api/v1/alertas/tipos/{codigo}', {
      params: { path: { codigo: tipo.codigo } },
      body: {
        anticipacion_valor: Number(valor),
        anticipacion_unidad: unidad,
        severidad,
        canal,
        destinatario_rol_id: rol ? Number(rol) : undefined,
        repeticiones: reps.split(',').map((x) => Number(x.trim())).filter((x) => x > 0),
      },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'La matriz quedó cambiada' })
      qc.invalidateQueries({ queryKey: ['alertas'] })
      cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo guardar'),
  })

  return (
    <Modal opened onClose={cerrar} title={tipo.nombre} size="lg">
      <Stack>
        <Text size="sm" c="dimmed">
          Sobre {tipo.entidad}. El código «{tipo.codigo}» no se cambia: es lo que une
          este tipo con la consulta que lo evalúa.
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Anticipación" value={valor} onChange={(e) => setValor(e.currentTarget.value)}
            description="Positivo avisa antes del hecho; negativo, después" />
          <Select label="Unidad" data={[
            { value: 'horas', label: 'horas' },
            { value: 'dias', label: 'días' },
            { value: 'dias_habiles', label: 'días hábiles' }]}
            value={unidad} onChange={(v) => v && setUnidad(v as TipoAlerta['anticipacion_unidad'])} />
          <Select label="Severidad" data={[
            { value: 'baja', label: 'Baja' }, { value: 'media', label: 'Media' },
            { value: 'alta', label: 'Alta' }]}
            value={severidad} onChange={(v) => v && setSeveridad(v as TipoAlerta['severidad'])} />
          <Select label="Canal" data={[
            { value: 'interna', label: 'interna' }, { value: 'correo', label: 'correo' },
            { value: 'whatsapp', label: 'whatsapp' }]}
            value={canal} onChange={(v) => v && setCanal(v)} />
          {/* El filtro no sobra: una opción sin `value` se vuelve "undefined",
              dos se vuelven dos "undefined", y Mantine tumba la página entera
              por opciones repetidas. Mejor un desplegable corto que una
              pantalla en blanco. */}
          <Select label="Le llega a" value={rol} onChange={setRol} clearable
            data={(roles.data ?? [])
              .filter((r) => r.id != null)
              .map((r) => ({ value: String(r.id), label: r.nombre }))}
            nothingFoundMessage="No se pudo cargar la lista de roles"
            description="Quién recibe este aviso" />
          <TextInput label="Repeticiones" value={reps} onChange={(e) => setReps(e.currentTarget.value)}
            placeholder="7, 15" description="A los cuántos días vuelve a insistir" />
        </SimpleGrid>
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={guardar.isPending} onClick={() => guardar.mutate()}>Guardar</Button>
        </Group>
      </Stack>
    </Modal>)
}
