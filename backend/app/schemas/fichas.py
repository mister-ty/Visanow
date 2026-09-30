from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.casos import CasoSalida
from app.schemas.personas import ClienteDetalle

TipoNota = Literal['nota', 'llamada', 'whatsapp', 'correo', 'reunion']


class SucesoSalida(BaseModel):
    cuando: datetime
    tipo: str = Field(description="'sistema' para lo que registró el sistema; si no, el tipo de la nota")
    titulo: str
    detalle: str | None
    usuario: str | None
    caso_id: int | None


class CitaProxima(BaseModel):
    id: int
    caso_id: int
    solicitante: str
    tipo: str
    inicia_en: datetime
    estado: str
    sede: str | None


class ResumenFicha(BaseModel):
    personas: int
    tramites_abiertos: int
    tramites_total: int
    proxima_cita: datetime | None
    ultimo_contacto_en: datetime | None
    dias_sin_contacto: int | None


class Ficha360(BaseModel):
    """Todo lo que hoy está repartido entre tres archivos, en una sola respuesta."""
    cliente: ClienteDetalle
    resumen: ResumenFicha
    tramites: list[CasoSalida] = []
    citas: list[CitaProxima] = []
    cronologia: list[SucesoSalida] = []
    ve_tramites: bool = Field(description='False si el rol no tiene permiso de ver trámites')


class NotaCrear(BaseModel):
    tipo: TipoNota = 'nota'
    asunto: str | None = Field(default=None, max_length=200)
    cuerpo: str | None = None


class NotaSalida(BaseModel):
    id: int
    tipo: str
    asunto: str | None
    cuerpo: str | None
    ocurrido_en: datetime


class ResultadoBusqueda(BaseModel):
    tipo: Literal['cliente', 'solicitante', 'tramite']
    id: int
    titulo: str
    detalle: str
    ruta: str
    coincidio_por: str
