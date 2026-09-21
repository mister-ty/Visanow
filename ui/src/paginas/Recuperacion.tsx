import { Alert, Anchor, Button, PasswordInput, Stack, TextInput } from '@mantine/core'
import { useForm } from '@mantine/form'
import { notifications } from '@mantine/notifications'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, exigir } from '../api/cliente'
import { PantallaCentrada } from '../componentes/PantallaCentrada'
import { mostrarError, validarPassword } from '../lib/errores'

export function Recuperar() {
  const [enviado, setEnviado] = useState(false)
  const formulario = useForm({
    initialValues: { email: '' },
    validate: { email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : 'Escriba un correo válido') },
  })
  const pedir = useMutation({
    mutationFn: (v: { email: string }) => exigir(api.POST('/api/v1/auth/recuperar', { body: v })),
    onSuccess: () => setEnviado(true),
    onError: (e) => mostrarError(e),
  })

  return (
    <PantallaCentrada titulo="Recuperar contraseña">
      {enviado ? (
        <Stack>
          {/* Mismo mensaje exista o no la cuenta: no se revela quién tiene acceso */}
          <Alert color="teal" variant="light">
            Si el correo corresponde a una cuenta activa, le llegará un enlace para crear una contraseña nueva.
            Vence en 30 minutos.
          </Alert>
          <Anchor component={Link} to="/ingreso" size="sm" ta="center">Volver al ingreso</Anchor>
        </Stack>
      ) : (
        <form onSubmit={formulario.onSubmit((v) => pedir.mutate(v))}>
          <Stack>
            <TextInput label="Correo" type="email" autoFocus {...formulario.getInputProps('email')} />
            <Button type="submit" fullWidth loading={pedir.isPending}>Enviar enlace</Button>
            <Anchor component={Link} to="/ingreso" size="sm" ta="center">Volver al ingreso</Anchor>
          </Stack>
        </form>
      )}
    </PantallaCentrada>
  )
}

export function Restablecer() {
  const navegar = useNavigate()
  // El token viene en el enlace del correo. Se lee una vez y se quita de la barra
  // de direcciones para que no quede en el historial ni en capturas de pantalla.
  const [tokenEnlace] = useState(() => {
    const t = new URLSearchParams(window.location.search).get('token')
    if (t) window.history.replaceState(null, '', window.location.pathname)
    return t
  })
  const formulario = useForm({
    initialValues: { nueva: '', confirmacion: '' },
    validate: {
      nueva: validarPassword,
      confirmacion: (v, todo) => (v === todo.nueva ? null : 'No coincide con la nueva'),
    },
  })
  const restablecer = useMutation({
    mutationFn: ({ nueva }: typeof formulario.values) =>
      exigir(api.POST('/api/v1/auth/restablecer', { body: { token: tokenEnlace!, nueva } })),
    onSuccess: () => {
      notifications.show({ color: 'teal', title: 'Listo', message: 'Contraseña creada. Ingrese con ella.' })
      navegar('/ingreso', { replace: true })
    },
    onError: (e) => mostrarError(e),
  })

  return (
    <PantallaCentrada titulo="Crear contraseña nueva">
      {!tokenEnlace ? (
        <Stack>
          <Alert color="red" variant="light">El enlace no es válido. Pida uno nuevo.</Alert>
          <Anchor component={Link} to="/recuperar" size="sm" ta="center">Pedir otro enlace</Anchor>
        </Stack>
      ) : (
        <form onSubmit={formulario.onSubmit((v) => restablecer.mutate(v))}>
          <Stack>
            <PasswordInput label="Contraseña nueva" description="Mínimo 10 caracteres, con letras y números."
              autoComplete="new-password" autoFocus {...formulario.getInputProps('nueva')} />
            <PasswordInput label="Repítala" autoComplete="new-password" {...formulario.getInputProps('confirmacion')} />
            <Button type="submit" fullWidth loading={restablecer.isPending}>Guardar</Button>
          </Stack>
        </form>
      )}
    </PantallaCentrada>
  )
}
