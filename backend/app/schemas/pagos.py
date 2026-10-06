from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

TipoAjuste = Literal['reembolso', 'cargo', 'descuento', 'condonacion']
EstadoPago = Literal['confirmado', 'pendiente', 'no_identificado', 'reversado', 'duplicado']


class PagoCrear(BaseModel):
    negocio_id: int | None = Field(default=None,
                                   description='Si no se sabe, queda en la bandeja sin asignar')
    fecha: date | None = None
    monto_bruto: float = Field(gt=0)
    costo_medio: float = Field(default=0, ge=0, description='Lo que cobra la pasarela o el banco')
    moneda: str = 'COP'
    medio_pago_id: int | None = None
    banco_cuenta_id: int | None = None
    referencia: str | None = Field(default=None, max_length=80)
    comprobante_url: str | None = None
    pagador_nombre: str | None = Field(default=None, max_length=160,
                                       description='Quién consignó, si no es el cliente')
    observacion: str | None = None


class PagoSalida(BaseModel):
    id: int
    negocio_id: int | None
    fecha: date
    monto_bruto: float
    costo_medio: float
    monto_neto: float
    moneda: str
    medio_pago_id: int | None
    medio_pago: str | None
    banco_cuenta_id: int | None
    referencia: str | None
    estado: EstadoPago
    pagador_nombre: str | None
    observacion: str | None
    creado_en: datetime


class PaginaPagos(BaseModel):
    total: int
    pagina: int
    tamano: int
    items: list[PagoSalida]


class AsignarPago(BaseModel):
    negocio_id: int


class CambiarEstadoPago(BaseModel):
    estado: EstadoPago
    observacion: str | None = None


class CuotaSalida(BaseModel):
    numero: int
    concepto: str
    monto: float
    fecha_pactada: date


class PlanCuotas(BaseModel):
    reparto: list[int] | None = Field(default=None,
                                      description='Porcentajes que suman 100. Por defecto [20, 80]')
    plazo_dias: int | None = Field(default=None, ge=0,
                                   description='Días para el saldo. Por defecto, el del catálogo')


class AjusteCrear(BaseModel):
    tipo: TipoAjuste
    monto: float = Field(gt=0, description='Siempre en positivo: el tipo decide el signo')
    motivo: str = Field(min_length=3, max_length=400)
    fecha: date | None = None


class AjusteSalida(BaseModel):
    id: int
    tipo: TipoAjuste
    monto: float = Field(description='Con signo: positivo sube la deuda, negativo la baja')
    motivo: str
    fecha: date
    autorizado_por: int


class EstadoFinancieroSalida(BaseModel):
    negocio_id: int
    valor_pactado: float
    total_pagado: float
    neto_recibido: float
    ajustes: float
    saldo: float
    estado_financiero: str
    moneda: str
    cuotas: list[CuotaSalida] = []
    pagos: list[PagoSalida] = []
    ajustes_detalle: list[AjusteSalida] = []


class FilaCarteraSalida(BaseModel):
    negocio_id: int
    cliente_id: int
    cliente: str
    servicio: str
    fecha_venta: date
    vendedor: str | None
    valor_pactado: float
    total_pagado: float
    saldo: float
    exigible_hoy: float
    vencido: float
    por_vencer: float
    dias_vencido: int
    moneda: str


class PaginaCartera(BaseModel):
    total: int
    suma_saldo: float
    pagina: int
    tamano: int
    items: list[FilaCarteraSalida]


class ResumenCartera(BaseModel):
    vendido: float
    cobrado: float
    cartera: float
    vencido: float
    ventas_con_saldo: int


class PorEstado(BaseModel):
    estado: str
    cuantas: int
    saldo: float
