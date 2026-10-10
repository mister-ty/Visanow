import {
  ActionIcon, Button, Card, Checkbox, Group, Modal, Pagination, Select, Stack, Table, Text,
  TextInput, Title,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useForm } from '@mantine/form'
import { notifications } from '@mantine/notifications'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconPlus, IconSearch, IconX } from '@tabler/icons-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, exigir } from '../api/cliente'
import { BotonExportar } from '../componentes/BotonExportar'
import { useSesion } from '../auth/sesion'
import { AvisoDuplicados } from '../componentes/AvisoDuplicados'
import { aSelect, useCatalogos } from '../lib/catalogos'
import { mostrarError } from '../lib/errores'

const TAMANO = 25

export function Clientes() {
  const { puede } = useSesion()
  const navegar = useNavigate()
  const [texto, setTexto] = useState('')
  const [busqueda] = useDebouncedValue(texto, 300)
  const [archivados, setArchivados] = useState(false)
  const [pagina, setPagina] = useState(1)
  const [creando, setCreando] = useState(false)

  const clientes = useQuery({
    queryKey: ['clientes', busqueda, archivados, pagina],
    queryFn: () => exigir(api.GET('/api/v1/clientes', {
      params: { query: { texto: busqueda || undefined, archivados, pagina, tamano: TAMANO } },
    })),
    placeholderData: keepPreviousData,
  })

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Clientes</Title>
        <Group gap="xs">
          <BotonExportar lista="clientes" permiso="clientes.exportar"
            filtros={{ texto: busqueda || undefined, archivados }} />
          {puede('clientes.crear') && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setCreando(true)}>Nuevo cliente</Button>
          )}
        </Group>
      </Group>

      <Group align="flex-end">
        <TextInput flex={1} maw={420} label="Buscar" placeholder="Nombre, documento, teléfono o correo"
          leftSection={<IconSearch size={16} />} value={texto}
          onChange={(e) => { setTexto(e.currentTarget.value); setPagina(1) }}
          rightSection={texto && (
            <ActionIcon variant="subtle" color="gray" onClick={() => setTexto('')} aria-label="Limpiar">
              <IconX size={14} />
            </ActionIcon>)} />
        <Checkbox label="Incluir archivados" checked={archivados} mb={6}
          onChange={(e) => { setArchivados(e.currentTarget.checked); setPagina(1) }} />
      </Group>

      <Card withBorder padding={0}>
        <Table.ScrollContainer minWidth={700}>
          <Table verticalSpacing="sm" highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Nombre</Table.Th><Table.Th>Documento</Table.Th><Table.Th>Teléfono</Table.Th>
                <Table.Th>Correo</Table.Th><Table.Th>Ciudad</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {clientes.data?.items.map((c) => (
                <Table.Tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => navegar(`/clientes/${c.id}`)}>
                  <Table.Td>
                    <Text size="sm" fw={500} c={c.archivado ? 'dimmed' : undefined}>
                      {c.nombre}{c.archivado && ' (archivado)'}
                    </Text>
                  </Table.Td>
                  <Table.Td><Text size="sm">{c.numero_documento ?? '—'}</Text></Table.Td>
                  <Table.Td><Text size="sm">{c.telefono ?? '—'}</Text></Table.Td>
                  <Table.Td><Text size="sm">{c.email ?? '—'}</Text></Table.Td>
                  <Table.Td><Text size="sm">{c.ciudad ?? '—'}</Text></Table.Td>
                </Table.Tr>
              ))}
              {clientes.data?.items.length === 0 && (
                <Table.Tr><Table.Td colSpan={5}>
                  <Text size="sm" c="dimmed" ta="center" py="lg">
                    {busqueda ? `No hay clientes que coincidan con «${busqueda}».` : 'Todavía no hay clientes.'}
                  </Text>
                </Table.Td></Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>

      <Group justify="space-between">
        <Text size="sm" c="dimmed">{clientes.data?.total ?? 0} cliente(s)</Text>
        {(clientes.data?.total ?? 0) > TAMANO && (
          <Pagination value={pagina} onChange={setPagina}
            total={Math.ceil((clientes.data?.total ?? 0) / TAMANO)} size="sm" />
        )}
      </Group>

      <FormularioCliente abierto={creando} cerrar={() => setCreando(false)} />
    </Stack>
  )
}


function FormularioCliente({ abierto, cerrar }: { abierto: boolean; cerrar: () => void }) {
  const clienteQuery = useQueryClient()
  const navegar = useNavigate()
  const formulario = useForm({
    initialValues: { nombre: '', tipo_documento: '', numero_documento: '', telefono: '', email: '',
                     ciudad: '', consentimiento: false, pais_id: '', canal_id: '' },
    validate: { nombre: (v) => (v.trim().length >= 2 ? null : 'Escriba el nombre completo') },
  })
  const [datos] = useDebouncedValue(formulario.values, 400)
  const [confirmado, setConfirmado] = useState(false)

  // Se buscan parecidos mientras se escribe: avisar antes de guardar evita la
  // ficha repetida, que después hay que fusionar a mano.
  const posibles = useQuery({
    queryKey: ['duplicados-nuevo', datos.nombre, datos.numero_documento, datos.telefono, datos.email],
    queryFn: () => exigir(api.POST('/api/v1/clientes/verificar-duplicados', {
      body: { nombre: datos.nombre, numero_documento: datos.numero_documento || undefined,
              telefono: datos.telefono || undefined, email: datos.email || undefined },
    })),
    enabled: abierto && datos.nombre.trim().length >= 3,
  })
  const hayFuerte = (posibles.data ?? []).some((c) => c.confianza === 'alta')
  const catalogos = useCatalogos()

  const crear = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.POST('/api/v1/clientes', {
      body: {
        ...Object.fromEntries(Object.entries(v).filter(([, x]) => x !== '')),
        nombre: v.nombre, consentimiento: v.consentimiento,
        // Los desplegables devuelven texto; la API espera el id numérico
        ...(v.pais_id ? { pais_id: Number(v.pais_id) } : {}),
        ...(v.canal_id ? { canal_id: Number(v.canal_id) } : {}),
      } as never,
    })),
    onSuccess: (c) => {
      notifications.show({ color: 'teal', message: 'Cliente creado' })
      clienteQuery.invalidateQueries({ queryKey: ['clientes'] })
      formulario.reset(); setConfirmado(false); cerrar()
      navegar(`/clientes/${c.id}`)
    },
    onError: (e) => mostrarError(e, 'No se pudo crear'),
  })

  return (
    <Modal opened={abierto} onClose={cerrar} title="Nuevo cliente" size="lg">
      <form onSubmit={formulario.onSubmit((v) => crear.mutate(v))}>
        <Stack>
          <TextInput label="Nombre completo" data-autofocus {...formulario.getInputProps('nombre')} />
          <Group grow>
            <TextInput label="Tipo de documento" placeholder="CC, CE, PA" {...formulario.getInputProps('tipo_documento')} />
            <TextInput label="Número de documento" {...formulario.getInputProps('numero_documento')} />
          </Group>
          <Group grow>
            <TextInput label="Teléfono" placeholder="3105177800" {...formulario.getInputProps('telefono')} />
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
          <Checkbox label="Autorizó el tratamiento de sus datos personales"
            {...formulario.getInputProps('consentimiento', { type: 'checkbox' })} />

          <AvisoDuplicados coincidencias={posibles.data} cargando={posibles.isFetching} />
          {hayFuerte && (
            <Checkbox color="red" checked={confirmado} onChange={(e) => setConfirmado(e.currentTarget.checked)}
              label="Revisé las fichas parecidas y confirmo que es una persona distinta" />
          )}

          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={crear.isPending} disabled={hayFuerte && !confirmado}>Crear</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
