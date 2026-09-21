import { Alert, Anchor, Button, PasswordInput, Stack } from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, exigir } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { PantallaCentrada } from '../componentes/PantallaCentrada'
import { mostrarError, validarPassword } from '../lib/errores'

export function CambiarContrasena() {
  const { yo, salir } = useSesion()
  const obligatorio = yo?.debe_cambiar_password ?? false

  const formulario = useForm({
    initialValues: { actual: '', nueva: '', confirmacion: '' },
    validate: {
      actual: (v) => (v ? null : 'Escriba la contraseña actual'),
      nueva: (v, todo) => validarPassword(v) ?? (v === todo.actual ? 'Debe ser distinta de la actual.' : null),
      confirmacion: (v, todo) => (v === todo.nueva ? null : 'No coincide con la nueva'),
    },
  })

  const cambiar = useMutation({
    mutationFn: ({ actual, nueva }: typeof formulario.values) =>
      exigir(api.POST('/api/v1/auth/cambiar-password', { body: { actual, nueva } })),
    // El backend cierra todas las sesiones, incluida esta: hay que volver a entrar
    onSuccess: () => salir('Contraseña cambiada. Ingrese con la nueva.', 'teal'),
    onError: (e) => mostrarError(e, 'No se pudo cambiar'),
  })

  return (
    <PantallaCentrada titulo="Cambiar contraseña"
      subtitulo={obligatorio ? 'Antes de empezar, reemplace la contraseña temporal que le entregaron.' : undefined}>
      <form onSubmit={formulario.onSubmit((v) => cambiar.mutate(v))}>
        <Stack>
          <PasswordInput label={obligatorio ? 'Contraseña temporal' : 'Contraseña actual'}
            autoComplete="current-password" {...formulario.getInputProps('actual')} />
          <PasswordInput label="Contraseña nueva" description="Mínimo 10 caracteres, con letras y números."
            autoComplete="new-password" {...formulario.getInputProps('nueva')} />
          <PasswordInput label="Repita la contraseña nueva" autoComplete="new-password"
            {...formulario.getInputProps('confirmacion')} />
          <Alert variant="light" color="gray">Al cambiarla se cierran todas sus sesiones abiertas.</Alert>
          <Button type="submit" fullWidth loading={cambiar.isPending}>Cambiar contraseña</Button>
          {!obligatorio && <Anchor component={Link} to="/" size="sm" ta="center">Cancelar</Anchor>}
        </Stack>
      </form>
    </PantallaCentrada>
  )
}
