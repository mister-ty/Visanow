from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Fuente = Literal['saas', 'manual', 'hibrido']
Resultado = Literal['aprobada', 'negada', 'proceso_administrativo', 'cancelado', 'no_continuo']
TipoCita = Literal['cas', 'biometria', 'entrevista', 'radicacion', 'preparacion', 'entrega', 'otra']
EstadoCita = Literal['pendiente', 'programada', 'confirmada', 'reprogramada', 'realizada', 'cancelada']
NivelRiesgo = Literal['ninguno', 'bajo', 'medio', 'alto']
#: Las dos preguntas distintas del tablero: qué lleva más tiempo sin moverse y
#: qué lleva más tiempo abierto.
OrdenTablero = Literal['quieto', 'antiguedad']

COLABORADORES = Field(default_factory=list,
                      description='Los demás que trabajan el trámite (RF-026). El responsable '
                                  'sigue siendo uno: un trámite con tres dueños no tiene ninguno')


class CasoCrear(BaseModel):
    solicitante_id: int
    pais_id: int
    tipo_visa_id: int | None = None
    modalidad_id: int | None = None
    sede_id: int | None = None
    responsable_id: int | None = None
    colaboradores: list[int] = COLABORADORES
    negocio_id: int | None = Field(default=None, description='La venta, si ya está registrada')
    id_externo: str | None = Field(default=None, max_length=60, description='N.º de solicitud del SaaS')
    fuente: Fuente | None = None
    proxima_accion: str | None = Field(default=None, max_length=200)
    proxima_accion_fecha: date | None = None


class CasoLoteCrear(BaseModel):
    """El alta de una familia en una sola pasada (RF-020).

    La venta se cierra para el grupo y el trámite se abre por persona, así que
    los mismos cinco campos se repetían una vez por cada quien que viaja.

    No lleva `id_externo` a propósito: una solicitud del SaaS es de un trámite y
    de uno solo, así que no hay un número que valga para toda la familia
    (RF-032). Se le pone después a cada uno, al vincularlo.
    """
    solicitantes: list[int] = Field(min_length=1,
                                    description='Las personas que viajan: un trámite por cada una')
    pais_id: int
    tipo_visa_id: int | None = None
    modalidad_id: int | None = None
    sede_id: int | None = None
    responsable_id: int | None = None
    colaboradores: list[int] = COLABORADORES
    negocio_id: int | None = Field(default=None, description='La venta, si ya está registrada')
    proxima_accion: str | None = Field(default=None, max_length=200)
    proxima_accion_fecha: date | None = None


class FuenteEntrada(BaseModel):
    """Marcar de dónde viene el trámite: SaaS, manual o híbrido (RF-021)."""
    fuente: Fuente
    id_externo: str | None = Field(default=None, max_length=60,
                                   description='N.º de solicitud del SaaS. Obligatorio si el '
                                               'trámite es del SaaS o híbrido; si se omite, se '
                                               'conserva el que ya tenía')


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
    servicio: str | None = Field(default=None, description='El servicio vendido, si hay venta')
    fuente: Fuente
    id_externo: str | None
    resultado: Resultado | None
    proxima_accion: str | None
    proxima_accion_fecha: date | None
    creado_en: datetime = Field(description='Fecha de entrada del trámite')
    antiguedad_dias: int = Field(description='Días que lleva abierto, desde que entró. No es '
                                             'lo mismo que los días sin movimiento')
    dias_sin_movimiento: int
    riesgo: NivelRiesgo
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
    titulo: str = Field(description='Lo que pasó, en español y con los catálogos resueltos')
    campo: str
    valor_anterior: str | None
    valor_nuevo: str | None
    usuario: str | None
    observacion: str | None
    ocurrido_en: datetime


class ColaboradorSalida(BaseModel):
    """Alguien que trabaja en el trámite sin ser el responsable (RF-026)."""
    usuario_id: int
    nombre: str
    rol_id: int | None = None
    agregado_en: datetime
    agregado_por: int | None = None


class ColaboradorEntrada(BaseModel):
    usuario_id: int
