import { Anchor, Badge, Card, Group, SimpleGrid, Stack, Text, ThemeIcon, Timeline, Title } from '@mantine/core'
import { IconBell, IconCheck, IconShieldCheck, IconShieldX } from '@tabler/icons-react'
import { Link } from 'react-router-dom'
import { useSesion } from '../auth/sesion'
import { formatearFechaHora, NOMBRES_ROL } from '../lib/formato'
import { SECCIONES } from '../navegacion'

/** «Mi trabajo». Cuando existan las tareas y alertas (actividad 5.4) aquí va la
 *  bandeja del día; mientras tanto muestra la cuenta y qué está llegando. */
export function Inicio() {
  const { yo, puede } = useSesion()
  if (!yo) return null
  const primerNombre = yo.nombre.split(' ')[0]
  const proximas = SECCIONES.filter((s) => s.pendiente && (!s.permiso || puede(s.permiso)))

  return (
    <Stack maw={960}>
      <Title order={2}>Hola, {primerNombre}</Title>

      <SimpleGrid cols={{ base: 1, md: 2 }} style={{ alignItems: 'start' }}>
        <Card withBorder padding="lg">
          <Text fw={600} mb="sm">Su cuenta</Text>
          <Stack gap="xs">
            <Group justify="space-between"><Text size="sm" c="dimmed">Perfil</Text>
              <Badge variant="light">{NOMBRES_ROL[yo.rol] ?? yo.rol}</Badge></Group>
            <Group justify="space-between"><Text size="sm" c="dimmed">Doble factor</Text>
              {yo.mfa_habilitado
                ? <Group gap={4}><IconShieldCheck size={16} color="var(--mantine-color-teal-7)" /><Text size="sm">Activo</Text></Group>
                : <Group gap={4}><IconShieldX size={16} color="var(--mantine-color-gray-6)" /><Text size="sm">No activo</Text></Group>}
            </Group>
            <Group justify="space-between"><Text size="sm" c="dimmed">Ingreso anterior</Text>
              <Text size="sm">{formatearFechaHora(yo.ultimo_acceso)}</Text></Group>
            <Group justify="space-between"><Text size="sm" c="dimmed">Permisos</Text>
              <Text size="sm">{yo.permisos.length}</Text></Group>
          </Stack>
        </Card>

        <Card withBorder padding="lg">
          <Text fw={600} mb="sm">Qué está llegando</Text>
          <Timeline active={0} bulletSize={22} lineWidth={2}>
            <Timeline.Item bullet={<IconCheck size={12} />} title="Acceso, usuarios, catálogos, clientes y trámites">
              <Text size="xs" c="dimmed">Disponible</Text>
            </Timeline.Item>
            {proximas.map((s) => (
              <Timeline.Item key={s.ruta} title={<Anchor component={Link} to={s.ruta} size="sm">{s.titulo}</Anchor>}>
                <Text size="xs" c="dimmed">{s.pendiente!.fecha}</Text>
              </Timeline.Item>
            ))}
          </Timeline>
        </Card>
      </SimpleGrid>

      <Card withBorder padding="lg">
        <Group gap="sm">
          <ThemeIcon variant="light" color="gray" radius="xl"><IconBell size={16} /></ThemeIcon>
          <Text size="sm" c="dimmed">
            Aquí va a aparecer su bandeja del día: tareas vencidas, citas próximas, clientes que no han enviado
            información y saldos por cobrar. Llega con el centro de alertas, el 14/10.
          </Text>
        </Group>
      </Card>
    </Stack>
  )
}
