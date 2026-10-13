"""Lo que la pantalla de rentabilidad recibe (RF-054).

Cada cifra viaja por separado a proposito. Mandar solo el margen obligaria a
creerlo: con las piezas a la vista, quien lo lee puede rehacer la resta y
reclamar la que no cuadre.
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

OrdenVentas = Literal['peores', 'mejores', 'recientes']


class MargenSalida(BaseModel):
    clave: str = Field(description='Id del servicio, primer dia del mes o id de la venta')
    etiqueta: str
    ventas: int
    ingreso_bruto: float = Field(description='Pagos confirmados, sin la tasa consular')
    reembolsos: float = Field(description='Plata que entro y se le devolvio al cliente')
    costo_medio: float = Field(description='Lo que se llevo la pasarela o el banco')
    ingreso_neto: float = Field(
        description='Ingreso bruto menos los reembolsos y el costo del medio de pago')
    comisiones: float
    gastos_directos: float = Field(description='Gastos cargados a la venta o a sus tramites')
    costo_servicio: float = Field(description='Lo que cuesta atender el servicio')
    margen: float = Field(description='Ingreso neto menos comisiones, gastos directos y costos')
    margen_pct: float | None = Field(
        description='Nulo cuando no ha entrado plata: un porcentaje sobre cero no dice nada')
    recaudo_terceros: float = Field(
        description='Tasa consular recaudada. No es ingreso de la agencia y no entra al margen')


class MargenVentaSalida(MargenSalida):
    negocio_id: int
    fecha_venta: date
    servicio: str
    es_recaudo_de_terceros: bool
    vendedor: str | None
    valor_pactado: float = Field(description='Lo acordado, para leer el ingreso en contexto')
    saldo: float = Field(description='Lo que el cliente todavia debe')


class InformeSalida(BaseModel):
    total: MargenSalida
    por_servicio: list[MargenSalida]
    por_periodo: list[MargenSalida] = Field(description='Un mes por fila, por fecha de venta')


class PaginaVentas(BaseModel):
    total: int
    pagina: int
    tamano: int
    items: list[MargenVentaSalida]
