import {
  ActionIcon, Alert, Anchor, Button, FileInput, Group, Loader, Modal, Stack,
  Switch, Text, TextInput, Tooltip,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconDownload, IconExternalLink, IconFile, IconLink, IconLock, IconTrash, IconUpload,
} from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, exigir, token, urlApi, type Esquemas } from '../api/cliente'
import { mostrarError } from '../lib/errores'
import { formatearFechaHora } from '../lib/formato'

type Documento = Esquemas['DocumentoSalida']
type Entidad = 'cliente' | 'solicitante' | 'caso' | 'negocio' | 'pago' | 'gasto'

const pesa = (bytes?: number | null) =>
  bytes == null ? '' : bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`

/**
 * Los documentos de una ficha (RNF-04, RF-064).
 *
 * Lo que se sube queda cifrado en el servidor. Lo que **no** se puede es
 * subirlo donde se va a perder: el servidor dice primero si tiene disco de
 * verdad, y si no lo tiene, acá no aparece el botón de subir — aparece el de
 * enlazar, con el motivo. Ofrecer «subir archivo» donde el archivo se va a
 * perder es peor que no ofrecerlo, porque la persona cree que quedó guardado.
 */
export function Documentos({ entidad, entidadId, puedeEditar = true }: {
  entidad: Entidad; entidadId: number; puedeEditar?: boolean
}) {
  const qc = useQueryClient()
  const [subiendo, setSubiendo] = useState(false)
  const [enlazando, setEnlazando] = useState(false)
  const clave = ['documentos', entidad, entidadId]

  const estado = useQuery({
    queryKey: ['documentos', 'estado'],
    queryFn: () => exigir(api.GET('/api/v1/documentos/estado')),
    staleTime: 10 * 60 * 1000,
  })

  const lista = useQuery({
    queryKey: clave,
    queryFn: () => exigir(api.GET('/api/v1/documentos', {
      params: { query: { entidad, entidad_id: entidadId } },
    })),
  })

  const quitar = useMutation({
    mutationFn: (id: number) => exigir(api.DELETE('/api/v1/documentos/{documento_id}', {
      params: { path: { documento_id: id } },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Documento eliminado' })
      qc.invalidateQueries({ queryKey: clave })
    },
    onError: (e) => mostrarError(e, 'No se pudo eliminar'),
  })

  // Por fetch y no por un <a href>: el token vive en sessionStorage, no en una
  // cookie, y un enlace no lo enviaría. Tampoco puede ir en la URL.
  const bajar = async (d: Documento) => {
    try {
      const r = await fetch(`${urlApi}/api/v1/documentos/${d.id}/contenido`, {
        headers: { Authorization: `Bearer ${token.leer() ?? ''}` },
      })
      if (!r.ok) {
        const cuerpo = await r.json().catch(() => ({}))
        throw new Error(cuerpo.detalle ?? `No se pudo descargar (${r.status})`)
      }
      const url = URL.createObjectURL(await r.blob())
      const a = document.createElement('a')
      a.href = url
      a.download = d.nombre
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      notifications.show({
        color: 'red', title: 'No se pudo descargar',
        message: e instanceof Error ? e.message : 'Error inesperado',
      })
    }
  }

  if (lista.isPending) return <Loader size="sm" color="teal" />
  const docs = lista.data ?? []
  const sinDisco = estado.data && !estado.data.se_pueden_subir

  return (
    <Stack gap="xs">
      {docs.length === 0 && <Text size="sm" c="dimmed">Todavía no hay documentos.</Text>}

      {docs.map((d: Documento) => (
        <Group key={d.id} justify="space-between" wrap="nowrap">
          <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
            {d.almacenamiento === 'enlace'
              ? <IconLink size={16} color="var(--mantine-color-blue-6)" />
              : <IconFile size={16} color="var(--mantine-color-gray-6)" />}
            <div style={{ minWidth: 0 }}>
              <Group gap={6} wrap="nowrap">
                <Text size="sm" truncate>{d.nombre}</Text>
                {d.restringido && (
                  <Tooltip label="Reservado: solo quien hace el trámite">
                    <IconLock size={13} color="var(--mantine-color-orange-6)" />
                  </Tooltip>)}
              </Group>
              <Text size="xs" c="dimmed">
                {formatearFechaHora(d.creado_en)}
                {d.tamano_bytes ? ` · ${pesa(d.tamano_bytes)}` : ''}
              </Text>
            </div>
          </Group>
          <Group gap={4} wrap="nowrap">
            {d.almacenamiento === 'enlace'
              ? (
                <Anchor href={d.url ?? '#'} target="_blank" rel="noopener noreferrer">
                  <ActionIcon variant="subtle" aria-label={`Abrir ${d.nombre}`}>
                    <IconExternalLink size={16} />
                  </ActionIcon>
                </Anchor>)
              : (
                <ActionIcon variant="subtle" aria-label={`Descargar ${d.nombre}`}
                  onClick={() => bajar(d)}>
                  <IconDownload size={16} />
                </ActionIcon>)}
            {puedeEditar && (
              <ActionIcon variant="subtle" color="red" aria-label={`Eliminar ${d.nombre}`}
                onClick={() => quitar.mutate(d.id)}>
                <IconTrash size={16} />
              </ActionIcon>)}
          </Group>
        </Group>))}

      {puedeEditar && (
        <Group gap="xs" mt={4}>
          {!sinDisco && (
            <Button size="xs" variant="light" leftSection={<IconUpload size={14} />}
              onClick={() => setSubiendo(true)}>Subir archivo</Button>)}
          <Button size="xs" variant={sinDisco ? 'light' : 'default'}
            leftSection={<IconLink size={14} />}
            onClick={() => setEnlazando(true)}>Enlazar</Button>
        </Group>)}

      {puedeEditar && sinDisco && (
        <Alert color="yellow" variant="light" p="xs">
          <Text size="xs">{estado.data?.motivo}</Text>
        </Alert>)}

      {subiendo && (
        <SubirArchivo entidad={entidad} entidadId={entidadId} cerrar={() => setSubiendo(false)}
          maxMb={estado.data?.max_mb ?? 25} tipos={estado.data?.tipos ?? []}
          listo={() => qc.invalidateQueries({ queryKey: clave })} />)}
      {enlazando && (
        <EnlazarDocumento entidad={entidad} entidadId={entidadId}
          cerrar={() => setEnlazando(false)}
          listo={() => qc.invalidateQueries({ queryKey: clave })} />)}
    </Stack>
  )
}

function Reservado({ valor, cambiar }: { valor: boolean; cambiar: (v: boolean) => void }) {
  return (
    <Switch checked={valor} onChange={(e) => cambiar(e.currentTarget.checked)}
      label="Reservado"
      description="El pasaporte escaneado y el DS-160 solo los ve quien hace el trámite" />
  )
}

function SubirArchivo({ entidad, entidadId, cerrar, listo, maxMb, tipos }: {
  entidad: Entidad; entidadId: number; cerrar: () => void; listo: () => void
  maxMb: number; tipos: string[]
}) {
  const [archivo, setArchivo] = useState<File | null>(null)
  const [reservado, setReservado] = useState(false)

  const subir = useMutation({
    mutationFn: async () => {
      if (!archivo) throw new Error('Escoja un archivo')
      const cuerpo = new FormData()
      cuerpo.append('archivo', archivo)
      cuerpo.append('entidad', entidad)
      cuerpo.append('entidad_id', String(entidadId))
      cuerpo.append('restringido', String(reservado))
      // FormData va por fetch: openapi-fetch serializa a JSON.
      const r = await fetch(`${urlApi}/api/v1/documentos`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.leer() ?? ''}` },
        body: cuerpo,
      })
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detalle ?? 'No se pudo subir')
      return r.json()
    },
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Documento guardado, cifrado' })
      listo()
      cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo subir'),
  })

  return (
    <Modal opened onClose={cerrar} title="Subir documento">
      <Stack>
        <FileInput label="Archivo" placeholder={`Hasta ${maxMb} MB`} value={archivo}
          onChange={setArchivo}
          description={`Se aceptan ${tipos.join(', ')}. Queda cifrado en el servidor.`} />
        <Reservado valor={reservado} cambiar={setReservado} />
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={subir.isPending} disabled={!archivo}
            onClick={() => subir.mutate()}>Subir</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function EnlazarDocumento({ entidad, entidadId, cerrar, listo }: {
  entidad: Entidad; entidadId: number; cerrar: () => void; listo: () => void
}) {
  const [nombre, setNombre] = useState('')
  const [url, setUrl] = useState('')
  const [reservado, setReservado] = useState(false)

  const guardar = useMutation({
    mutationFn: () => exigir(api.POST('/api/v1/documentos/enlace', {
      body: { entidad, entidad_id: entidadId, nombre, url, restringido: reservado },
    })),
    onSuccess: () => {
      notifications.show({ color: 'teal', message: 'Enlace guardado' })
      listo()
      cerrar()
    },
    onError: (e) => mostrarError(e, 'No se pudo guardar'),
  })

  return (
    <Modal opened onClose={cerrar} title="Enlazar un documento">
      <Stack>
        <Text size="sm" c="dimmed">
          Para lo que ya vive en otro lado —una carpeta compartida, por ejemplo—. Acá queda
          la referencia; el archivo se queda donde está.
        </Text>
        <TextInput label="Cómo se llama" value={nombre} required
          onChange={(e) => setNombre(e.currentTarget.value)}
          placeholder="Carpeta del cliente" />
        <TextInput label="Dirección" value={url} required
          onChange={(e) => setUrl(e.currentTarget.value)}
          placeholder="https://drive.google.com/..." />
        <Reservado valor={reservado} cambiar={setReservado} />
        <Group justify="flex-end">
          <Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button loading={guardar.isPending} disabled={!nombre || !url}
            onClick={() => guardar.mutate()}>Guardar</Button>
        </Group>
      </Stack>
    </Modal>
  )
}
