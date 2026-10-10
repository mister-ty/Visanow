import {
  Alert, Badge, Card, Center, Code, Group, Loader, Pagination, Select, Stack, Table, Text,
  TextInput, Title,
} from '@mantine/core'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, exigir, type Esquemas } from '../api/cliente'
import { formatearFechaHora } from '../lib/formato'

type Registro = Esquemas['RegistroSalida']

const COLOR_OPERACION: Record<string, string> = {
  insert: 'teal', update: 'blue', delete: 'red', login: 'gray',
  login_fallido: 'orange', anonimizar: 'grape', eliminar: 'red', exportar: 'yellow',
}

/** `clientes` → `Clientes`, y `alertas_tipos` → `Alertas tipos`. */
const bonito = (s: string) =>
  (s.charAt(0).toUpperCase() + s.slice(1)).replace(/_/g, ' ')

/**
 * Quién hizo qué, cuándo y sobre qué registro (RF-076).
 *
 * La auditoría se escribía desde el primer día y nadie podía leerla. Toda la
 * política de datos dice «el día que un archivo con clientes aparezca donde no
 * debía, se mira quién lo sacó»; hasta ahora eso significaba entrar a la base
 * de datos.
 *
 * Lo que no muestra, porque no está guardado, es el dato personal en sí: anota
 * que cambió el teléfono de un cliente, no cuál era. La tabla es inalterable
 * (RNF-05), así que lo que entrara ahí sobreviviría a cualquier anonimización
 * posterior (RNF-09).
 */
export function Auditoria() {
  const [entidad, setEntidad] = useState<string | null>(null)
  const [operacion, setOperacion] = useState<string | null>(null)
  const [registro, setRegistro] = useState('')
  const [pagina, setPagina] = useState(1)

  const filtros = useQuery({
    queryKey: ['auditoria', 'filtros'],
    queryFn: () => exigir(api.GET('/api/v1/auditoria/filtros')),
    staleTime: 5 * 60 * 1000,
  })

  const datos = useQuery({
    queryKey: ['auditoria', entidad, operacion, registro, pagina],
    queryFn: () => exigir(api.GET('/api/v1/auditoria', {
      params: {
        query: {
          entidad: entidad ?? undefined,
          operacion: operacion ?? undefined,
          entidad_id: registro ? Number(registro) : undefined,
          pagina, tamano: 50,
        },
      },
    })),
    placeholderData: keepPreviousData,
  })

  const cambiar = (fn: () => void) => { fn(); setPagina(1) }
  const paginas = Math.ceil((datos.data?.total ?? 0) / 50)

  return (
    <Stack>
      <div>
        <Title order={2}>Auditoría</Title>
        <Text size="sm" c="dimmed">Quién hizo qué, cuándo y desde dónde. No se puede modificar.</Text>
      </div>

      <Alert color="blue" variant="light">
        El registro anota <b>qué campo</b> cambió, no el dato. Si a un cliente le cambiaron
        el teléfono, acá dice que se cambió el teléfono y quién lo hizo; el teléfono está en
        la ficha del cliente, que es donde debe estar. Se guarda así a propósito: esta tabla
        no se puede borrar, y si llevara los datos personales adentro, anonimizar a una
        persona no la anonimizaría.
      </Alert>

      <Group align="flex-end">
        <Select label="Sobre qué" placeholder="Todo" clearable w={200}
          data={(filtros.data?.entidades ?? []).map((e) => ({ value: e, label: bonito(e) }))}
          value={entidad} onChange={(v) => cambiar(() => setEntidad(v))} />
        <Select label="Operación" placeholder="Todas" clearable w={180}
          data={(filtros.data?.operaciones ?? []).map((o) => ({ value: o, label: bonito(o) }))}
          value={operacion} onChange={(v) => cambiar(() => setOperacion(v))} />
        <TextInput label="N.º de registro" placeholder="p. ej. 418" w={160}
          description="Para seguir un cliente o un trámite concreto"
          value={registro} onChange={(e) => cambiar(() => setRegistro(e.currentTarget.value))} />
        <Text size="sm" c="dimmed" pb={6}>
          {datos.data ? `${datos.data.total.toLocaleString('es-CO')} registro(s)` : ''}
        </Text>
      </Group>

      {datos.isPending
        ? <Center h={200}><Loader color="teal" /></Center>
        : (
          <Card withBorder padding={0}>
            <Table.ScrollContainer minWidth={900}>
              <Table verticalSpacing="sm" highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Cuándo</Table.Th><Table.Th>Quién</Table.Th>
                    <Table.Th>Qué hizo</Table.Th><Table.Th>Sobre</Table.Th>
                    <Table.Th>Qué cambió</Table.Th><Table.Th>Desde</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {datos.data?.items.map((r: Registro) => (
                    <Table.Tr key={r.id}>
                      <Table.Td><Text size="sm">{formatearFechaHora(r.ocurrido_en)}</Text></Table.Td>
                      <Table.Td>
                        <Text size="sm">{r.usuario ?? <Text span c="dimmed">el sistema</Text>}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge variant="light" color={COLOR_OPERACION[r.operacion] ?? 'gray'}>
                          {bonito(r.operacion)}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{bonito(r.entidad)}</Text>
                        {r.entidad_id !== null && (
                          <Text size="xs" c="dimmed">n.º {r.entidad_id}</Text>)}
                      </Table.Td>
                      <Table.Td>
                        <Group gap={4} wrap="wrap">
                          {r.campos.length === 0 && <Text size="sm" c="dimmed">—</Text>}
                          {/* `title` del navegador y no <Tooltip>: una pagina de 50
                              filas con seis campos cada una son 300 tooltips, cada
                              uno con su portal, y React termina tumbando la tabla
                              al redibujarla ("removeChild ... is not a child"). El
                              atributo nativo dice lo mismo sin montar nada. */}
                          {r.campos.slice(0, 6).map((c) => (
                            <Code key={c} title={detalle(r, c)}>{c}</Code>))}
                          {r.campos.length > 6 && (
                            <Text size="xs" c="dimmed">y {r.campos.length - 6} más</Text>)}
                        </Group>
                      </Table.Td>
                      <Table.Td><Text size="xs" c="dimmed">{r.ip ?? '—'}</Text></Table.Td>
                    </Table.Tr>))}
                  {datos.data?.items.length === 0 && (
                    <Table.Tr><Table.Td colSpan={6}>
                      <Center h={100}><Text c="dimmed">No hay registros con esos filtros.</Text></Center>
                    </Table.Td></Table.Tr>)}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>)}

      {paginas > 1 && (
        <Group justify="center">
          <Pagination total={paginas} value={pagina} onChange={setPagina} color="teal" />
        </Group>)}
    </Stack>
  )
}

/** Lo que se guardó de ese campo, para el globo de ayuda. */
function detalle(r: Registro, campo: string): string {
  const antes = (r.antes as Record<string, unknown> | null)?.[campo]
  const despues = (r.despues as Record<string, unknown> | null)?.[campo]
  const texto = (v: unknown) =>
    v === undefined || v === null ? 'vacío' : typeof v === 'object' ? JSON.stringify(v) : String(v)
  if (r.antes && r.despues) return `${campo}: ${texto(antes)} → ${texto(despues)}`
  return `${campo}: ${texto(despues ?? antes)}`
}
