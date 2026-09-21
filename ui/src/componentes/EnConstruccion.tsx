import { Badge, Card, Group, List, Stack, Text, Title } from '@mantine/core'
import { IconCircleDashed } from '@tabler/icons-react'
import type { Seccion } from '../navegacion'

/** Pantalla aún no construida: dice qué va a tener y cuándo llega, en vez de
 *  mostrar una página vacía o datos inventados. */
export function EnConstruccion({ seccion }: { seccion: Seccion }) {
  const p = seccion.pendiente!
  return (
    <Stack maw={760}>
      <Group justify="space-between" align="center">
        <Title order={2}>{seccion.titulo}</Title>
        <Badge variant="light" color="gray" size="lg">En construcción · {p.fecha}</Badge>
      </Group>
      <Card withBorder padding="lg">
        <Text fw={600} mb="sm">Qué va a tener esta pantalla</Text>
        <List spacing="xs" icon={<IconCircleDashed size={16} color="var(--mantine-color-gray-5)" />}>
          {p.contenido.map((c) => <List.Item key={c}>{c}</List.Item>)}
        </List>
        <Text size="sm" c="dimmed" mt="md">Actividad {p.actividad} del cronograma.</Text>
      </Card>
    </Stack>
  )
}
