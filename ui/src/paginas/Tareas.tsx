import {
  Badge, Button, Card, Center, Group, Loader, Modal, Select, SimpleGrid, Stack, Switch, Table,
  Text, TextInput, Textarea, Title,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconPlus } from '@tabler/icons-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { useAsignables } from '../lib/catalogos'
import { mostrarError } from '../lib/errores'
import { aInstanteBogota, formatearFechaHora } from '../lib/formato'

type Tarea = Esquemas['TareaSalida']
type EstadoTarea = Tarea['estado']
type Prioridad = Tarea['prioridad']

const NOMBRE_ESTADO: Record<EstadoTarea, string> = {
  pendiente: 'Pendiente', en_curso: 'En curso', hecha: 'Hecha', cancelada: 'Cancelada',
}
const NOMBRE_PRIORIDAD: Record<Prioridad, string> = { alta: 'Alta', media: 'Media', baja: 'Baja' }
const COLOR_PRIORIDAD: Record<Prioridad, string> = { alta: 'red', media: 'yellow', baja: 'gray' }

/** Tareas (RF-060). El backend ya entrega lo urgente arriba (prioridad y
 *  vencimiento); la pantalla no reordena para no contradecirlo. */
export function Tareas() {
  const { puede } = useSesion()
  const [creando, setCreando] = useState(false)
  const [soloAbiertas, setSoloAbiertas] = useState(true)
  const [soloVencidas, setSoloVencidas] = useState(false)
  const [prioridad, setPrioridad] = useState<string | null>(null)

  const resumen = useQuery({
    queryKey: ['tareas', 'resumen'],
    queryFn: () => exigir(api.GET('/api/v1/tareas/resumen')),
  })
  const consulta = {
    solo_abiertas: soloAbiertas, vencidas: soloVencidas, tamano: 100,
    ...(prioridad ? { prioridad: prioridad as Prioridad } : {}),
  }
  const tareas = useQuery({
    queryKey: ['tareas', 'lista', consulta],
    queryFn: () => exigir(api.GET('/api/v1/tareas', { params: { query: consulta } })),
    placeholderData: keepPreviousData,
  })
  const r = resumen.data

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Tareas</Title>
          <Text size="sm" c="dimmed">Lo que hay que hacer, lo urgente primero.</Text>
        </div>
        {puede('alertas.crear') && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setCreando(true)}>Nueva tarea</Button>)}
      </Group>

      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Contador titulo="Abiertas" valor={r?.abiertas} />
        <Contador titulo="Vencidas" valor={r?.vencidas} color="red" />
        <Contador titulo="Vencen hoy" valor={r?.vencen_hoy} color="orange" />
        <Contador titulo="Prioridad alta" valor={r?.alta_prioridad} />
      </SimpleGrid>

      <Group align="flex-end">
        <Select label="Prioridad" w={160} clearable value={prioridad} onChange={(v) => setPrioridad(v === null ? null : String(v))}
          data={Object.entries(NOMBRE_PRIORIDAD).map(([value, label]) => ({ value, label }))} />
        <Switch mb={8} label="Solo abiertas" checked={soloAbiertas}
          onChange={(e) => setSoloAbiertas(e.currentTarget.checked)} />
        <Switch mb={8} label="Solo vencidas" checked={soloVencidas}
          onChange={(e) => setSoloVencidas(e.currentTarget.checked)} />
      </Group>

      {tareas.isPending ? <Center h={120}><Loader color="teal" /></Center> : (
        <Card withBorder padding={0}>
          <Table.ScrollContainer minWidth={820}>
            <Table verticalSpacing="sm" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Tarea</Table.Th><Table.Th>Responsable</Table.Th><Table.Th>Prioridad</Table.Th>
                  <Table.Th>Vence</Table.Th><Table.Th>Estado</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {tareas.data?.items.map((t) => <FilaTarea key={t.id} tarea={t} />)}
                {tareas.data?.items.length === 0 && (
                  <Table.Tr><Table.Td colSpan={5}>
                    <Text size="sm" c="dimmed" ta="center" py="lg">No hay tareas con esos filtros.</Text>
                  </Table.Td></Table.Tr>)}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>)}
      <Text size="sm" c="dimmed">{tareas.data?.total ?? 0} tarea(s)</Text>

      <ModalTarea abierto={creando} cerrar={() => setCreando(false)} />
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

function FilaTarea({ tarea: t }: { tarea: Tarea }) {
  const { puede } = useSesion()
  const cq = useQueryClient()
  const cambiar = useMutation({
    mutationFn: (estado: EstadoTarea) => exigir(api.PATCH('/api/v1/tareas/{tarea_id}', {
      params: { path: { tarea_id: t.id } }, body: { estado },
    })),
    onSuccess: () => cq.invalidateQueries({ queryKey: ['tareas'] }),
    onError: (e) => mostrarError(e, 'No se pudo cambiar la tarea'),
  })
  const cerrada = t.estado === 'hecha' || t.estado === 'cancelada'
  return (
    <Table.Tr style={cerrada ? { opacity: 0.6 } : undefined}>
      <Table.Td>
        <Text size="sm" fw={500}>{t.titulo}</Text>
        {t.descripcion && <Text size="xs" c="dimmed" lineClamp={2}>{t.descripcion}</Text>}
        <Group gap="xs">
          {t.caso_id && <Text size="xs" component={Link} to={`/casos/${t.caso_id}`}>Ver trámite</Text>}
          {t.cliente_id && <Text size="xs" component={Link} to={`/clientes/${t.cliente_id}`}>
            {t.cliente ?? 'Ver cliente'}</Text>}
          {t.origen === 'automatica' && <Badge size="xs" variant="light" color="gray">Automática</Badge>}
        </Group>
      </Table.Td>
      <Table.Td>{t.responsable ?? '—'}</Table.Td>
      <Table.Td><Badge variant="light" color={COLOR_PRIORIDAD[t.prioridad]}>
        {NOMBRE_PRIORIDAD[t.prioridad]}</Badge></Table.Td>
      <Table.Td>
        {formatearFechaHora(t.vence_en)}
        {t.vencida && !cerrada && <Badge ml="xs" size="sm" color="red">Vencida</Badge>}
      </Table.Td>
      <Table.Td>
        {puede('alertas.editar')
          ? <Select w={150} size="xs" allowDeselect={false} value={t.estado} disabled={cambiar.isPending}
              onChange={(v) => v && v !== t.estado && cambiar.mutate(v as EstadoTarea)}
              data={Object.entries(NOMBRE_ESTADO).map(([value, label]) => ({ value, label }))} />
          : NOMBRE_ESTADO[t.estado]}
      </Table.Td>
    </Table.Tr>)
}

function ModalTarea({ abierto, cerrar }: { abierto: boolean; cerrar: () => void }) {
  const cq = useQueryClient()
  const asignables = useAsignables()
  const [titulo, setTitulo] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [prioridad, setPrioridad] = useState<string | null>('media')
  const [responsable, setResponsable] = useState<string | null>(null)
  const [vence, setVence] = useState('')

  const m = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/tareas', {
      body: {
        titulo: titulo.trim(), prioridad: prioridad as Prioridad,
        ...(descripcion.trim() ? { descripcion: descripcion.trim() } : {}),
        ...(responsable ? { responsable_id: Number(responsable) } : {}),
        ...(vence ? { vence_en: aInstanteBogota(vence) } : {}),
      },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', title: 'Tarea creada', message: titulo.trim() })
      cq.invalidateQueries({ queryKey: ['tareas'] })
      setTitulo(''); setDescripcion(''); setVence(''); setResponsable(null); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo crear la tarea'),
  })
  return (
    <Modal opened={abierto} onClose={cerrar} title="Nueva tarea">
      <Stack>
        <TextInput label="Qué hay que hacer" required maxLength={200} value={titulo}
          onChange={(e) => setTitulo(e.currentTarget.value)} />
        <Textarea label="Detalle" value={descripcion} onChange={(e) => setDescripcion(e.currentTarget.value)} />
        <Group grow align="flex-start">
          <Select label="Prioridad" allowDeselect={false} value={prioridad} onChange={(v) => setPrioridad(v === null ? null : String(v))}
            data={Object.entries(NOMBRE_PRIORIDAD).map(([value, label]) => ({ value, label }))} />
          <Select label="Responsable" clearable searchable value={responsable} onChange={(v) => setResponsable(v === null ? null : String(v))}
            placeholder="Yo" data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))} />
        </Group>
        <TextInput label="Vence" type="datetime-local" value={vence}
          description="Hora de Bogotá. Vacío = sin fecha límite" onChange={(e) => setVence(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={m.isPending} disabled={titulo.trim().length < 3} onClick={() => m.mutate()}>
            Crear</Button>
        </Group>
      </Stack>
    </Modal>)
}

