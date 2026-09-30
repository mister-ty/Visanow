import { Badge, Combobox, Group, Loader, Text, TextInput, useCombobox } from '@mantine/core'
import { useDebouncedValue, useHotkeys } from '@mantine/hooks'
import { IconPlaneDeparture, IconSearch, IconUser, IconUsersGroup } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, exigir, type Esquemas } from '../api/cliente'

type Resultado = Esquemas['ResultadoBusqueda']

const ICONOS = {
  cliente: IconUser,
  solicitante: IconUsersGroup,
  tramite: IconPlaneDeparture,
} as const

const ROTULOS = {
  cliente: 'Clientes',
  solicitante: 'Personas que viajan',
  tramite: 'Trámites',
} as const

/** Una sola caja para todo (RF-029): el asesor escribe lo que tenga a mano —un
 *  nombre, un teléfono, una cédula, un pasaporte, el n.º de solicitud— y llega
 *  a la ficha. No hay que saber en qué pantalla buscar. */
export function BusquedaGlobal() {
  const navegar = useNavigate()
  const combobox = useCombobox({ onDropdownClose: () => combobox.resetSelectedOption() })
  const [texto, setTexto] = useState('')
  const [buscado] = useDebouncedValue(texto.trim(), 300)
  const campo = useRef<HTMLInputElement>(null)
  useHotkeys([['mod+K', () => campo.current?.focus()]])

  const resultados = useQuery({
    queryKey: ['buscar', buscado],
    queryFn: () => exigir(api.GET('/api/v1/buscar', { params: { query: { q: buscado } } })),
    enabled: buscado.length >= 2,
    staleTime: 15_000,
  })

  const ir = (r: Resultado) => {
    navegar(r.ruta)
    setTexto('')
    combobox.closeDropdown()
    campo.current?.blur()
  }

  const grupos = (['cliente', 'solicitante', 'tramite'] as const)
    .map((tipo) => ({ tipo, items: (resultados.data ?? []).filter((r) => r.tipo === tipo) }))
    .filter((g) => g.items.length > 0)
  const planos = grupos.flatMap((g) => g.items)

  return (
    // El desplegable lleva ancho propio: en el teléfono el campo es angosto y
    // los nombres y los documentos quedaban cortados a la mitad.
    <Combobox store={combobox} withinPortal position="bottom-start" shadow="md" width={320}
      onOptionSubmit={(valor) => { const r = planos[Number(valor)]; if (r) ir(r) }}>
      <Combobox.Target>
        <TextInput ref={campo} value={texto} w={{ base: 180, sm: 340 }} size="sm"
          placeholder="Buscar persona, teléfono, documento…" aria-label="Buscar en todo el sistema"
          leftSection={<IconSearch size={16} />}
          rightSection={resultados.isFetching ? <Loader size={14} color="teal" /> : null}
          onChange={(e) => { setTexto(e.currentTarget.value); combobox.openDropdown() }}
          onFocus={() => combobox.openDropdown()}
          onBlur={() => combobox.closeDropdown()} />
      </Combobox.Target>

      <Combobox.Dropdown hidden={buscado.length < 2}>
        <Combobox.Options mah={380} style={{ overflowY: 'auto' }}>
          {grupos.map((g) => {
            const Icono = ICONOS[g.tipo]
            return (
              <Combobox.Group key={g.tipo} label={ROTULOS[g.tipo]}>
                {g.items.map((r) => (
                  <Combobox.Option key={`${r.tipo}-${r.id}`} value={String(planos.indexOf(r))}>
                    <Group gap="sm" wrap="nowrap">
                      <Icono size={16} stroke={1.6} />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <Text size="sm" truncate>{r.titulo}</Text>
                        <Text size="xs" c="dimmed" truncate>{r.detalle}</Text>
                      </div>
                      <Badge size="xs" variant="light" color="gray">{r.coincidio_por}</Badge>
                    </Group>
                  </Combobox.Option>
                ))}
              </Combobox.Group>
            )
          })}
          {!resultados.isFetching && planos.length === 0 && (
            <Combobox.Empty>
              Nada con «{buscado}». Se busca por nombre, teléfono, documento, correo, pasaporte,
              DS-160 o n.º de solicitud.
            </Combobox.Empty>
          )}
        </Combobox.Options>
      </Combobox.Dropdown>
    </Combobox>
  )
}
