import {
  ActionIcon, Alert, Badge, Button, Card, Center, Group, Loader, Modal, NumberInput, Paper,
  ScrollArea, Select, Stack, Switch, Text, TextInput, Textarea, Title, Tooltip,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { notifications } from '@mantine/notifications'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  IconArrowRight, IconPhoneCall, IconPlus, IconSnowflake, IconUser,
} from '@tabler/icons-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { aSelect, useAsignables, useCatalogos } from '../lib/catalogos'
import { mostrarError } from '../lib/errores'
import { formatearPesos } from '../lib/formato'

type Oportunidad = Esquemas['OportunidadSalida']

// Cuántos días sin hablarle a un lead empiezan a doler. Sale de la operación:
// una cita consular se consigue en semanas, así que un mes sin contacto es un
// cliente que ya se fue con otro.
const DIAS_FRIO = 30

export function Embudo() {
  const { puede } = useSesion()
  const navegar = useNavigate()
  const clienteQuery = useQueryClient()
  const [soloFrias, setSoloFrias] = useState(false)
  const [canal, setCanal] = useState<string | null>(null)
  const [asesor, setAsesor] = useState<string | null>(null)
  const [texto, setTexto] = useState('')
  const [creando, setCreando] = useState(false)
  const [moviendo, setMoviendo] = useState<Oportunidad | null>(null)
  const [contactando, setContactando] = useState<Oportunidad | null>(null)

  const catalogos = useCatalogos()
  const asignables = useAsignables()

  const consulta = {
    ...(soloFrias ? { frias_desde: DIAS_FRIO } : {}),
    ...(canal ? { canal_id: Number(canal) } : {}),
    ...(asesor ? { asesor_id: Number(asesor) } : {}),
    ...(texto ? { texto } : {}),
    tamano: 200,
  }

  const pasos = useQuery({
    queryKey: ['embudo'],
    queryFn: () => exigir(api.GET('/api/v1/oportunidades/embudo')),
  })
  const oportunidades = useQuery({
    queryKey: ['oportunidades', consulta],
    queryFn: () => exigir(api.GET('/api/v1/oportunidades', { params: { query: consulta } })),
    placeholderData: keepPreviousData,
  })
  const refrescar = () => {
    clienteQuery.invalidateQueries({ queryKey: ['oportunidades'] })
    clienteQuery.invalidateQueries({ queryKey: ['embudo'] })
  }

  if (pasos.isPending) return <Center h={200}><Loader color="teal" /></Center>
  if (pasos.isError) return <Alert color="red">No se pudo abrir el embudo. {String(pasos.error)}</Alert>

  const abiertos = (pasos.data ?? []).filter((p) => !p.es_cierre)
  const items = oportunidades.data?.items ?? []
  const porEstado = (codigo: string) => items.filter((o) => o.estado === codigo)

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Embudo comercial</Title>
          <Text size="sm" c="dimmed">
            De dónde sale cada cliente y en qué paso se está quedando.
          </Text>
        </div>
        {puede('oportunidades.crear') && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setCreando(true)}>
            Nuevo lead
          </Button>)}
      </Group>

      <Group align="flex-end" wrap="wrap">
        <TextInput flex={1} maw={300} label="Buscar" placeholder="Cliente o próxima acción"
          value={texto} onChange={(e) => setTexto(e.currentTarget.value)} />
        <Select label="Llegó por" data={aSelect(catalogos.data?.canales)} clearable w={180}
          value={canal} onChange={(v) => setCanal(v === null ? null : String(v))} />
        <Select label="Asesor" w={180} clearable value={asesor}
          onChange={(v) => setAsesor(v === null ? null : String(v))}
          data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))} />
        <Switch mb={8} checked={soloFrias} onChange={(e) => setSoloFrias(e.currentTarget.checked)}
          label={`Solo las frías (más de ${DIAS_FRIO} días sin contacto)`} />
      </Group>

      <ScrollArea type="auto" offsetScrollbars>
        <Group align="flex-start" wrap="nowrap" gap="sm">
          {abiertos.map((paso) => {
            const columna = porEstado(paso.codigo)
            return (
              <Paper key={paso.codigo} withBorder p="sm" miw={250} w={250} bg="gray.0">
                <Group justify="space-between" mb={2} wrap="nowrap">
                  <Text size="sm" fw={600} truncate>{paso.nombre}</Text>
                  <Badge size="sm" variant="light" color="gray">{columna.length}</Badge>
                </Group>
                <Text size="xs" c="dimmed" mb="xs">
                  {paso.valor_estimado > 0 ? formatearPesos(paso.valor_estimado) : 'sin valor estimado'}
                </Text>
                <Stack gap={6}>
                  {columna.map((o) => (
                    <Tarjeta key={o.id} o={o} abrir={() => navegar(`/clientes/${o.cliente_id}`)}
                      mover={() => setMoviendo(o)} contactar={() => setContactando(o)}
                      editable={puede('oportunidades.editar')} />
                  ))}
                  {columna.length === 0 && (
                    <Text size="xs" c="dimmed" ta="center" py="sm">Nada aquí</Text>)}
                </Stack>
              </Paper>)
          })}
        </Group>
      </ScrollArea>

      {items.length === 0 && (
        <Alert color="gray" variant="light">
          No hay oportunidades abiertas con estos filtros. El embudo es donde se ve qué campaña
          trae clientes que compran, que es justo lo que hoy no se puede responder.
        </Alert>)}

      <FormularioLead abierto={creando} cerrar={() => setCreando(false)} creado={refrescar} />
      <ModalMover oportunidad={moviendo} pasos={pasos.data ?? []}
        cerrar={() => setMoviendo(null)} hecho={refrescar} />
      <ModalContacto oportunidad={contactando} cerrar={() => setContactando(null)} hecho={refrescar} />
    </Stack>
  )
}

function Tarjeta({ o, abrir, mover, contactar, editable }: {
  o: Oportunidad; abrir: () => void; mover: () => void; contactar: () => void; editable: boolean
}) {
  const frio = o.dias_sin_contacto >= DIAS_FRIO
  return (
    <Card withBorder padding="xs" bg="white">
      <Group gap={4} justify="space-between" wrap="nowrap" mb={2}>
        <Text size="sm" fw={600} truncate style={{ cursor: 'pointer' }} onClick={abrir}>
          {o.cliente}
        </Text>
        {frio && (
          <Tooltip label={`${o.dias_sin_contacto} días sin contacto`}>
            <IconSnowflake size={14} color="var(--mantine-color-blue-5)" />
          </Tooltip>)}
      </Group>
      {o.valor_estimado ? (
        <Text size="xs" c="dimmed">{formatearPesos(o.valor_estimado)}</Text>) : null}
      <Text size="xs" c={o.proxima_accion ? undefined : 'orange'} lineClamp={2} mt={2}>
        {o.proxima_accion ?? 'sin próxima acción'}
      </Text>
      <Group gap={4} mt={6} justify="space-between" wrap="nowrap">
        <Group gap={3} wrap="nowrap">
          <IconUser size={11} />
          <Text size="xs" c="dimmed" truncate>{o.asesor ?? 'sin asesor'}</Text>
        </Group>
        {editable && (
          <Group gap={2} wrap="nowrap">
            <Tooltip label="Le hablé hoy">
              <ActionIcon size="sm" variant="subtle" color="gray" aria-label="Registrar contacto"
                onClick={contactar}><IconPhoneCall size={13} /></ActionIcon>
            </Tooltip>
            <Tooltip label="Mover de paso">
              <ActionIcon size="sm" variant="subtle" color="teal" aria-label="Mover oportunidad"
                onClick={mover}><IconArrowRight size={13} /></ActionIcon>
            </Tooltip>
          </Group>)}
      </Group>
    </Card>)
}

/** Mover por el embudo. Perder exige motivo del catálogo (RF-015): «no respondió»
 *  y «precio» llevan a decisiones distintas, «se perdió» no lleva a ninguna. */
function ModalMover({ oportunidad, pasos, cerrar, hecho }: {
  oportunidad: Oportunidad | null
  pasos: Esquemas['PasoEmbudo'][]
  cerrar: () => void
  hecho: () => void
}) {
  const catalogos = useCatalogos()
  const [destino, setDestino] = useState<string | null>(null)
  const [motivo, setMotivo] = useState<string | null>(null)
  const [nota, setNota] = useState('')
  const [proxima, setProxima] = useState('')

  const paso = pasos.find((p) => p.codigo === destino)
  const pide_motivo = paso?.codigo === 'perdido'
  const sigue_abierta = paso !== undefined && !paso.es_cierre

  const mover = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/oportunidades/{oportunidad_id}/estado', {
      params: { path: { oportunidad_id: oportunidad!.id } },
      body: {
        codigo_destino: destino!,
        motivo_perdida: pide_motivo ? (motivo ?? undefined) : undefined,
        nota: nota || undefined,
        proxima_accion: proxima || undefined,
      },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Oportunidad movida' })
      setDestino(null); setMotivo(null); setNota(''); setProxima('')
      hecho(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo mover'),
  })

  const motivos = (catalogos.data?.motivos_perdida ?? [])
    .map((m) => ({ value: m.codigo ?? String(m.id), label: m.nombre }))

  return (
    <Modal opened={oportunidad !== null} onClose={cerrar}
      title={`Mover la oportunidad de ${oportunidad?.cliente ?? ''}`}>
      <Stack>
        <Select label="¿A qué paso?" data-autofocus allowDeselect={false}
          data={pasos.map((p) => ({ value: p.codigo, label: p.nombre }))}
          value={destino} onChange={(v) => setDestino(v === null ? null : String(v))} />
        {pide_motivo && (
          <>
            <Select label="¿Por qué se perdió?" data={motivos} value={motivo}
              onChange={(v) => setMotivo(v === null ? null : String(v))}
              description="«No respondió» y «precio» llevan a decisiones distintas" />
            <Textarea label="Detalle" autosize minRows={2} value={nota}
              onChange={(e) => setNota(e.currentTarget.value)} />
          </>)}
        {sigue_abierta && (
          <TextInput label="Próxima acción" value={proxima}
            placeholder={oportunidad?.proxima_accion ?? 'Qué sigue'}
            description="Una oportunidad abierta siempre tiene un siguiente paso"
            onChange={(e) => setProxima(e.currentTarget.value)} />)}
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={mover.isPending} disabled={!destino} onClick={() => mover.mutate()}>
            Mover
          </Button>
        </Group>
      </Stack>
    </Modal>)
}

function ModalContacto({ oportunidad, cerrar, hecho }: {
  oportunidad: Oportunidad | null; cerrar: () => void; hecho: () => void
}) {
  const [proxima, setProxima] = useState('')
  const registrar = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/oportunidades/{oportunidad_id}/contacto', {
      params: { path: { oportunidad_id: oportunidad!.id } },
      body: { proxima_accion: proxima || undefined },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Contacto registrado' })
      setProxima(''); hecho(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo registrar'),
  })
  return (
    <Modal opened={oportunidad !== null} onClose={cerrar}
      title={`Hablé con ${oportunidad?.cliente ?? ''}`}>
      <Stack>
        <Text size="sm" c="dimmed">
          Queda la fecha de hoy como último contacto, y sale de la lista de leads fríos.
        </Text>
        <TextInput label="¿Qué sigue?" data-autofocus value={proxima}
          placeholder={oportunidad?.proxima_accion ?? 'Mandar la cotización el lunes'}
          onChange={(e) => setProxima(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={registrar.isPending} onClick={() => registrar.mutate()}>Registrar</Button>
        </Group>
      </Stack>
    </Modal>)
}

/** Un lead nuevo. Exige cliente y próxima acción: sin dueño ni siguiente paso no
 *  está en el embudo, está olvidado. */
function FormularioLead({ abierto, cerrar, creado }: {
  abierto: boolean; cerrar: () => void; creado: () => void
}) {
  const catalogos = useCatalogos()
  const asignables = useAsignables()
  const [buscado, setBuscado] = useState('')
  const clientes = useQuery({
    queryKey: ['clientes-lead', buscado],
    queryFn: () => exigir(api.GET('/api/v1/clientes', {
      params: { query: { texto: buscado || undefined, tamano: 20 } },
    })),
    enabled: abierto,
  })

  const formulario = useForm({
    initialValues: { cliente_id: '', servicio_id: '', pais_id: '', canal_id: '', campania: '',
                     asesor_id: '', valor_estimado: '', proxima_accion: 'Llamar para calificar' },
    validate: {
      cliente_id: (v) => (v ? null : 'Elija de qué cliente es'),
      proxima_accion: (v) => (v.trim().length >= 3 ? null : 'Escriba cuál es el siguiente paso'),
    },
  })

  const crear = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.POST('/api/v1/oportunidades', {
      body: {
        cliente_id: Number(v.cliente_id),
        servicio_id: v.servicio_id ? Number(v.servicio_id) : null,
        pais_id: v.pais_id ? Number(v.pais_id) : null,
        canal_id: v.canal_id ? Number(v.canal_id) : null,
        campania: v.campania || null,
        asesor_id: v.asesor_id ? Number(v.asesor_id) : null,
        valor_estimado: v.valor_estimado ? Number(v.valor_estimado) : null,
        proxima_accion: v.proxima_accion,
      },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Lead creado' })
      formulario.reset(); creado(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo crear el lead'),
  })

  return (
    <Modal opened={abierto} onClose={cerrar} title="Nuevo lead" size="lg">
      <form onSubmit={formulario.onSubmit((v) => crear.mutate(v))}>
        <Stack>
          <Select label="Cliente" searchable data-autofocus
            placeholder="Busque por nombre"
            data={(clientes.data?.items ?? []).map((c) => ({ value: String(c.id), label: c.nombre }))}
            searchValue={buscado} onSearchChange={setBuscado}
            nothingFoundMessage="Cree primero el cliente desde Clientes"
            {...formulario.getInputProps('cliente_id')} />
          <Group grow>
            <Select label="¿Qué le interesa?" data={aSelect(catalogos.data?.servicios)} searchable
              clearable {...formulario.getInputProps('servicio_id')} />
            <Select label="País" data={aSelect(catalogos.data?.paises)} searchable clearable
              {...formulario.getInputProps('pais_id')} />
          </Group>
          <Group grow>
            <Select label="¿Por dónde llegó?" data={aSelect(catalogos.data?.canales)} clearable
              {...formulario.getInputProps('canal_id')} />
            <TextInput label="Campaña o influencer" placeholder="Reel de septiembre"
              {...formulario.getInputProps('campania')} />
          </Group>
          <Group grow>
            <Select label="Asesor" clearable
              description="Si se deja vacío queda a su nombre"
              data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))}
              {...formulario.getInputProps('asesor_id')} />
            <NumberInput label="Valor estimado" thousandSeparator="." decimalSeparator=","
              prefix="$ " allowNegative={false} {...formulario.getInputProps('valor_estimado')} />
          </Group>
          <TextInput label="Próxima acción" {...formulario.getInputProps('proxima_accion')} />
          <Group justify="flex-end">
            <Button variant="default" onClick={cerrar}>Cancelar</Button>
            <Button type="submit" loading={crear.isPending}>Crear lead</Button>
          </Group>
        </Stack>
      </form>
    </Modal>)
}
