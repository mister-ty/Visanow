import { Checkbox, Group, Select, Textarea, TextInput } from '@mantine/core'
import type { UseFormReturnType } from '@mantine/form'
import { aSelect, useCatalogos } from '../lib/catalogos'

/** Lo que un cliente tiene, que es lo mismo al crearlo y al editarlo. */
export interface ValoresCliente {
  nombre: string
  tipo_documento: string
  numero_documento: string
  telefono: string
  email: string
  ciudad: string
  pais_id: string
  canal_id: string
  observaciones: string
  consentimiento: boolean
}

export const CLIENTE_VACIO: ValoresCliente = {
  nombre: '', tipo_documento: '', numero_documento: '', telefono: '', email: '',
  ciudad: '', pais_id: '', canal_id: '', observaciones: '', consentimiento: false,
}

/**
 * Los campos de un cliente, en un solo sitio.
 *
 * Estaban escritos dos veces —una en «Nuevo cliente» y otra en «Editar»— y las
 * dos copias ya se habían separado: al crear no existía el campo de
 * observaciones, así que para escribir una nota había que guardar la ficha y
 * volver a abrirla. Eso es lo que pasa siempre con un formulario copiado, y por
 * eso vive acá: el día que se agregue un dato del cliente, aparece en los dos.
 */
export function CamposCliente({ formulario, autofoco = false }: {
  formulario: UseFormReturnType<ValoresCliente>
  autofoco?: boolean
}) {
  const catalogos = useCatalogos()
  return (
    <>
      <TextInput label="Nombre completo" data-autofocus={autofoco || undefined}
        {...formulario.getInputProps('nombre')} />
      <Group grow>
        <TextInput label="Tipo de documento" placeholder="CC, CE, PA"
          {...formulario.getInputProps('tipo_documento')} />
        <TextInput label="Número de documento" {...formulario.getInputProps('numero_documento')} />
      </Group>
      <Group grow>
        <TextInput label="Teléfono" placeholder="3105177800"
          {...formulario.getInputProps('telefono')} />
        <TextInput label="Correo" type="email" {...formulario.getInputProps('email')} />
      </Group>
      <Group grow>
        <TextInput label="Ciudad" {...formulario.getInputProps('ciudad')} />
        <Select label="País" data={aSelect(catalogos.data?.paises)} searchable clearable
          {...formulario.getInputProps('pais_id')} />
      </Group>
      <Select label="¿Por dónde llegó?" data={aSelect(catalogos.data?.canales)} clearable
        description="Sirve para saber qué canal trae más clientes"
        {...formulario.getInputProps('canal_id')} />
      <Textarea label="Observaciones" autosize minRows={2}
        description="Lo que haga falta recordar de este cliente"
        {...formulario.getInputProps('observaciones')} />
      <Checkbox label="Autorizó el tratamiento de sus datos personales"
        {...formulario.getInputProps('consentimiento', { type: 'checkbox' })} />
    </>
  )
}
