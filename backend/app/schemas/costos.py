from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

EstadoGasto = Literal['pagado', 'pendiente', 'anulado']
EstadoComision = Literal['provisional', 'causada', 'liquidada', 'anulada']


class GastoCrear(BaseModel):
    categoria_id: int
    concepto: str = Field(min_length=3, max_length=200)
    monto: float = Field(gt=0)
    fecha: date | None = None
    moneda: str = 'COP'
    negocio_id: int | None = Field(default=None,
                                   description='Lo vuelve un gasto directo de la venta')
    caso_id: int | None = Field(default=None,
                                description='Lo vuelve un gasto directo del trámite')
    proveedor_id: int | None = None
    medio_pago_id: int | None = None
    banco_cuenta_id: int | None = None
    comprobante_url: str | None = None
    observacion: str | None = None
    estado: EstadoGasto = 'pagado'


class GastoSalida(BaseModel):
    id: int
    categoria_id: int
    categoria: str
    concepto: str
    fecha: date
    monto: float
    moneda: str
    estado: EstadoGasto
    negocio_id: int | None
    caso_id: int | None
    es_directo: bool = Field(description='Se le puede cargar a una venta o a un trámite')
    observacion: str | None
    creado_en: datetime


class PaginaGastos(BaseModel):
    total: int
    suma: float
    pagina: int
    tamano: int
    items: list[GastoSalida]


class AnularEntrada(BaseModel):
    motivo: str = Field(min_length=3, max_length=400)


class GastoPorCategoria(BaseModel):
    categoria: str
    cuantos: int
    total: float


class ComisionSalida(BaseModel):
    id: int
    negocio_id: int
    vendedor_id: int
    vendedor: str | None
    base_calculo: float
    monto: float
    estado: EstadoComision
    periodo: date | None
    porcentaje_aplicado: float | None
    escalon: str | None = Field(default=None, description='«base» o «meta»')
    explicacion: str | None = Field(default=None, description='Por qué se calculó así')
    liquidacion_id: int | None
    creado_en: datetime


class LiquidarEntrada(BaseModel):
    vendedor_id: int
    periodo: date = Field(description='Cualquier día del mes a liquidar')
    observaciones: str | None = None


class LiquidacionSalida(BaseModel):
    id: int
    vendedor_id: int
    vendedor: str | None
    periodo: date
    total: float
    cantidad: int
    estado: str
    observaciones: str | None
    creada_en: datetime
    pagada_en: datetime | None
    comisiones: list[ComisionSalida] = []
