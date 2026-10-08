from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Canal = Literal['whatsapp', 'correo', 'sms']


class PlantillaCrear(BaseModel):
    evento: str = Field(min_length=3, max_length=40)
    nombre: str = Field(min_length=3, max_length=80)
    canal: Canal = 'whatsapp'
    asunto: str | None = Field(default=None, max_length=160, description='Solo para correo')
    cuerpo: str = Field(min_length=1, description='Con variables como {{cliente_nombre}}')


class PlantillaEditar(BaseModel):
    nombre: str | None = Field(default=None, min_length=3, max_length=80)
    asunto: str | None = Field(default=None, max_length=160)
    cuerpo: str | None = Field(default=None, min_length=1)
    activa: bool | None = None


class PlantillaSalida(BaseModel):
    id: int
    evento: str
    nombre: str
    canal: Canal
    asunto: str | None
    cuerpo: str
    activa: bool
    variables: list[str]
    actualizada_en: datetime


class VariableSalida(BaseModel):
    clave: str
    descripcion: str


class EventoSalida(BaseModel):
    clave: str
    nombre: str


class CatalogoPlantillas(BaseModel):
    eventos: list[EventoSalida]
    variables: list[VariableSalida]


class RenderEntrada(BaseModel):
    caso_id: int | None = None
    negocio_id: int | None = Field(default=None, description='Para mensajes de saldo sin trámite')


class RenderSalida(BaseModel):
    asunto: str | None
    mensaje: str
    faltantes: list[str] = Field(description='Variables sin dato: quedan visibles como {{x}}')
    telefono: str | None
    correo: str | None
