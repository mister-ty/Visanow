import { Card, Center, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'

/** Marco de las pantallas fuera de la aplicación: ingreso, recuperación, primer acceso. */
export function PantallaCentrada({ titulo, subtitulo, children }: {
  titulo: string; subtitulo?: string; children: ReactNode
}) {
  return (
    <Center mih="100vh" bg="gray.0" p="md">
      <Card withBorder shadow="sm" padding="xl" w="100%" maw={420}>
        <Stack gap={4} mb="lg" align="center">
          <Text fw={800} size="xl" c="teal.8">VisaNow</Text>
          <Title order={3} ta="center">{titulo}</Title>
          {subtitulo && <Text size="sm" c="dimmed" ta="center">{subtitulo}</Text>}
        </Stack>
        {children}
      </Card>
    </Center>
  )
}
