import { Button, Card, List, Stack, Text, Title } from '@mantine/core'
import { IconExternalLink } from '@tabler/icons-react'
import { urlAdministracion } from '../api/cliente'

/** Los catálogos se administran en el panel que sirve la API (/admin): ahí cada
 *  cambio queda auditado con valor anterior y nuevo. */
export function Configuracion() {
  return (
    <Stack maw={760}>
      <Title order={2}>Configuración</Title>
      <Card withBorder padding="lg">
        <Text fw={600} mb="xs">Catálogos y parámetros</Text>
        <Text size="sm" c="dimmed" mb="md">
          Servicios y precios, países, sedes, tipos de visa, canales, medios de pago, bancos, categorías de gasto,
          estados, alertas y parámetros como el plazo de pago del saldo.
        </Text>
        <List size="sm" spacing={4} mb="md">
          <List.Item>Se abre en una pestaña aparte y pide de nuevo el correo, la contraseña y el código.</List.Item>
          <List.Item>Cada cambio queda registrado: quién, cuándo, valor anterior y valor nuevo.</List.Item>
          <List.Item>Nada se borra: lo que ya no se usa se desactiva.</List.Item>
        </List>
        <Button component="a" href={urlAdministracion} target="_blank" rel="noopener"
          rightSection={<IconExternalLink size={16} />}>
          Abrir la administración de catálogos
        </Button>
      </Card>
    </Stack>
  )
}
