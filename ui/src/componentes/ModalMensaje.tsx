import {
  Alert, Button, CopyButton, Group, Loader, Modal, Select, Stack, Text, Textarea,
} from '@mantine/core'
import { useMutation, useQuery } from '@tanstack/react-query'
import { IconBrandWhatsapp, IconMail } from '@tabler/icons-react'
import { useState } from 'react'
import { api, exigir } from '../api/cliente'
import { mostrarError } from '../lib/errores'

/** Mensaje al cliente armado con la plantilla de un evento (RF-063).
 *
 *  El sistema no envía nada: deja el texto listo para copiarlo o abrirlo en
 *  WhatsApp o el correo, y la persona lo manda. Así nada sale sin que alguien
 *  lo haya leído antes. Se monta solo al abrirlo, así cada trámite arranca limpio. */
export function ModalMensaje({ casoId, cerrar }: {
  casoId: number
  cerrar: () => void
}) {
  const abierto = true
  const [plantilla, setPlantilla] = useState<string | null>(null)
  const [texto, setTexto] = useState('')
  const [faltantes, setFaltantes] = useState<string[]>([])
  const [contacto, setContacto] = useState<{ telefono: string | null; correo: string | null; asunto: string | null }>(
    { telefono: null, correo: null, asunto: null })

  const plantillas = useQuery({
    queryKey: ['plantillas'],
    queryFn: () => exigir(api.GET('/api/v1/plantillas')),
    enabled: abierto,
  })
  const generar = useMutation({
    mutationFn: (id: number) => exigir(api.POST('/api/v1/plantillas/{plantilla_id}/generar', {
      params: { path: { plantilla_id: id } }, body: { caso_id: casoId } })),
    onSuccess: (r) => {
      setTexto(r.mensaje)
      setFaltantes(r.faltantes)
      setContacto({ telefono: r.telefono ?? null, correo: r.correo ?? null, asunto: r.asunto ?? null })
    },
    onError: (e) => mostrarError(e, 'No se pudo armar el mensaje'),
  })

  const elegir = (v: string | number | null) => {
    setPlantilla(v === null ? null : String(v))
    if (v !== null) generar.mutate(Number(v))
  }

  // wa.me exige el número solo con dígitos y con indicativo de país
  const digitos = (contacto.telefono ?? '').replace(/\D/g, '')
  const whatsapp = digitos ? `https://wa.me/${digitos}?text=${encodeURIComponent(texto)}` : null
  const correo = contacto.correo
    ? `mailto:${contacto.correo}?subject=${encodeURIComponent(contacto.asunto ?? '')}&body=${encodeURIComponent(texto)}`
    : null

  return (
    <Modal opened={abierto} onClose={cerrar} title="Mensaje al cliente" size="lg">
      <Stack>
        {plantillas.isPending && <Loader size="sm" color="teal" />}
        <Select label="Plantilla" placeholder="Elija el evento" value={plantilla} onChange={elegir}
          data={(plantillas.data ?? []).map((p) => ({
            value: String(p.id), label: `${p.nombre} (${p.canal})` }))}
          nothingFoundMessage="No hay plantillas activas" />
        {generar.isPending && <Loader size="sm" color="teal" />}
        {faltantes.length > 0 && (
          <Alert color="yellow" variant="light">
            Faltan datos para {faltantes.map((f) => `{{${f}}}`).join(', ')}. Quedaron a la vista:
            complételos antes de enviar.
          </Alert>)}
        {plantilla && !generar.isPending && (
          <>
            <Textarea label="Mensaje" autosize minRows={5} value={texto}
              onChange={(e) => setTexto(e.currentTarget.value)} />
            <Text size="xs" c="dimmed">Puede ajustarlo antes de copiarlo o enviarlo.</Text>
            <Group justify="flex-end">
              <CopyButton value={texto}>
                {({ copied, copy }) => (
                  <Button variant="default" onClick={copy}>{copied ? 'Copiado' : 'Copiar'}</Button>)}
              </CopyButton>
              {whatsapp && (
                <Button component="a" href={whatsapp} target="_blank" rel="noreferrer"
                  leftSection={<IconBrandWhatsapp size={16} />}>WhatsApp</Button>)}
              {correo && (
                <Button component="a" href={correo} variant="light"
                  leftSection={<IconMail size={16} />}>Correo</Button>)}
            </Group>
          </>)}
      </Stack>
    </Modal>
  )
}
