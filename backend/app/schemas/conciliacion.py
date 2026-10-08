from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

EstadoMovimiento = Literal['sin_conciliar', 'conciliado', 'parcial',
                           'duplicado', 'reversado', 'descartado']


class MovimientoEntrada(BaseModel):
    """Una línea del extracto. El nombre de quien consigna no se pide para
    cruzar: se guarda como pista, porque muchas veces no es el del cliente."""
    fecha: date
    valor: float = Field(description='Positivo: es plata que entró')
    banco: str = Field(min_length=2, max_length=60)
    descripcion: str | None = Field(default=None, max_length=300)
    referencia: str | None = Field(default=None, max_length=120)
    moneda: str = 'COP'
    banco_cuenta_id: int | None = None
    nota_cliente: str | None = Field(
        default=None, max_length=200,
        description='Lo que se anotaba a mano en la columna CLIENTE del Excel')
    nota_abono: str | None = Field(default=None, max_length=60)
    observacion: str | None = None
    fila: int | None = Field(default=None, description='Fila del archivo de origen')


class ImportarEntrada(BaseModel):
    movimientos: list[MovimientoEntrada] = Field(min_length=1)
    archivo: str | None = Field(default=None, max_length=120)
    hoja: str | None = Field(default=None, max_length=60)


class ImportarSalida(BaseModel):
    leidos: int
    nuevos: int
    repetidos: int = Field(description='Ya estaban: importar dos veces no duplica')
    sin_fecha: int
    sin_valor: int


class MovimientoSalida(BaseModel):
    id: int
    banco: str
    fecha: date
    valor: float
    moneda: str
    descripcion: str | None
    referencia: str | None
    estado: EstadoMovimiento
    pago_id: int | None
    duplicado_de_id: int | None = None
    negocio_id: int | None = None
    cliente: str | None = None
    motivo_descarte: str | None
    nota_cliente: str | None
    nota_abono: str | None
    conciliado_en: datetime | None
    creado_en: datetime


class PaginaMovimientos(BaseModel):
    total: int
    suma: float
    pagina: int
    tamano: int
    items: list[MovimientoSalida]


class CandidatoSalida(BaseModel):
    pago_id: int
    negocio_id: int | None
    cliente: str | None
    fecha: date
    monto: float
    dias_de_diferencia: int
    exacto: bool = Field(description='Mismo día que el movimiento del banco')


class SugerenciasSalida(BaseModel):
    movimiento: MovimientoSalida
    candidatos: list[CandidatoSalida]
    sin_duda: bool = Field(
        description='Un solo candidato y del mismo día: se puede cuadrar sin preguntar')


class ConciliarEntrada(BaseModel):
    """Contra qué se cuadra: un pago que ya existe, o la venta a la que hay que
    abonarle, y entonces el pago nace del movimiento del banco."""
    pago_id: int | None = None
    negocio_id: int | None = None

    @model_validator(mode='after')
    def uno_u_otro(self):
        if (self.pago_id is None) == (self.negocio_id is None):
            raise ValueError('Diga un pago o una venta, no los dos ni ninguno.')
        return self


class ParcialEntrada(BaseModel):
    pago_id: int = Field(description='El pago que este movimiento cubre solo en parte')


class DuplicadoEntrada(BaseModel):
    duplicado_de_id: int = Field(description='El movimiento bueno, del que este es repetido')


class ReversadoEntrada(BaseModel):
    motivo: str = Field(min_length=3, max_length=300)


class DescartarEntrada(BaseModel):
    motivo: str = Field(min_length=3, max_length=300,
                        description='Por qué este movimiento no es plata de un cliente')


class CruceAutomaticoEntrada(BaseModel):
    desde: date | None = None
    hasta: date | None = None


class CruceAutomaticoSalida(BaseModel):
    cuadrados: int
    ambiguos: int = Field(description='Calzan con más de un pago: decide una persona')
    sin_candidato: int


class EstadoResumen(BaseModel):
    cuantos: int
    total: float


class ResumenSalida(BaseModel):
    sin_conciliar: EstadoResumen
    conciliado: EstadoResumen
    parcial: EstadoResumen
    duplicado: EstadoResumen
    reversado: EstadoResumen
    descartado: EstadoResumen
