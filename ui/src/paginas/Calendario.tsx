import {
  ActionIcon, Badge, Button, Card, Center, Group, Loader, SegmentedControl, Select, Stack,
  Switch, Text, Title, Tooltip,
} from '@mantine/core'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'
import { aSelect, useAsignables, useCatalogos } from '../lib/catalogos'

type Cita = Esquemas['CitaAgenda']

/**
 * La agenda: qué hay mañana (RF-024).
 *
 * Una cita solo se veía abriendo el trámite al que pertenece. Eso contesta
 * «¿cuándo es la cita de Ana?» y no contesta la pregunta con la que se arma el
 * día. Saber si el jueves había tres entrevistas significaba abrir los trámites
 * de uno en uno, así que la agenda seguía viviendo en la cabeza de alguien y el
 * sistema no servía para repartir el trabajo.
 *
 * Las horas son de Bogotá de punta a punta. El servidor corre en UTC y una cita
 * de las 7 de la noche acá ya es del día siguiente en UTC: por eso el backend
 * filtra por día de Bogotá y acá se muestra igual (RN-10).
 */

const DIAS = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom']

const COLOR_TIPO: Record<string, string> = {
  cas: 'blue', entrevista: 'teal', biometria: 'violet', entrega: 'orange',
}

const COLOR_ESTADO: Record<string, string> = {
  pendiente: 'orange', programada: 'blue', confirmada: 'teal',
  reprogramada: 'yellow', realizada: 'gray', cancelada: 'red',
}

/** aaaa-mm-dd de una fecha local, sin pasar por UTC (que correría el día). */
const iso = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** El lunes de la semana de esa fecha. */
function lunesDe(d: Date): Date {
  const x = new Date(d)
  const desplazamiento = (x.getDay() + 6) % 7      // domingo = 6, no 0
  x.setDate(x.getDate() - desplazamiento)
  x.setHours(0, 0, 0, 0)
  return x
}

const sumarDias = (d: Date, n: number): Date => {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

const horaDe = (instante: string): string =>
  new Date(instante).toLocaleTimeString('es-CO', {
    hour: '2-digit', minute: '2-digit', timeZone: 'America/Bogota',
  })

export function Calendario() {
  const navegar = useNavigate()
  const catalogos = useCatalogos()
  const asignables = useAsignables()

  const [ancla, setAncla] = useState(() => new Date())
  const [vista, setVista] = useState<'semana' | 'mes'>('semana')
  const [responsable, setResponsable] = useState<string | null>(null)
  const [sede, setSede] = useState<string | null>(null)
  const [conCanceladas, setConCanceladas] = useState(false)

  // La semana arranca el lunes; el «mes» son cuatro semanas desde ese lunes,
  // que es lo que de verdad se mira para repartir trabajo —nadie planea el 31
  // mirando el 1—.
  const inicio = lunesDe(ancla)
  const dias = vista === 'semana' ? 7 : 28
  const fin = sumarDias(inicio, dias - 1)

  const consulta = {
    desde: iso(inicio), hasta: iso(fin),
    ...(responsable ? { responsable_id: Number(responsable) } : {}),
    ...(sede ? { sede_id: Number(sede) } : {}),
    ...(conCanceladas ? { incluir_canceladas: true } : {}),
  }
  const agenda = useQuery({
    queryKey: ['agenda', consulta],
    queryFn: () => exigir(api.GET('/api/v1/agenda', { params: { query: consulta } })),
    placeholderData: keepPreviousData,
  })

  const porDia = new Map<string, Cita[]>()
  for (const c of agenda.data ?? []) {
    // Se agrupa por el día de BOGOTÁ, no por el del navegador: si alguien abre
    // esto desde otro huso, la cita tiene que seguir cayendo en el día en que
    // es para la agencia.
    const dia = new Date(c.inicia_en).toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })
    const lista = porDia.get(dia) ?? []
    lista.push(c)
    porDia.set(dia, lista)
  }

  const hoy = iso(new Date())
  const titulo = inicio.toLocaleDateString('es-CO', { month: 'long', year: 'numeric' })

  return (
    <Stack>
      <Group justify="space-between" wrap="wrap">
        <div>
          <Title order={2}>Calendario</Title>
          <Text size="sm" c="dimmed">Las citas de todos los trámites, para armar el día.</Text>
        </div>
        <Group gap="xs">
          <SegmentedControl size="sm" value={vista}
            onChange={(v) => setVista(v as 'semana' | 'mes')}
            data={[{ value: 'semana', label: 'Semana' }, { value: 'mes', label: '4 semanas' }]} />
          <ActionIcon variant="default" aria-label="Anterior"
            onClick={() => setAncla(sumarDias(inicio, -dias))}>
            <IconChevronLeft size={16} />
          </ActionIcon>
          <Button size="compact-sm" variant="default" onClick={() => setAncla(new Date())}>
            Hoy
          </Button>
          <ActionIcon variant="default" aria-label="Siguiente"
            onClick={() => setAncla(sumarDias(inicio, dias))}>
            <IconChevronRight size={16} />
          </ActionIcon>
        </Group>
      </Group>

      <Card withBorder padding="sm">
        <Group grow align="end">
          <Select label="Responsable" placeholder="Todos" clearable searchable
            data={(asignables.data ?? []).map((u) => ({ value: String(u.id), label: u.nombre }))}
            value={responsable} onChange={(v) => setResponsable(v === null ? null : String(v))} />
          <Select label="Sede" placeholder="Todas" clearable searchable
            data={aSelect(catalogos.data?.sedes)} value={sede} onChange={(v) => setSede(v === null ? null : String(v))} />
          <Switch label="Mostrar canceladas" checked={conCanceladas}
            description="Una cita cancelada no se borra: queda para saber que se perdió el cupo"
            onChange={(e) => setConCanceladas(e.currentTarget.checked)} />
        </Group>
      </Card>

      <Text size="sm" fw={600} tt="capitalize">{titulo}</Text>

      {agenda.isPending ? (
        <Center h={200}><Loader color="teal" /></Center>
      ) : (
        <Stack gap="xs">
          {Array.from({ length: dias / 7 }, (_, semana) => (
            <Group key={semana} grow align="stretch" gap="xs" wrap="nowrap">
              {Array.from({ length: 7 }, (_, i) => {
                const dia = sumarDias(inicio, semana * 7 + i)
                const clave = iso(dia)
                const citas = porDia.get(clave) ?? []
                const esHoy = clave === hoy
                return (
                  <Card key={clave} withBorder padding="xs"
                    bg={esHoy ? 'teal.0' : undefined}
                    style={{ minHeight: 110, flex: 1 }}>
                    <Group gap={4} justify="space-between" mb={4} wrap="nowrap">
                      <Text size="xs" c="dimmed">{DIAS[i]}</Text>
                      <Text size="sm" fw={esHoy ? 700 : 500} c={esHoy ? 'teal' : undefined}>
                        {dia.getDate()}
                      </Text>
                    </Group>
                    <Stack gap={4}>
                      {citas.map((c) => (
                        <Tooltip key={c.id} withArrow multiline w={280}
                          label={`${c.solicitante} · ${c.tipo} · ${c.estado}`
                                 + (c.pais ? ` · ${c.pais}` : '')
                                 + (c.responsable ? ` · ${c.responsable}` : '')}>
                          <Card withBorder padding={4} radius="sm"
                            style={{ cursor: 'pointer' }}
                            onClick={() => navegar('/casos/' + c.caso_id)}>
                            <Group gap={4} wrap="nowrap">
                              <Badge size="xs" variant="light"
                                color={COLOR_ESTADO[c.estado] ?? COLOR_TIPO[c.tipo] ?? 'gray'}>
                                {horaDe(c.inicia_en)}
                              </Badge>
                            </Group>
                            <Text size="xs" lineClamp={1}>{c.solicitante}</Text>
                          </Card>
                        </Tooltip>
                      ))}
                    </Stack>
                  </Card>
                )
              })}
            </Group>
          ))}
        </Stack>
      )}

      <Text size="sm" c="dimmed">
        {(agenda.data ?? []).length} cita(s) entre el {inicio.getDate()} y el {fin.getDate()}
      </Text>
    </Stack>
  )
}
