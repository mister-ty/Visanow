import { Anchor, Button, Group, PasswordInput, PinInput, Stack, Text, TextInput } from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api, exigir } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { PantallaCentrada } from '../componentes/PantallaCentrada'
import { codigoDe, mostrarError } from '../lib/errores'

export function Ingreso() {
  const { autenticado, entrar } = useSesion()
  const navegar = useNavigate()
  const [tokenMfa, setTokenMfa] = useState<string | null>(null)
  const [codigo, setCodigo] = useState('')

  const formulario = useForm({
    initialValues: { email: '', password: '' },
    validate: {
      email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : 'Escriba un correo válido'),
      password: (v) => (v ? null : 'Escriba la contraseña'),
    },
  })

  const completar = (accessToken: string) => {
    entrar(accessToken)
    navegar('/', { replace: true })
  }

  const ingresar = useMutation({
    mutationFn: (datos: typeof formulario.values) => exigir(api.POST('/api/v1/auth/login', { body: datos })),
    onSuccess: (r) => ('requiere_mfa' in r ? setTokenMfa(r.token_mfa) : completar(r.access_token)),
    onError: (e) => mostrarError(e, 'No se pudo ingresar'),
  })

  const verificar = useMutation({
    mutationFn: (c: string) =>
      exigir(api.POST('/api/v1/auth/mfa/verificar', { body: { token_mfa: tokenMfa!, codigo: c } })),
    onSuccess: (r) => completar(r.access_token),
    onError: (e) => {
      setCodigo('')
      if (codigoDe(e) === 'token_mfa_invalido') setTokenMfa(null)   // venció el paso: volver al inicio
      mostrarError(e, 'No se pudo verificar')
    },
  })

  if (autenticado) return <Navigate to="/" replace />

  if (tokenMfa) {
    return (
      <PantallaCentrada titulo="Código de verificación"
        subtitulo="Escriba los 6 dígitos que muestra su aplicación autenticadora.">
        <Stack align="center">
          <PinInput length={6} type="number" oneTimeCode autoFocus value={codigo} size="lg"
            onChange={setCodigo} onComplete={(c) => verificar.mutate(c)} disabled={verificar.isPending} />
          <Button fullWidth loading={verificar.isPending} disabled={codigo.length !== 6}
            onClick={() => verificar.mutate(codigo)}>Verificar</Button>
          <Anchor size="sm" component="button" onClick={() => { setTokenMfa(null); setCodigo('') }}>
            Volver
          </Anchor>
        </Stack>
      </PantallaCentrada>
    )
  }

  return (
    <PantallaCentrada titulo="Ingresar">
      <form onSubmit={formulario.onSubmit((v) => ingresar.mutate(v))}>
        <Stack>
          <TextInput label="Correo" type="email" autoComplete="username" autoFocus
            {...formulario.getInputProps('email')} />
          <PasswordInput label="Contraseña" autoComplete="current-password"
            {...formulario.getInputProps('password')} />
          <Button type="submit" fullWidth loading={ingresar.isPending}>Ingresar</Button>
          <Group justify="center">
            <Anchor component={Link} to="/recuperar" size="sm">¿Olvidó su contraseña?</Anchor>
          </Group>
          <Text size="xs" c="dimmed" ta="center">
            Por seguridad, tras 5 intentos fallidos la cuenta se bloquea 15 minutos.
          </Text>
        </Stack>
      </form>
    </PantallaCentrada>
  )
}
