import {
  Alert, Badge, Button, Card, Center, FileInput, Group, Loader, Modal, SimpleGrid, Stack, Table, Tabs,
  Text, TextInput, Title,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { IconUpload } from '@tabler/icons-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { leerExcelSaas } from '../lib/excelSaas'
import { mostrarError } from '../lib/errores'
import { formatearFechaHora } from '../lib/formato'

type Importacion = Esquemas['ImportacionSalida']
type Resultado = Esquemas['FilaSalida']['resultado']
type Fila = Esquemas['FilaSalida']

const RESULTADOS: Resultado[] = ['nuevo', 'actualizado', 'sin_cambio', 'conflicto', 'rechazado']
const NOMBRE_RESULTADO: Record<Resultado, string> = {
  nuevo: 'Nuevos', actualizado: 'Actualizados', sin_cambio: 'Sin cambio', conflicto: 'Conflictos', rechazado: 'Rechazados',
}
const COLOR_RESULTADO: Record<Resultado, string> = {
  nuevo: 'blue', actualizado: 'teal', sin_cambio: 'gray', conflicto: 'orange', rechazado: 'red',
}
const CUENTA: Record<Resultado, keyof Importacion> = {
  nuevo: 'nuevos', actualizado: 'actualizados', sin_cambio: 'sin_cambios', conflicto: 'conflictos', rechazado: 'rechazados',
}
const NOMBRE_ESTADO: Record<Importacion['estado'], string> = {
  previsualizada: 'Por aplicar', aplicada: 'Aplicada', descartada: 'Descartada', fallida: 'Fallida',
}

/** Importación del consolidado del SaaS (RF-032, RF-033, RF-036). Siempre en
 *  dos pasos —previsualizar y luego aplicar—: importar a ciegas sobre datos de
 *  clientes reales no se puede deshacer. */
export function ImportacionSaas() {
  const { puede } = useSesion()
  const [abierta, setAbierta] = useState<number | null>(null)
  const estado = useQuery({
    queryKey: ['saas', 'estado'],
    queryFn: () => exigir(api.GET('/api/v1/saas/estado')),
  })
  const conflictos = useQuery({
    queryKey: ['saas', 'conflictos'],
    queryFn: () => exigir(api.GET('/api/v1/saas/conflictos')),
  })
  const e = estado.data
  return (
    <Stack>
      <div>
        <Title order={2}>Importación del SaaS</Title>
        <Text size="sm" c="dimmed">Traer el consolidado de solicitudes y cuadrarlo con los trámites de VisaNow.</Text>
      </div>
      {e && (
        <Alert color={e.resultado === 'ok' ? 'teal' : 'orange'} variant="light">
          {e.ultima_exitosa
            ? `Última sincronización exitosa: ${formatearFechaHora(e.ultima_exitosa)}`
              + (e.horas_desde_la_ultima_exitosa !== null ? ` (hace ${Math.round(e.horas_desde_la_ultima_exitosa)} h).` : '.')
            : 'Todavía no hay una sincronización exitosa.'}
          {e.resultado === 'error' && e.detalle ? ` Último intento con error: ${e.detalle}` : ''}
        </Alert>)}
      <Tabs defaultValue={puede('importacion.crear') ? 'importar' : 'historial'} keepMounted={false}>
        <Tabs.List>
          {puede('importacion.crear') && <Tabs.Tab value="importar">Importar archivo</Tabs.Tab>}
          <Tabs.Tab value="historial">Historial</Tabs.Tab>
          <Tabs.Tab value="conflictos"
            rightSection={conflictos.data?.length ? <Badge size="sm" color="orange">{conflictos.data.length}</Badge> : null}>
            Conflictos
          </Tabs.Tab>
        </Tabs.List>
        {puede('importacion.crear') && (
          <Tabs.Panel value="importar" pt="md"><Subir abrir={setAbierta} /></Tabs.Panel>)}
        <Tabs.Panel value="historial" pt="md"><Historial abrir={setAbierta} /></Tabs.Panel>
        <Tabs.Panel value="conflictos" pt="md"><Conflictos /></Tabs.Panel>
      </Tabs>
      <ModalImportacion id={abierta} cerrar={() => setAbierta(null)} />
    </Stack>
  )
}

function Subir({ abrir }: { abrir: (id: number) => void }) {
  const cq = useQueryClient()
  const [archivo, setArchivo] = useState<File | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const m = useMutation({
    mutationFn: async (f: File) => {
      const { filas, faltantes } = await leerExcelSaas(f)
      if (faltantes.includes('N° Solicitud') || filas.length === 0) {
        throw new Error(filas.length === 0
          ? 'El archivo no tiene filas para importar.'
          : 'No encuentro la columna «N° Solicitud», que es la llave de cada fila.')
      }
      setAviso(faltantes.length ? `Al archivo le faltan estas columnas: ${faltantes.join(', ')}.` : null)
      return exigir(api.POST('/api/v1/saas/previsualizar', { body: { filas, archivo: f.name } }))
    },
    onSuccess: (imp) => {
      cq.invalidateQueries({ queryKey: ['saas'] })
      setArchivo(null); abrir(imp.id)
    },
    onError: (e) => (e instanceof Error && e.constructor === Error
      ? notifications.show({ color: 'red', title: 'No se pudo leer el archivo', message: e.message })
      : mostrarError(e, 'No se pudo previsualizar')),
  })
  return (
    <Card withBorder maw={560}>
      <Stack>
        <Text size="sm">
          Suba el Excel del SaaS. Se lee en este navegador y solo se envían las filas. Todavía no cambia
          nada: primero verá qué pasaría con cada solicitud.
        </Text>
        <FileInput label="Archivo del SaaS" placeholder="Elegir .xlsx" accept=".xlsx,.xls" clearable
          leftSection={<IconUpload size={16} />} value={archivo} onChange={setArchivo} />
        {aviso && <Alert color="yellow" variant="light">{aviso}</Alert>}
        <Group justify="flex-end">
          <Button disabled={!archivo} loading={m.isPending} onClick={() => archivo && m.mutate(archivo)}>
            Previsualizar</Button>
        </Group>
      </Stack>
    </Card>)
}

function Historial({ abrir }: { abrir: (id: number) => void }) {
  const lista = useQuery({
    queryKey: ['saas', 'importaciones'],
    queryFn: () => exigir(api.GET('/api/v1/saas/importaciones', { params: { query: { limite: 30 } } })),
  })
  if (lista.isPending) return <Center h={120}><Loader color="teal" /></Center>
  return (
    <Card withBorder padding={0}>
      <Table.ScrollContainer minWidth={760}>
        <Table verticalSpacing="sm" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Cuándo</Table.Th><Table.Th>Archivo</Table.Th><Table.Th>Filas</Table.Th>
              <Table.Th>Resultado</Table.Th><Table.Th>Estado</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {lista.data?.map((i) => (
              <Table.Tr key={i.id} style={{ cursor: 'pointer' }} onClick={() => abrir(i.id)}>
                <Table.Td>{formatearFechaHora(i.iniciada_en)}</Table.Td>
                <Table.Td>{i.archivo_nombre ?? '—'}</Table.Td>
                <Table.Td>{i.filas_totales}</Table.Td>
                <Table.Td>
                  <Text size="sm">{i.nuevos} nuevos · {i.actualizados} actualizados · {i.sin_cambios} sin cambio</Text>
                  <Text size="xs" c="dimmed">{i.conflictos} conflictos · {i.rechazados} rechazados</Text>
                </Table.Td>
                <Table.Td><Badge variant="light" color={i.estado === 'fallida' ? 'red' : i.estado === 'aplicada' ? 'teal' : 'gray'}>
                  {NOMBRE_ESTADO[i.estado]}</Badge></Table.Td>
              </Table.Tr>))}
            {lista.data?.length === 0 && (
              <Table.Tr><Table.Td colSpan={5}>
                <Text size="sm" c="dimmed" ta="center" py="lg">Todavía no se ha importado ningún archivo.</Text>
              </Table.Td></Table.Tr>)}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>)
}

/** Una importación con el detalle de cada fila, por categoría. */
function ModalImportacion({ id, cerrar }: { id: number | null; cerrar: () => void }) {
  const { puede } = useSesion()
  const cq = useQueryClient()
  const [filtro, setFiltro] = useState<Resultado | null>(null)
  const [vinculando, setVinculando] = useState<Fila | null>(null)

  const imp = useQuery({
    queryKey: ['saas', 'importacion', id, filtro],
    queryFn: () => exigir(api.GET('/api/v1/saas/importaciones/{importacion_id}', {
      params: { path: { importacion_id: id! }, query: filtro ? { resultado: filtro } : {} },
    })),
    enabled: id !== null,
  })
  const terminar = () => cq.invalidateQueries({ queryKey: ['saas'] })
  const aplicar = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/saas/importaciones/{importacion_id}/aplicar', {
      params: { path: { importacion_id: id! } },
    })),
    onSuccess: (r) => {
      notifications.show({
        color: 'teal', title: 'Importación aplicada',
        message: `${r.actualizados} actualizado(s), ${r.conflictos} conflicto(s) por resolver y ${r.por_vincular} solicitud(es) por vincular a mano.`,
      })
      terminar()
    },
    onError: (e) => mostrarError(e, 'No se pudo aplicar'),
  })
  const descartar = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/saas/importaciones/{importacion_id}/descartar', {
      params: { path: { importacion_id: id! } },
    })),
    onSuccess: () => { notifications.show({ color: 'teal', title: 'Importación descartada', message: 'No se cambió ningún trámite.' }); terminar() },
    onError: (e) => mostrarError(e, 'No se pudo descartar'),
  })
  const confirmarAplicar = () => modals.openConfirmModal({
    title: 'Aplicar la importación',
    children: <Text size="sm">Se actualizarán los trámites que ya están vinculados. Esto no se puede deshacer en bloque.</Text>,
    labels: { confirm: 'Aplicar', cancel: 'Cancelar' },
    onConfirm: () => aplicar.mutate(),
  })

  const d = imp.data
  const porAplicar = d?.estado === 'previsualizada' && puede('importacion.crear')
  return (
    <Modal opened={id !== null} onClose={() => { setFiltro(null); cerrar() }} size="xl"
      title={d ? `Importación ${d.archivo_nombre ?? '#' + d.id}` : 'Importación'}>
      {imp.isPending && <Center h={120}><Loader color="teal" /></Center>}
      {d && (
        <Stack>
          <Group justify="space-between">
            <Text size="sm" c="dimmed">{formatearFechaHora(d.iniciada_en)} · {d.filas_totales} fila(s) · {NOMBRE_ESTADO[d.estado]}</Text>
            {porAplicar && (
              <Group>
                <Button variant="default" loading={descartar.isPending} onClick={() => descartar.mutate()}>Descartar</Button>
                <Button loading={aplicar.isPending} onClick={confirmarAplicar}>Aplicar</Button>
              </Group>)}
          </Group>
          {d.estado === 'previsualizada' && (
            <Alert color="blue" variant="light">Esto es solo una vista previa: ningún trámite ha cambiado.</Alert>)}
          <SimpleGrid cols={{ base: 2, sm: 5 }}>
            {RESULTADOS.map((r) => (
              <Card key={r} withBorder padding="sm" style={{
                cursor: 'pointer', borderColor: r === filtro ? 'var(--mantine-color-teal-6)' : undefined,
              }} onClick={() => setFiltro(r === filtro ? null : r)}>
                <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{NOMBRE_RESULTADO[r]}</Text>
                <Text size="xl" fw={700}>{String(d[CUENTA[r]])}</Text>
              </Card>))}
          </SimpleGrid>
          <Table.ScrollContainer minWidth={640} mah={420}>
            <Table verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr><Table.Th>Fila</Table.Th><Table.Th>Solicitud</Table.Th><Table.Th>Resultado</Table.Th><Table.Th>Detalle</Table.Th><Table.Th /></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {d.filas.map((f) => (
                  <Table.Tr key={f.fila_numero}>
                    <Table.Td>{f.fila_numero}</Table.Td>
                    <Table.Td>{f.id_externo ?? '—'}</Table.Td>
                    <Table.Td><Badge variant="light" color={COLOR_RESULTADO[f.resultado]}>{NOMBRE_RESULTADO[f.resultado]}</Badge></Table.Td>
                    <Table.Td><Text size="sm">{f.detalle ?? '—'}</Text>
                      {f.caso_id && <Text size="xs" component={Link} to={`/casos/${f.caso_id}`}>Ver trámite</Text>}</Table.Td>
                    <Table.Td>
                      {f.resultado === 'nuevo' && f.id_externo && !f.caso_id && puede('importacion.crear') && (
                        <Button size="compact-sm" variant="default" onClick={() => setVinculando(f)}>Vincular</Button>)}
                    </Table.Td>
                  </Table.Tr>))}
                {d.filas.length === 0 && (
                  <Table.Tr><Table.Td colSpan={5}><Text size="sm" c="dimmed" ta="center" py="md">Sin filas en esta categoría.</Text></Table.Td></Table.Tr>)}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Stack>)}
      <ModalVincular key={vinculando?.fila_numero ?? 'ninguna'} fila={vinculando} cerrar={() => setVinculando(null)} />
    </Modal>)
}

/** Las filas «nuevo» no crean el trámite solas: el export no dice de forma
 *  confiable de qué persona es. Una persona reconoce el trámite y lo amarra. */
function ModalVincular({ fila, cerrar }: { fila: Fila | null; cerrar: () => void }) {
  const cq = useQueryClient()
  const [nombre, setNombre] = useState('')
  const [buscar, setBuscar] = useState('')
  const numero = fila?.id_externo ?? ''
  const candidatos = useQuery({
    queryKey: ['saas', 'candidatos', numero, buscar],
    queryFn: () => exigir(api.GET('/api/v1/saas/candidatos', {
      params: { query: { numero_solicitud: numero, ...(buscar ? { nombre: buscar } : {}) } },
    })),
    enabled: fila !== null,
  })
  const m = useMutation({
    mutationFn: (caso_id: number) => exigir(api.POST('/api/v1/saas/vincular', {
      body: { caso_id, numero_solicitud: numero },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', title: 'Trámite vinculado', message: 'Las próximas importaciones lo actualizan solas.' })
      cq.invalidateQueries({ queryKey: ['saas'] }); cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo vincular'),
  })
  return (
    <Modal opened={fila !== null} onClose={cerrar} title={`Vincular la solicitud ${numero}`}>
      <Stack>
        <Group align="flex-end" wrap="nowrap">
          <TextInput style={{ flex: 1 }} label="Buscar por nombre" value={nombre}
            onChange={(e) => setNombre(e.currentTarget.value)} onKeyDown={(e) => e.key === 'Enter' && setBuscar(nombre.trim())} />
          <Button variant="default" onClick={() => setBuscar(nombre.trim())}>Buscar</Button>
        </Group>
        {candidatos.isPending && <Center h={60}><Loader color="teal" size="sm" /></Center>}
        <Table>
          <Table.Tbody>
            {candidatos.data?.map((c) => (
              <Table.Tr key={c.caso_id}>
                <Table.Td>{c.solicitante}<Text size="xs" c="dimmed">Trámite #{c.caso_id} · {c.fuente}</Text></Table.Td>
                <Table.Td ta="right">
                  <Button size="compact-sm" loading={m.isPending} onClick={() => m.mutate(c.caso_id)}>Vincular</Button>
                </Table.Td>
              </Table.Tr>))}
            {candidatos.data?.length === 0 && (
              <Table.Tr><Table.Td><Text size="sm" c="dimmed">Ningún trámite parece corresponder. Pruebe con otro nombre.</Text></Table.Td></Table.Tr>)}
          </Table.Tbody>
        </Table>
        <Text size="xs" c="dimmed">El sistema sugiere; usted decide de quién es la solicitud.</Text>
      </Stack>
    </Modal>)
}

/** Dos valores distintos para el mismo campo: el sistema no decide solo. */
function Conflictos() {
  const { puede } = useSesion()
  const cq = useQueryClient()
  const lista = useQuery({
    queryKey: ['saas', 'conflictos'],
    queryFn: () => exigir(api.GET('/api/v1/saas/conflictos')),
  })
  const resolver = useMutation({
    mutationFn: (a: { id: number; decision: 'resuelto_visanow' | 'resuelto_saas' | 'ignorado' }) =>
      exigir(api.POST('/api/v1/saas/conflictos/{conflicto_id}/resolver', {
        params: { path: { conflicto_id: a.id } }, body: { decision: a.decision },
      })),
    onSuccess: () => cq.invalidateQueries({ queryKey: ['saas'] }),
    onError: (e) => mostrarError(e, 'No se pudo resolver'),
  })
  if (lista.isPending) return <Center h={120}><Loader color="teal" /></Center>
  return (
    <Card withBorder padding={0}>
      <Table.ScrollContainer minWidth={760}>
        <Table verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Trámite</Table.Th><Table.Th>Campo</Table.Th><Table.Th>VisaNow dice</Table.Th>
              <Table.Th>El SaaS dice</Table.Th><Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {lista.data?.map((c) => (
              <Table.Tr key={c.id}>
                <Table.Td>{c.caso_id
                  ? <Text size="sm" component={Link} to={`/casos/${c.caso_id}`}>#{c.caso_id}</Text> : '—'}
                  <Text size="xs" c="dimmed">{formatearFechaHora(c.detectado_en)}</Text></Table.Td>
                <Table.Td>{c.campo}</Table.Td>
                <Table.Td>{c.valor_visanow ?? '—'}</Table.Td>
                <Table.Td>{c.valor_saas ?? '—'}</Table.Td>
                <Table.Td>
                  {puede('importacion.crear') && (
                    <Group gap="xs" justify="flex-end" wrap="nowrap">
                      <Button size="compact-sm" variant="default" disabled={resolver.isPending}
                        onClick={() => resolver.mutate({ id: c.id, decision: 'resuelto_visanow' })}>Gana VisaNow</Button>
                      <Button size="compact-sm" disabled={resolver.isPending}
                        onClick={() => resolver.mutate({ id: c.id, decision: 'resuelto_saas' })}>Gana el SaaS</Button>
                      <Button size="compact-sm" variant="subtle" color="gray" disabled={resolver.isPending}
                        onClick={() => resolver.mutate({ id: c.id, decision: 'ignorado' })}>Ignorar</Button>
                    </Group>)}
                </Table.Td>
              </Table.Tr>))}
            {lista.data?.length === 0 && (
              <Table.Tr><Table.Td colSpan={5}>
                <Text size="sm" c="dimmed" ta="center" py="lg">No hay conflictos por resolver.</Text>
              </Table.Td></Table.Tr>)}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>)
}
