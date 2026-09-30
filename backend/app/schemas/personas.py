from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Criterio = Literal['documento', 'pasaporte', 'telefono', 'email', 'nombre', 'manual']


class ClienteBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=160)
    tipo_documento: str | None = Field(default=None, max_length=20)
    numero_documento: str | None = Field(default=None, max_length=40)
    telefono: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    ciudad: str | None = Field(default=None, max_length=80)
    pais_id: int | None = None
    canal_id: int | None = None
    consentimiento: bool = False
    observaciones: str | None = None


class ClienteCrear(ClienteBase):
    pass


class ClienteEditar(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=160)
    tipo_documento: str | None = None
    numero_documento: str | None = None
    telefono: str | None = None
    email: EmailStr | None = None
    ciudad: str | None = None
    pais_id: int | None = None
    canal_id: int | None = None
    consentimiento: bool | None = None
    observaciones: str | None = None


class ClienteSalida(BaseModel):
    id: int
    nombre: str
    tipo_documento: str | None
    numero_documento: str | None
    telefono: str | None
    email: str | None
    ciudad: str | None
    consentimiento: bool
    archivado: bool
    creado_en: datetime


class SolicitanteSalida(BaseModel):
    id: int
    grupo_id: int | None
    cliente_id: int | None
    nombre: str
    tipo_documento: str | None
    numero_documento: str | None
    pasaporte: str | None = Field(description='Enmascarado: solo los últimos caracteres')
    fecha_nacimiento: date | None
    nacionalidad: str | None
    telefono: str | None
    email: str | None
    relacion_con_cliente: str | None


class GrupoSalida(BaseModel):
    id: int
    nombre: str
    cliente_contacto_id: int
    observaciones: str | None
    solicitantes: list[SolicitanteSalida] = []


class ClienteDetalle(ClienteSalida):
    pais_id: int | None
    canal_id: int | None
    observaciones: str | None
    consentimiento_fecha: datetime | None
    grupos: list[GrupoSalida] = []
    solicitantes: list[SolicitanteSalida] = Field(default=[], description='Propios y de sus grupos')


class PaginaClientes(BaseModel):
    total: int
    pagina: int
    tamano: int
    items: list[ClienteSalida]


class GrupoCrear(BaseModel):
    nombre: str = Field(min_length=2, max_length=160)
    cliente_contacto_id: int
    observaciones: str | None = None


class SolicitanteCrear(BaseModel):
    grupo_id: int | None = None
    cliente_id: int | None = None
    nombre: str = Field(min_length=2, max_length=160)
    tipo_documento: str | None = Field(default=None, max_length=20)
    numero_documento: str | None = Field(default=None, max_length=40)
    pasaporte: str | None = Field(default=None, max_length=40)
    fecha_nacimiento: date | None = None
    nacionalidad: str | None = Field(default=None, max_length=80)
    telefono: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    relacion_con_cliente: str | None = Field(default=None, max_length=40,
                                             description='titular, cónyuge, hijo, otro')
    observaciones: str | None = None


class SolicitanteEditar(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=160)
    tipo_documento: str | None = None
    numero_documento: str | None = None
    pasaporte: str | None = None
    fecha_nacimiento: date | None = None
    nacionalidad: str | None = None
    telefono: str | None = None
    email: EmailStr | None = None
    relacion_con_cliente: str | None = None
    observaciones: str | None = None


class VerificarDuplicados(BaseModel):
    """Se consulta mientras se escribe la ficha, antes de guardarla."""
    nombre: str = Field(min_length=2)
    tipo_documento: str | None = None
    numero_documento: str | None = None
    telefono: str | None = None
    email: EmailStr | None = None
    pasaporte: str | None = None
    excluir_id: int | None = None


class CoincidenciaSalida(BaseModel):
    cliente_id: int
    nombre: str
    confianza: Literal['alta', 'media', 'baja']
    criterios: list[str]
    explicacion: str
    parecido_nombre: float
    archivado: bool
    posible_familiar: bool = Field(default=False,
                                   description='Comparte datos pero el nombre de pila es distinto')


class FusionEntrada(BaseModel):
    absorbido_id: int
    criterio: Criterio = 'manual'


class FusionSalida(BaseModel):
    conservado_id: int
    absorbido_id: int
    movidos: dict[str, int] = Field(description='Cuántos registros cambiaron de ficha, por tabla')


class PasaporteSalida(BaseModel):
    solicitante_id: int
    pasaporte: str = Field(description='Valor completo. La consulta queda en la auditoría.')
