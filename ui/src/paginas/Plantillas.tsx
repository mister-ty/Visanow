import {
  Alert, Badge, Button, Center, Code, Group, Loader, Modal, Select, Stack, Switch, Table, Text,
  TextInput, Textarea, Title,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconPlus } from '@tabler/icons-react'
import { useState } from 'react'
import { api, exigir, type Esquemas } from '../api/cliente'
import { mostrarError } from '../lib/errores'

type Plantilla = Esquemas['PlantillaSalida']
const CANALES = [
  { value: 'whatsapp', label: 'WhatsApp' }, { value: 'correo', label: 'Correo' },
  { value: 'sms', label: 'SMS' },
]

export function Plantillas() {
  const [editando, setEditando] = useState<Plantilla | 'nueva' | null>(null)
  const catalogo = useQuery({
    queryKey: ['plantillas-catalogo'],
    queryFn: () => exigir(api.GET('/api/v1/plantillas/catalogo')),
    staleTime: Infinity,
  })
  const lista = useQuery({
    queryKey: ['plantillas', 'todas'],
    queryFn: () => exigir(api.GET('/api/v1/plantillas', { params: { query: { incluir_inactivas: true } } })),
  })
  if (lista.isPending || catalogo.isPending) return <Center h={200}><Loader color="teal" /></Center>
  if (lista.isError || catalogo.isError) return <Alert color="red">No se pudieron cargar las plantillas.</Alert>
  const evento = (c: string) => catalogo.data.eventos.find((e) => e.clave === c)?.nombre ?? c

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Plantillas de mensajes</Title>
          <Text size="sm" c="dimmed">
            Un texto por evento, con variables que el sistema llena. Se usan desde la ficha del trámite.
          </Text>
        </div>
        <Button leftSection={<IconPlus size={16} />} onClick={() => setEditando('nueva')}>Nueva plantilla</Button>
      </Group>
      <Table.ScrollContainer minWidth={560}>
        <Table striped>
          <Table.Thead>
            <Table.Tr><Table.Th>Evento</Table.Th><Table.Th>Nombre</Table.Th><Table.Th>Canal</Table.Th>
              <Table.Th>Estado</Table.Th><Table.Th /></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {lista.data.map((p) => (
              <Table.Tr key={p.id}>
                <Table.Td>{evento(p.evento)}</Table.Td>
                <Table.Td>{p.nombre}</Table.Td>
                <Table.Td>{p.canal}</Table.Td>
                <Table.Td><Badge variant="light" color={p.activa ? 'teal' : 'gray'}>
                  {p.activa ? 'Activa' : 'Inactiva'}</Badge></Table.Td>
                <Table.Td><Button size="xs" variant="subtle" onClick={() => setEditando(p)}>Editar</Button></Table.Td>
              </Table.Tr>))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {/* La `key` remonta el formulario al cambiar de plantilla */}
      <FormularioPlantilla key={editando === null ? 'ninguna' : editando === 'nueva' ? 'nueva' : editando.id}
        editando={editando} cerrar={() => setEditando(null)}
        eventos={catalogo.data.eventos} variables={catalogo.data.variables} />
    </Stack>
  )
}

function FormularioPlantilla({ editando, cerrar, eventos, variables }: {
  editando: Plantilla | 'nueva' | null
  cerrar: () => void
  eventos: Esquemas['EventoSalida'][]
  variables: Esquemas['VariableSalida'][]
}) {
  const clienteQuery = useQueryClient()
  const existente = editando && editando !== 'nueva' ? editando : null
  const form = useForm({
    initialValues: {
      evento: existente?.evento ?? '', nombre: existente?.nombre ?? '',
      canal: existente?.canal ?? 'whatsapp', asunto: existente?.asunto ?? '',
      cuerpo: existente?.cuerpo ?? '', activa: existente?.activa ?? true,
    },
    validate: {
      evento: (v) => (v ? null : 'Elija el evento'),
      nombre: (v) => (v.trim().length >= 3 ? null : 'Mínimo 3 letras'),
      cuerpo: (v) => (v.trim() ? null : 'El mensaje no puede estar vacío'),
    },
  })
  const guardar = useMutation({
    mutationFn: (v: typeof form.values) => existente
      ? exigir(api.PATCH('/api/v1/plantillas/{plantilla_id}', {
        params: { path: { plantilla_id: existente.id } },
        body: { nombre: v.nombre, asunto: v.asunto || null, cuerpo: v.cuerpo, activa: v.activa } }))
      : exigir(api.POST('/api/v1/plantillas', { body: {
        evento: v.evento, nombre: v.nombre, canal: v.canal as 'whatsapp' | 'correo' | 'sms',
        asunto: v.asunto || null, cuerpo: v.cuerpo } })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Plantilla guardada' })
      clienteQuery.invalidateQueries({ queryKey: ['plantillas'] })
      cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo guardar'),
  })

  return (
    <Modal opened={editando !== null} onClose={cerrar} size="lg"
      title={existente ? 'Editar plantilla' : 'Nueva plantilla'}>
      <form onSubmit={form.onSubmit((v) => guardar.mutate(v))}>
        <Stack>
          <Select label="Evento" data={eventos.map((e) => ({ value: e.clave, label: e.nombre }))}
            disabled={!!existente} {...form.getInputProps('evento')} />
          <TextInput label="Nombre" {...form.getInputProps('nombre')} />
          <Select label="Canal" data={CANALES} allowDeselect={false} disabled={!!existente}
            {...form.getInputProps('canal')} />
          {form.values.canal === 'correo' && <TextInput label="Asunto" {...form.getInputProps('asunto')} />}
          <Textarea label="Mensaje" autosize minRows={5} {...form.getInputProps('cuerpo')} />
          <Text size="xs" c="dimmed">
            Variables: {variables.map((v) => <Code key={v.clave} mr={4} title={v.descripcion}>{`{{${v.clave}}}`}</Code>)}
          </Text>
          {existente && <Switch label="Activa" {...form.getInputProps('activa', { type: 'checkbox' })} />}
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={guardar.isPending}>Guardar</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
