import {
  ActionIcon, Alert, Badge, Button, Card, Center, Fieldset, Group, Loader, Modal, MultiSelect,
  NumberInput, Pagination, Paper, ScrollArea, SegmentedControl, Select, Stack, Switch, Table, Text,
  TextInput, Textarea, Title, Tooltip,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useDebouncedValue } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  IconArrowRight, IconPhoneCall, IconPlus, IconSnowflake, IconTrophy, IconUser,
} from '@tabler/icons-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { aSelect, useAsignables, useCatalogos, type Opcion } from '../lib/catalogos'
import { mostrarError } from '../lib/errores'
import { formatearPesos } from '../lib/formato'

type Oportunidad = Esquemas['OportunidadSalida']
type Paso = Esquemas['PasoEmbudo']

// Cuántos días sin hablarle a un lead empiezan a doler. Sale de la operación:
// una cita consular se consigue en semanas, así que un mes sin contacto es un
// cliente que ya se fue con otro.
const DIAS_FRIO = 30

// Cuántas oportunidades se traen por página. Antes se pedían 200 fijas y nunca
// se miraba cuántas había: pasadas las 200, las tarjetas simplemente no se
// dibujaban y nadie se enteraba. Ahora se pagina y se dice cuántas hay.
const TAMANO = 100

/** Hoy en Bogotá, no en el reloj del navegador: a quien abra la pantalla desde
 *  otro país el calendario no le puede ofrecer un día que acá no ha llegado. */
const hoyEnBogota = () =>
  new Date().toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })

// El día en que llegó el lead, en hora de Bogotá (RN-10): de esa fecha sale
// «cuántos leads trajo la pauta de septiembre», así que tiene que verse.
const diaCorto = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeZone: 'America/Bogota' })
const formatearDia = (iso: string | null | undefined) => (iso ? diaCorto.format(new Date(iso)) : '—')

/** El nombre de una opción de catálogo a partir de su id. */
const nombreDe = (opciones: Opcion[] | undefined, id: number | null | undefined) =>
  (id === null || id === undefined ? null : opciones?.find((o) => o.id === id)?.nombre ?? null)

type Filtros = {
  texto: string
  servicio: string | null
  canal: string | null
  campania: string | null
  asesor: string | null
  estado: string | null
  frias: boolean
  cerradas: boolean
}

const SIN_FILTROS: Filtros = {
  texto: '', servicio: null, canal: null, campania: null, asesor: null,
  estado: null, frias: false, cerradas: false,
}

export function Embudo() {
  const { puede } = useSesion()
  const navegar = useNavigate()
  const clienteQuery = useQueryClient()
  const [vista, setVista] = useState('tablero')
  const [f, setF] = useState<Filtros>(SIN_FILTROS)
  const [pagina, setPagina] = useState(1)
  const [creando, setCreando] = useState(false)
  const [moviendo, setMoviendo] = useState<Oportunidad | null>(null)
  const [contactando, setContactando] = useState<Oportunidad | null>(null)
  const [ganando, setGanando] = useState<Oportunidad | null>(null)

  const catalogos = useCatalogos()
  const asignables = useAsignables()
  const [busqueda] = useDebouncedValue(f.texto, 300)

  // Cambiar un filtro vuelve a la primera página: si no, al afinar la búsqueda
  // la pantalla se queda en la página 7 de un resultado que ahora tiene dos, y
  // se ve vacía como si no hubiera nada.
  const cambiar = (cambio: Partial<Filtros>) => { setF((a) => ({ ...a, ...cambio })); setPagina(1) }

  // Un solo juego de filtros para las dos consultas. El encabezado de cada
  // columna dice cuánta plata hay en ese paso: si el conteo de tarjetas obedece
  // el filtro y el total en pesos no, la pantalla da dos respuestas distintas a
  // la misma pregunta, y la equivocada es la que está en grande.
  const filtros = {
    ...(busqueda ? { texto: busqueda } : {}),
    ...(f.servicio ? { servicio_id: Number(f.servicio) } : {}),
    ...(f.canal ? { canal_id: Number(f.canal) } : {}),
    ...(f.campania ? { campania_id: Number(f.campania) } : {}),
    ...(f.asesor ? { asesor_id: Number(f.asesor) } : {}),
    ...(f.frias ? { frias_desde: DIAS_FRIO } : {}),
  }
  const consulta = {
    ...filtros,
    // El estado recorta la lista. En el tablero el estado ES la columna, así
    // que filtrarlo dejaría las demás columnas vacías con el encabezado
    // contando otra cosa.
    ...(vista === 'lista' && f.estado ? { estado: f.estado } : {}),
    incluir_cerradas: f.cerradas,
    pagina,
    tamano: TAMANO,
  }

  const pasos = useQuery({
    queryKey: ['embudo', filtros],
    queryFn: () => exigir(api.GET('/api/v1/oportunidades/embudo', { params: { query: filtros } })),
    placeholderData: keepPreviousData,
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

  // Las ganadas y las perdidas solo se dibujan si se piden: una oportunidad
  // cerrada desaparecía de la pantalla, y con ella el motivo de la pérdida.
  const columnas = (pasos.data ?? []).filter((p) => f.cerradas || !p.es_cierre)
  const items = oportunidades.data?.items ?? []
  const total = oportunidades.data?.total ?? 0
  const paginas = Math.max(1, Math.ceil(total / TAMANO))
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
        <Group>
          <SegmentedControl value={vista} onChange={(v) => setVista(String(v))} data={[
            { value: 'tablero', label: 'Tablero' }, { value: 'lista', label: 'Lista' }]} />
          {puede('oportunidades.crear') && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setCreando(true)}>
              Nuevo lead
            </Button>)}
        </Group>
      </Group>

      <Group align="flex-end" wrap="wrap" gap="sm">
        <TextInput flex={1} miw={200} maw={280} label="Buscar" placeholder="Cliente o próxima acción"
          value={f.texto} onChange={(e) => cambiar({ texto: e.currentTarget.value })} />
        <Select label="¿Qué le interesa?" data={aSelect(catalogos.data?.servicios)} searchable
          clearable w={170} value={f.servicio}
          onChange={(v) => cambiar({ servicio: v === null ? null : String(v) })} />
        <Select label="Llegó por" data={aSelect(catalogos.data?.canales)} clearable w={150}
          value={f.canal} onChange={(v) => cambiar({ canal: v === null ? null : String(v) })} />
        <Select label="Campaña" data={aSelect(catalogos.data?.campanias)} searchable clearable
          w={170} value={f.campania}
          description="Qué pauta trae clientes"
          onChange={(v) => cambiar({ campania: v === null ? null : String(v) })} />
        <Select label="Asesor" w={160} clearable value={f.asesor}
          onChange={(v) => cambiar({ asesor: v === null ? null : String(v) })}
          data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))} />
        {vista === 'lista' && (
          <Select label="Paso del embudo" w={170} clearable value={f.estado}
            onChange={(v) => cambiar({ estado: v === null ? null : String(v) })}
            data={(pasos.data ?? []).map((p) => ({ value: p.codigo, label: p.nombre }))} />)}
        <Switch mb={8} checked={f.frias} onChange={(e) => cambiar({ frias: e.currentTarget.checked })}
          label={`Solo las frías (más de ${DIAS_FRIO} días sin contacto)`} />
        <Switch mb={8} checked={f.cerradas}
          onChange={(e) => cambiar({ cerradas: e.currentTarget.checked })}
          label="Incluir ganadas y perdidas" />
      </Group>

      {vista === 'tablero' ? (
        <ScrollArea type="auto" offsetScrollbars>
          <Group align="flex-start" wrap="nowrap" gap="sm">
            {columnas.map((paso) => {
              const columna = porEstado(paso.codigo)
              const sinDibujar = paso.cuantas - columna.length
              return (
                <Paper key={paso.codigo} withBorder p="sm" miw={250} w={250} bg="gray.0">
                  <Group justify="space-between" mb={2} wrap="nowrap">
                    <Text size="sm" fw={600} truncate>{paso.nombre}</Text>
                    {/* El conteo viene del embudo y no de las tarjetas cargadas:
                        así el número dice cuántas hay, no cuántas alcanzaron. */}
                    <Badge size="sm" variant="light" color="gray">{paso.cuantas}</Badge>
                  </Group>
                  <Text size="xs" c="dimmed" mb="xs">
                    {paso.valor_estimado > 0
                      ? formatearPesos(paso.valor_estimado) : 'sin valor estimado'}
                  </Text>
                  <Stack gap={6}>
                    {columna.map((o) => (
                      <Tarjeta key={o.id} o={o} abrir={() => navegar(`/clientes/${o.cliente_id}`)}
                        mover={() => setMoviendo(o)} contactar={() => setContactando(o)}
                        ganar={() => setGanando(o)} puedeGanar={puede('negocios.crear')}
                        editable={puede('oportunidades.editar')} />
                    ))}
                    {paso.cuantas === 0 && (
                      <Text size="xs" c="dimmed" ta="center" py="sm">Nada aquí</Text>)}
                    {sinDibujar > 0 && (
                      <Text size="xs" c="orange" ta="center" py={4}>
                        y {sinDibujar} más en las otras páginas
                      </Text>)}
                  </Stack>
                </Paper>)
            })}
          </Group>
        </ScrollArea>
      ) : (
        <Lista items={items} catalogos={catalogos.data} abrir={(o) => navegar(`/clientes/${o.cliente_id}`)}
          mover={setMoviendo} contactar={setContactando} ganar={setGanando}
          puedeGanar={puede('negocios.crear')} editable={puede('oportunidades.editar')} />
      )}

      <Group justify="space-between" align="center">
        <Text size="sm" c="dimmed">
          {total} oportunidad(es){total > items.length && ` · se ven ${items.length} en esta página`}
        </Text>
        {paginas > 1 && (
          <Pagination value={pagina} onChange={setPagina} total={paginas} color="teal" size="sm" />)}
      </Group>

      {total === 0 && (
        <Alert color="gray" variant="light">
          No hay oportunidades con estos filtros. El embudo es donde se ve qué campaña
          trae clientes que compran, que es justo lo que hoy no se puede responder.
        </Alert>)}

      <FormularioLead abierto={creando} cerrar={() => setCreando(false)} creado={refrescar} />
      <ModalMover oportunidad={moviendo} pasos={pasos.data ?? []}
        cerrar={() => setMoviendo(null)} hecho={refrescar} />
      <ModalContacto oportunidad={contactando} cerrar={() => setContactando(null)} hecho={refrescar} />
      {/* La `key` remonta el formulario al cambiar de oportunidad */}
      <ModalGanar key={ganando?.id ?? 'ninguno'} oportunidad={ganando}
        cerrar={() => setGanando(null)} hecho={refrescar} />
    </Stack>
  )
}

/** De dónde salió el cliente, en una línea: el canal, la campaña y quién lo
 *  recomendó. Es la respuesta a «fuente» del RF-010 y la pregunta que hoy no se
 *  puede contestar con los archivos. */
function Origen({ o, catalogos }: { o: Oportunidad; catalogos: Esquemas['Catalogos'] | undefined }) {
  const canal = nombreDe(catalogos?.canales, o.canal_id)
  const campania = nombreDe(catalogos?.campanias, o.campania_id) ?? o.campania
  return (
    <>
      <Text size="sm">{canal ?? 'sin canal'}</Text>
      {campania && <Text size="xs" c="dimmed">{campania}</Text>}
      {o.referido_por && <Text size="xs" c="dimmed">lo recomendó {o.referido_por}</Text>}
    </>)
}

/** La lista filtrable que pide el RF-011. El tablero muestra una tarjeta
 *  recortada por columna; acá se ve de un tirón de dónde salió cada
 *  oportunidad, qué se le prometió y, si se perdió, por qué. */
function Lista({ items, catalogos, abrir, mover, contactar, ganar, puedeGanar, editable }: {
  items: Oportunidad[]
  catalogos: Esquemas['Catalogos'] | undefined
  abrir: (o: Oportunidad) => void
  mover: (o: Oportunidad) => void
  contactar: (o: Oportunidad) => void
  ganar: (o: Oportunidad) => void
  puedeGanar: boolean
  editable: boolean
}) {
  return (
    <Card withBorder padding={0}>
      <Table.ScrollContainer minWidth={1100}>
        <Table verticalSpacing="sm" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Cliente</Table.Th><Table.Th>Llegó</Table.Th><Table.Th>Paso</Table.Th>
              <Table.Th>De dónde salió</Table.Th><Table.Th>Le interesa</Table.Th>
              <Table.Th>Valor estimado</Table.Th><Table.Th>Próxima acción</Table.Th>
              <Table.Th>Sin contacto</Table.Th><Table.Th>Asesor</Table.Th>
              {editable && <Table.Th />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((o) => (
              <Table.Tr key={o.id}>
                <Table.Td>
                  <Text size="sm" fw={500} style={{ cursor: 'pointer' }} onClick={() => abrir(o)}>
                    {o.cliente}
                  </Text>
                </Table.Td>
                {/* Cuándo llegó, no cuándo se digitó: es la fecha con la que se
                    cuentan los leads de una pauta o de un mes. */}
                <Table.Td><Text size="sm">{formatearDia(o.creado_en)}</Text></Table.Td>
                <Table.Td>
                  <Badge variant="light" color={o.es_cierre ? 'gray' : 'teal'}>{o.estado_nombre}</Badge>
                  {/* Lo único que queda de un negocio perdido (RF-015). Sin
                      esto el motivo se guardaba y no se podía leer en ninguna
                      pantalla, así que no cambiaba ninguna decisión. */}
                  {o.motivo_perdida_nombre && (
                    <Text size="xs" c="dimmed" mt={2}>
                      {o.motivo_perdida_nombre}
                      {o.motivo_perdida_nota ? `: ${o.motivo_perdida_nota}` : ''}
                    </Text>)}
                </Table.Td>
                <Table.Td><Origen o={o} catalogos={catalogos} /></Table.Td>
                <Table.Td>
                  <Text size="sm">{nombreDe(catalogos?.servicios, o.servicio_id) ?? '—'}</Text>
                  <Text size="xs" c="dimmed">{nombreDe(catalogos?.paises, o.pais_id) ?? ''}</Text>
                </Table.Td>
                <Table.Td><Text size="sm">{formatearPesos(o.valor_estimado)}</Text></Table.Td>
                <Table.Td>
                  <Text size="sm" c={o.proxima_accion ? undefined : 'orange'}>
                    {o.proxima_accion ?? 'sin próxima acción'}
                  </Text>
                  {o.proxima_accion_fecha && (
                    <Text size="xs" c="dimmed">{o.proxima_accion_fecha}</Text>)}
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c={o.dias_sin_contacto >= DIAS_FRIO ? 'blue' : undefined}>
                    {o.es_cierre ? '—' : `${o.dias_sin_contacto} d`}
                  </Text>
                </Table.Td>
                <Table.Td><Text size="sm">{o.asesor ?? 'sin asesor'}</Text></Table.Td>
                {editable && (
                  <Table.Td>
                    {!o.es_cierre && (
                      <Group gap={2} wrap="nowrap">
                        <Tooltip label="Le hablé hoy">
                          <ActionIcon size="sm" variant="subtle" color="gray"
                            aria-label="Registrar contacto" onClick={() => contactar(o)}>
                            <IconPhoneCall size={13} /></ActionIcon>
                        </Tooltip>
                        <Tooltip label="Mover de paso">
                          <ActionIcon size="sm" variant="subtle" color="gray"
                            aria-label="Mover oportunidad" onClick={() => mover(o)}>
                            <IconArrowRight size={13} /></ActionIcon>
                        </Tooltip>
                        {puedeGanar && (
                          <Tooltip label="Ganada: crear la venta y abrir los trámites">
                            <ActionIcon size="sm" variant="subtle" color="teal"
                              aria-label="Ganar oportunidad" onClick={() => ganar(o)}>
                              <IconTrophy size={13} /></ActionIcon>
                          </Tooltip>)}
                      </Group>)}
                  </Table.Td>)}
              </Table.Tr>
            ))}
            {items.length === 0 && (
              <Table.Tr><Table.Td colSpan={editable ? 10 : 9}>
                <Text size="sm" c="dimmed" ta="center" py="lg">
                  No hay oportunidades con estos filtros.
                </Text>
              </Table.Td></Table.Tr>)}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>)
}

function Tarjeta({ o, abrir, mover, contactar, ganar, puedeGanar, editable }: {
  o: Oportunidad
  abrir: () => void
  mover: () => void
  contactar: () => void
  ganar: () => void
  puedeGanar: boolean
  editable: boolean
}) {
  const frio = o.dias_sin_contacto >= DIAS_FRIO
  return (
    <Card withBorder padding="xs" bg="white">
      <Group gap={4} justify="space-between" wrap="nowrap" mb={2}>
        <Text size="sm" fw={600} truncate style={{ cursor: 'pointer' }} onClick={abrir}>
          {o.cliente}
        </Text>
        {frio && !o.es_cierre && (
          <Tooltip label={`${o.dias_sin_contacto} días sin contacto`}>
            <IconSnowflake size={14} color="var(--mantine-color-blue-5)" />
          </Tooltip>)}
      </Group>
      {o.valor_estimado ? (
        <Text size="xs" c="dimmed">{formatearPesos(o.valor_estimado)}</Text>) : null}
      {o.motivo_perdida_nombre ? (
        <Tooltip label={o.motivo_perdida_nota ?? o.motivo_perdida_nombre} disabled={!o.motivo_perdida_nota}>
          <Text size="xs" c="dimmed" mt={2}>Se perdió: {o.motivo_perdida_nombre}</Text>
        </Tooltip>
      ) : (
        <Text size="xs" c={o.proxima_accion ? undefined : 'orange'} lineClamp={2} mt={2}>
          {o.proxima_accion ?? 'sin próxima acción'}
        </Text>)}
      <Group gap={4} mt={6} justify="space-between" wrap="nowrap">
        <Group gap={3} wrap="nowrap">
          <IconUser size={11} />
          <Text size="xs" c="dimmed" truncate>{o.asesor ?? 'sin asesor'}</Text>
        </Group>
        {editable && !o.es_cierre && (
          <Group gap={2} wrap="nowrap">
            <Tooltip label="Le hablé hoy">
              <ActionIcon size="sm" variant="subtle" color="gray" aria-label="Registrar contacto"
                onClick={contactar}><IconPhoneCall size={13} /></ActionIcon>
            </Tooltip>
            <Tooltip label="Mover de paso">
              <ActionIcon size="sm" variant="subtle" color="gray" aria-label="Mover oportunidad"
                onClick={mover}><IconArrowRight size={13} /></ActionIcon>
            </Tooltip>
            {puedeGanar && (
              <Tooltip label="Ganada: crear la venta y abrir los trámites">
                <ActionIcon size="sm" variant="subtle" color="teal" aria-label="Ganar oportunidad"
                  onClick={ganar}><IconTrophy size={13} /></ActionIcon>
              </Tooltip>)}
          </Group>)}
      </Group>
    </Card>)
}

/** Mover por el embudo. Perder exige motivo del catálogo (RF-015): «no respondió»
 *  y «precio» llevan a decisiones distintas, «se perdió» no lleva a ninguna. */
function ModalMover({ oportunidad, pasos, cerrar, hecho }: {
  oportunidad: Oportunidad | null
  pasos: Paso[]
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

/** Un lead nuevo (RF-010). Exige cliente y próxima acción: sin dueño ni
 *  siguiente paso no está en el embudo, está olvidado.
 *
 *  «De dónde salió» va en su propio recuadro porque es la pregunta que hoy no
 *  se puede responder con los archivos, y la que decide dónde se pone la plata
 *  de publicidad: el canal, la campaña del catálogo y, cuando llegó
 *  recomendado, quién lo recomendó. */
function FormularioLead({ abierto, cerrar, creado }: {
  abierto: boolean; cerrar: () => void; creado: () => void
}) {
  const catalogos = useCatalogos()
  const asignables = useAsignables()
  const [buscado, setBuscado] = useState('')
  const [buscadoPadrino, setBuscadoPadrino] = useState('')
  const clientes = useQuery({
    queryKey: ['clientes-lead', buscado],
    queryFn: () => exigir(api.GET('/api/v1/clientes', {
      params: { query: { texto: buscado || undefined, tamano: 20 } },
    })),
    enabled: abierto,
  })
  const padrinos = useQuery({
    queryKey: ['clientes-recomiendan', buscadoPadrino],
    queryFn: () => exigir(api.GET('/api/v1/clientes', {
      params: { query: { texto: buscadoPadrino || undefined, tamano: 20 } },
    })),
    enabled: abierto,
  })

  const formulario = useForm({
    initialValues: { cliente_id: '', fecha: '', servicio_id: '', pais_id: '', canal_id: '',
                     campania_id: '', campania: '', referido_por_cliente_id: '',
                     asesor_id: '', valor_estimado: '', proxima_accion: 'Llamar para calificar' },
    validate: {
      cliente_id: (v) => (v ? null : 'Elija de qué cliente es'),
      proxima_accion: (v) => (v.trim().length >= 3 ? null : 'Escriba cuál es el siguiente paso'),
      fecha: (v) => (!v || v <= hoyEnBogota() ? null : 'Un lead no puede haber llegado mañana'),
    },
  })

  const crear = useMutation({
    mutationFn: (v: typeof formulario.values) => exigir(api.POST('/api/v1/oportunidades', {
      body: {
        cliente_id: Number(v.cliente_id),
        fecha: v.fecha || null,
        servicio_id: v.servicio_id ? Number(v.servicio_id) : null,
        pais_id: v.pais_id ? Number(v.pais_id) : null,
        canal_id: v.canal_id ? Number(v.canal_id) : null,
        campania_id: v.campania_id ? Number(v.campania_id) : null,
        campania: v.campania || null,
        referido_por_cliente_id: v.referido_por_cliente_id
          ? Number(v.referido_por_cliente_id) : null,
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
            {/* La fecha se captura, no se asigna: un lead transcrito de la hoja
                de pauta llegó el día que llegó, no el día que se digitó. */}
            <TextInput label="¿Cuándo llegó?" type="date" max={hoyEnBogota()}
              description="Vacío: hoy. Se escribe al transcribir la hoja de pauta"
              {...formulario.getInputProps('fecha')} />
            <Select label="¿Qué le interesa?" data={aSelect(catalogos.data?.servicios)} searchable
              clearable {...formulario.getInputProps('servicio_id')} />
          </Group>
          <Select label="País" data={aSelect(catalogos.data?.paises)} searchable clearable
            {...formulario.getInputProps('pais_id')} />

          <Fieldset legend="De dónde salió" variant="filled">
            <Stack gap="sm">
              <Group grow>
                <Select label="¿Por dónde llegó?" data={aSelect(catalogos.data?.canales)} clearable
                  {...formulario.getInputProps('canal_id')} />
                <Select label="Campaña o influencer" searchable clearable
                  data={aSelect(catalogos.data?.campanias)}
                  description="Del catálogo, para poder sumarla después"
                  {...formulario.getInputProps('campania_id')} />
              </Group>
              <Select label="¿Quién lo recomendó?" searchable clearable
                placeholder="Busque por nombre"
                description="La recomendación es el canal que más vende"
                data={(padrinos.data?.items ?? []).map((c) => ({ value: String(c.id), label: c.nombre }))}
                searchValue={buscadoPadrino} onSearchChange={setBuscadoPadrino}
                nothingFoundMessage="Sin resultados"
                {...formulario.getInputProps('referido_por_cliente_id')} />
              <TextInput label="Si la campaña no está en el catálogo"
                placeholder="Reel de septiembre" {...formulario.getInputProps('campania')} />
            </Stack>
          </Fieldset>

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


/** Ganar la oportunidad: se crea la venta y se abre un trámite por cada persona
 *  que viaja, sin volver a digitar nada (RF-014). El precio sale del catálogo
 *  según cuántos viajan, y se puede negociar encima. */
function ModalGanar({ oportunidad, cerrar, hecho }: {
  oportunidad: Oportunidad | null; cerrar: () => void; hecho: () => void
}) {
  const catalogos = useCatalogos()
  const [servicio, setServicio] = useState<string | null>(
    oportunidad?.servicio_id ? String(oportunidad.servicio_id) : null)
  const [elegidos, setElegidos] = useState<string[]>([])
  const [negociado, setNegociado] = useState<number | string>('')
  const [observaciones, setObservaciones] = useState('')

  const personas = useQuery({
    queryKey: ['solicitantes-venta', oportunidad?.cliente_id],
    queryFn: () => exigir(api.GET('/api/v1/solicitantes', {
      params: { query: { cliente_id: oportunidad!.cliente_id } },
    })),
    enabled: oportunidad !== null,
  })
  const viajan = elegidos.length || personas.data?.length || 1

  const cotizacion = useQuery({
    queryKey: ['cotizar', servicio, viajan, negociado],
    queryFn: () => exigir(api.POST('/api/v1/cotizar', {
      body: {
        servicio_id: Number(servicio), personas: viajan, descuento: 0,
        ...(negociado ? { valor_pactado: Number(negociado) } : {}),
      },
    })),
    enabled: oportunidad !== null && servicio !== null,
  })

  const ganar = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/oportunidades/{oportunidad_id}/ganar', {
      params: { path: { oportunidad_id: oportunidad!.id } },
      body: {
        descuento: 0, abrir_tramites: true,
        ...(servicio ? { servicio_id: Number(servicio) } : {}),
        ...(elegidos.length ? { solicitantes_ids: elegidos.map(Number) } : {}),
        ...(negociado ? { valor_pactado: Number(negociado) } : {}),
        ...(observaciones ? { observaciones } : {}),
      },
    })),
    onSuccess: (venta) => {
      notifications.show({
        color: 'teal', title: 'Venta creada',
        message: `Se abrieron ${venta.casos.length} trámite(s) sin volver a digitar nada.`,
      })
      hecho(); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo cerrar la venta'),
  })

  const c = cotizacion.data

  return (
    <Modal opened={oportunidad !== null} onClose={cerrar} size="lg"
      title={`Cerrar la venta de ${oportunidad?.cliente ?? ''}`}>
      <Stack>
        <Select label="¿Qué se vendió?" data={aSelect(catalogos.data?.servicios)} searchable
          value={servicio} onChange={(v) => setServicio(v === null ? null : String(v))}
          data-autofocus />
        <MultiSelect label="¿Quiénes viajan?" searchable
          description="Si no elige a nadie, se abre un trámite para todas las personas del cliente"
          data={(personas.data ?? []).map((s) => ({ value: String(s.id), label: s.nombre }))}
          value={elegidos} onChange={setElegidos} />

        {c && (
          <Card withBorder padding="sm" bg="gray.0">
            <Group justify="space-between">
              <Text size="sm">Precio de lista para {c.personas} persona(s)</Text>
              <Text size="sm" fw={600}>{formatearPesos(c.valor_lista)}</Text>
            </Group>
            {c.descuento > 0 && (
              <Group justify="space-between">
                <Text size="sm" c="dimmed">Descuento</Text>
                <Text size="sm" c="dimmed">- {formatearPesos(c.descuento)}</Text>
              </Group>)}
            <Group justify="space-between" mt={4}>
              <Text size="sm" fw={600}>Valor pactado</Text>
              <Text size="sm" fw={700} c="teal.8">{formatearPesos(c.valor_pactado)}</Text>
            </Group>
            {c.avisos.map((a) => (
              <Text key={a} size="xs" c="dimmed" mt={6}>{a}</Text>))}
          </Card>)}

        <NumberInput label="Precio negociado" thousandSeparator="." decimalSeparator=","
          prefix="$ " allowNegative={false} value={negociado} onChange={(v) => setNegociado(typeof v === 'bigint' ? Number(v) : v)}
          description="Déjelo vacío para cobrar el de lista" />
        <TextInput label="Observaciones" value={observaciones}
          placeholder="Descuento por ser referida"
          onChange={(e) => setObservaciones(e.currentTarget.value)} />

        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={ganar.isPending} disabled={!servicio} onClick={() => ganar.mutate()}>
            Cerrar la venta
          </Button>
        </Group>
      </Stack>
    </Modal>)
}
