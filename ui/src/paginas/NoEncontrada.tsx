import { Button, Stack, Text, Title } from '@mantine/core'
import { Link } from 'react-router-dom'

export function NoEncontrada() {
  return (
    <Stack align="flex-start">
      <Title order={2}>Esta página no existe</Title>
      <Text c="dimmed">Puede que el enlace esté mal escrito o que la página se haya movido.</Text>
      <Button component={Link} to="/" variant="light">Ir a Mi trabajo</Button>
    </Stack>
  )
}
