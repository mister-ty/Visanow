from datetime import date, datetime
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


class OportunidadEnFicha(BaseModel):
    id: int
    estado: str
    servicio: str | None
    pais: str | None
    valor_estimado: float | None
    proxima_accion: str | None
    proxima_accion_fecha: date | None
    creada_en: datetime


class VentaEnFicha(BaseModel):
    id: int
    servicio: str | None
    fecha_venta: date
    personas: int
    valor_pactado: float
    pagado: float
    saldo: float
    estado_financiero: str


class PagoEnFicha(BaseModel):
    id: int
    negocio_id: int | None
    fecha: date
    monto: float
    medio: str | None
    referencia: str | None


class DineroEnFicha(BaseModel):
    """La plata del cliente, o solo si está al día, según quién pregunte.

    Operaciones necesita saber si el cliente pagó el anticipo para arrancar el
    trámite, y no tiene por qué ver cuánto (respuesta de la administradora del
    29/09). Por eso `al_dia` se responde con `pagos.estado` y los montos con
    `pagos.ver`: son dos permisos distintos y aquí se notan.
    """
    ve_montos: bool
    al_dia: bool | None = Field(
        default=None, description='Si no debe nada vencido. Sin montos, para quien no los ve')
    ventas: list[VentaEnFicha] = []
    pagos: list[PagoEnFicha] = []
    total_pactado: float | None = None
    total_pagado: float | None = None
    saldo: float | None = None


class TareaEnFicha(BaseModel):
    id: int
    titulo: str
    estado: str
    prioridad: str
    vence_en: date | None
    responsable: str | None


class AlertaEnFicha(BaseModel):
    id: int
    tipo: str
    mensaje: str
    severidad: str
    estado: str
    creada_en: datetime


class DocumentoEnFicha(BaseModel):
    id: int
    nombre: str
    almacenamiento: str
    url: str | None
    mime: str | None
    restringido: bool
    sobre: str = Field(description='De qué cuelga: el cliente, una persona o un trámite')
    creado_en: datetime


class Ficha360(BaseModel):
    """Todo lo que estaba repartido entre siete pantallas, en una sola respuesta.

    Cada bloque viene vacío cuando el rol no puede verlo, y el campo `ve_*` lo
    dice: la pantalla distingue «no hay» de «no le corresponde», que no son lo
    mismo y confundirlos hace que alguien crea que un cliente no tiene ventas.
    """
    cliente: ClienteDetalle
    resumen: ResumenFicha
    tramites: list[CasoSalida] = []
    citas: list[CitaProxima] = []
    cronologia: list[SucesoSalida] = []
    oportunidades: list[OportunidadEnFicha] = []
    dinero: DineroEnFicha
    tareas: list[TareaEnFicha] = []
    alertas: list[AlertaEnFicha] = []
    documentos: list[DocumentoEnFicha] = []
    ve_tramites: bool = Field(description='False si el rol no tiene permiso de ver trámites')
    ve_oportunidades: bool = False
    ve_trabajo: bool = Field(default=False, description='Tareas y alertas')


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
    tipo: Literal['cliente', 'solicitante', 'tramite', 'pago']
    id: int
    titulo: str
    detalle: str
    ruta: str
    coincidio_por: str
