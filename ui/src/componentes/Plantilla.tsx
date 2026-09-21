import { AppShell, Avatar, Burger, Group, Menu, NavLink, Stack, Text, UnstyledButton } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconChevronDown, IconLogout } from '@tabler/icons-react'
import { NavLink as Enlace, Outlet, useLocation } from 'react-router-dom'
import { useSesion } from '../auth/sesion'
import { NOMBRES_ROL } from '../lib/formato'
import { SECCIONES } from '../navegacion'

export function Plantilla() {
  const [abierto, { toggle, close }] = useDisclosure()
  const { yo, puede, salir } = useSesion()
  const { pathname } = useLocation()
  const visibles = SECCIONES.filter((s) => !s.permiso || puede(s.permiso))
  const iniciales = (yo?.nombre ?? '?').split(' ').map((p) => p[0]).slice(0, 2).join('')

  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 240, breakpoint: 'sm', collapsed: { mobile: !abierto } }}
      padding="lg">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger opened={abierto} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Menú" />
            <Text fw={800} size="lg" c="teal.8">VisaNow</Text>
          </Group>
          <Menu position="bottom-end" withinPortal>
            <Menu.Target>
              <UnstyledButton aria-label="Mi cuenta">
                <Group gap="xs">
                  <Avatar color="teal" radius="xl" size="sm">{iniciales}</Avatar>
                  <Stack gap={0} visibleFrom="sm">
                    <Text size="sm" fw={600} lh={1.2}>{yo?.nombre}</Text>
                    <Text size="xs" c="dimmed" lh={1.2}>{NOMBRES_ROL[yo?.rol ?? ''] ?? yo?.rol}</Text>
                  </Stack>
                  <IconChevronDown size={14} />
                </Group>
              </UnstyledButton>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item component={Enlace} to="/cambiar-contrasena">Cambiar contraseña</Menu.Item>
              <Menu.Divider />
              <Menu.Item color="red" leftSection={<IconLogout size={14} />} onClick={() => salir()}>
                Salir
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        {visibles.map((s) => (
          <NavLink key={s.ruta} component={Enlace} to={s.ruta} label={s.titulo} onClick={close}
            leftSection={<s.icono size={18} stroke={1.6} />}
            active={s.ruta === '/' ? pathname === '/' : pathname.startsWith(s.ruta)}
            description={s.pendiente ? `Llega el ${s.pendiente.fecha.split(' ').pop()}` : undefined} />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  )
}
