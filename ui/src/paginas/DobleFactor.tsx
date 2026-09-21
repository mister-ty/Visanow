import { Alert, Button, Center, Code, List, PinInput, Stack, Text } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { QRCodeSVG } from 'qrcode.react'
import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api, exigir } from '../api/cliente'
import { useSesion } from '../auth/sesion'
import { PantallaCentrada } from '../componentes/PantallaCentrada'
import { mostrarError } from '../lib/errores'

/** Activación del doble factor (RNF-02). Obligatoria para quien ve dinero,
 *  usuarios o auditoría: el backend no le deja hacer nada más hasta activarlo. */
export function DobleFactor() {
  const { yo, entrar } = useSesion()
  const navegar = useNavigate()
  const clienteQuery = useQueryClient()
  const [codigo, setCodigo] = useState('')

  const iniciar = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/auth/mfa/iniciar')),
    onError: (e) => mostrarError(e),
  })

  const confirmar = useMutation({
    mutationFn: (c: string) => exigir(api.POST('/api/v1/auth/mfa/confirmar', { body: { codigo: c } })),
    // Activarlo cierra las sesiones abiertas con solo contraseña; esta recibe una nueva
    onSuccess: (r) => {
      entrar(r.access_token)
      clienteQuery.invalidateQueries({ queryKey: ['yo'] })
      navegar('/', { replace: true })
    },
    onError: (e) => { setCodigo(''); mostrarError(e, 'El código no coincide') },
  })

  if (yo?.mfa_habilitado) return <Navigate to="/" replace />

  return (
    <PantallaCentrada titulo="Activar doble factor"
      subtitulo="Su perfil maneja información sensible. Además de la contraseña, se le pedirá un código del teléfono.">
      {!iniciar.data ? (
        <Stack>
          <Text size="sm">Necesita una aplicación autenticadora en el teléfono, por ejemplo:</Text>
          <List size="sm">
            <List.Item>Google Authenticator</List.Item>
            <List.Item>Microsoft Authenticator</List.Item>
          </List>
          <Button fullWidth loading={iniciar.isPending} onClick={() => iniciar.mutate()}>Ya la tengo, continuar</Button>
        </Stack>
      ) : (
        <Stack>
          <Text size="sm">1. En la aplicación, agregue una cuenta y escanee este código:</Text>
          <Center p="sm" bg="white"><QRCodeSVG value={iniciar.data.uri} size={180} marginSize={2} /></Center>
          <Text size="xs" c="dimmed">¿No puede escanearlo? Escriba esta clave a mano:</Text>
          <Code block ta="center" fz="sm">{iniciar.data.secreto.match(/.{1,4}/g)?.join(' ')}</Code>
          <Text size="sm">2. Escriba el código de 6 dígitos que aparece en la aplicación:</Text>
          <Center>
            <PinInput length={6} type="number" oneTimeCode value={codigo} onChange={setCodigo}
              onComplete={(c) => confirmar.mutate(c)} disabled={confirmar.isPending} />
          </Center>
          <Button fullWidth loading={confirmar.isPending} disabled={codigo.length !== 6}
            onClick={() => confirmar.mutate(codigo)}>Activar</Button>
          <Alert variant="light" color="yellow">
            Si pierde el teléfono, la administradora puede reiniciarle el doble factor.
          </Alert>
        </Stack>
      )}
    </PantallaCentrada>
  )
}
