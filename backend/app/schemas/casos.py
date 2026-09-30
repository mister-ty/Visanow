from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Fuente = Literal['saas', 'manual', 'hibrido']
Resultado = Literal['aprobada', 'negada', 'proceso_administrativo', 'cancelado', 'no_continuo']
TipoCita = Literal['cas', 'biometria', 'entrevista', 'radicacion', 'preparacion', 'entrega', 'otra']
EstadoCita = Literal['pendiente', 'programada', 'confirmada', 'reprogramada', 'realizada', 'cancelada']


class CasoCrear(BaseModel):
    solicitante_id: int
    pais_id: int
    tipo_visa_id: int | None = None
    modalidad_id: int | None = None
    sede_id: int | None = None
    responsable_id: int | None = None
    negocio_id: int | None = Field(default=None, description='La venta, si ya está registrada')
    id_externo: str | None = Field(default=None, max_length=60, description='N.º de solicitud del SaaS')
    fuente: Fuente | None = None
    proxima_accion: str | None = Field(default=None, max_length=200)
    proxima_accion_fecha: date | None = None


class CasoEditar(BaseModel):
    pais_id: int | None = None
    tipo_visa_id: int | None = None
    modalidad_id: int | None = None
    sede_id: int | None = None
    responsable_id: int | None = None
    negocio_id: int | None = None
    proxima_accion: str | None = Field(default=None, max_length=200)
    proxima_accion_fecha: date | None = None


class CasoSalida(BaseModel):
    id: int
    solicitante_id: int
    solicitante: str
    estado: str
    estado_nombre: str
    es_final: bool
    responsable: str | None
    responsable_id: int | None
    pais: str | None
    fuente: Fuente
    id_externo: str | None
    resultado: Resultado | None
    proxima_accion: str | None
    proxima_accion_fecha: date | None
    dias_sin_movimiento: int
    riesgo: Literal['ninguno', 'bajo', 'medio', 'alto']
    sin_venta: bool
    ultima_actividad_en: datetime


class EstadoPosible(BaseModel):
    codigo: str
    nombre: str


class CitaSalida(BaseModel):
    id: int
    tipo: TipoCita
    sede_id: int | None
    inicia_en: datetime
    zona_horaria: str
    estado: EstadoCita
    observaciones: str | None


class ItemChecklist(BaseModel):
    item_id: int
    codigo: str
    nombre: str
    obligatorio: bool
    cumplido: bool


class CasoDetalle(CasoSalida):
    pais_id: int | None
    tipo_visa_id: int | None
    modalidad_id: int | None
    sede_id: int | None
    negocio_id: int | None
    etapa_saas: str | None
    resultado_fecha: date | None
    resultado_nota: str | None
    creado_en: datetime
    citas: list[CitaSalida] = []
    checklist: list[ItemChecklist] = []
    estados_posibles: list[EstadoPosible] = []


class PaginaCasos(BaseModel):
    total: int
    pagina: int
    tamano: int
    items: list[CasoSalida]


class ResumenEstado(BaseModel):
    codigo: str
    nombre: str
    total: int


class CambioEstado(BaseModel):
    codigo_destino: str
    motivo: str | None = None
    cambios: CasoEditar | None = Field(default=None, description='Datos que faltan para poder avanzar')
    resultado: Resultado | None = None
    resultado_fecha: date | None = None
    forzar: bool = Field(default=False, description='Saltarse el orden de los estados. Exige motivo y '
                                                    'permiso de administradora; queda como excepción.')


class ResultadoEntrada(BaseModel):
    resultado: Resultado
    fecha: date | None = None
    nota: str | None = None


class CitaCrear(BaseModel):
    tipo: TipoCita
    inicia_en: datetime
    sede_id: int | None = None
    zona_horaria: str = 'America/Bogota'
    observaciones: str | None = None


class CitaEditar(BaseModel):
    estado: EstadoCita | None = None
    inicia_en: datetime | None = None
    sede_id: int | None = None
    observaciones: str | None = None


class MarcarItem(BaseModel):
    cumplido: bool
    observacion: str | None = None


class HistorialSalida(BaseModel):
    campo: str
    valor_anterior: str | None
    valor_nuevo: str | None
    usuario: str | None
    observacion: str | None
    ocurrido_en: datetime
