"""Importación del consolidado del SaaS (RF-030 a RF-036)."""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Resultado = Literal['nuevo', 'actualizado', 'sin_cambio', 'conflicto', 'rechazado']
EstadoImportacion = Literal['previsualizada', 'aplicada', 'descartada', 'fallida']
DecisionConflicto = Literal['resuelto_visanow', 'resuelto_saas', 'ignorado']


class FilaEntrada(BaseModel):
    """Una solicitud del export. Los nombres son los de las columnas, ya leídas."""
    numero_solicitud: str | None = Field(
        default=None, description='La llave: sin ella la fila se rechaza')
    solicitante: str | None = None
    pasaporte: str | None = None
    etapa: str | None = None
    fecha_creacion: date | datetime | None = None
    ds160_enviado_en: date | datetime | None = None
    ds160_numero: str | None = None
    busqueda_citas: Any = Field(default=None, description='«active» / «inactive» del export')
    fila: int | None = Field(default=None, description='Fila del archivo, para el reporte')


class PrevisualizarEntrada(BaseModel):
    filas: list[FilaEntrada] = Field(min_length=1)
    archivo: str | None = Field(default=None, max_length=200)


class FilaSalida(BaseModel):
    fila_numero: int
    id_externo: str | None
    resultado: Resultado
    caso_id: int | None
    detalle: str | None


class ImportacionSalida(BaseModel):
    id: int
    origen: str
    archivo_nombre: str | None
    filas_totales: int
    nuevos: int
    actualizados: int
    sin_cambios: int
    conflictos: int
    rechazados: int
    estado: EstadoImportacion
    iniciada_en: datetime
    aplicada_en: datetime | None
    filas: list[FilaSalida] = []


class AplicarSalida(BaseModel):
    importacion_id: int
    actualizados: int
    conflictos: int
    por_vincular: int = Field(
        description='Solicitudes que no tienen trámite: se vinculan a mano (RF-036)')
    saltados: int


class VincularEntrada(BaseModel):
    caso_id: int
    numero_solicitud: str = Field(min_length=1, max_length=80)


class CandidatoSalida(BaseModel):
    caso_id: int
    solicitante: str
    fuente: str


class EstadoSincronizacion(BaseModel):
    """RF-035: de acá lee la alerta de fuente desactualizada."""
    origen: str
    ultima: datetime | None
    resultado: Literal['ok', 'error'] | None
    detalle: str | None
    intentos: int
    ultima_exitosa: datetime | None
    horas_desde_la_ultima_exitosa: float | None


class ConflictoSalida(BaseModel):
    id: int
    caso_id: int | None
    campo: str
    valor_visanow: str | None
    valor_saas: str | None
    estado: str
    detectado_en: datetime


class ResolverEntrada(BaseModel):
    decision: DecisionConflicto
