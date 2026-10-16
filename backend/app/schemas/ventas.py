from datetime import date, datetime

from pydantic import BaseModel, Field


class CotizarEntrada(BaseModel):
    servicio_id: int
    personas: int = Field(default=1, ge=1, le=20)
    descuento: float = Field(default=0, ge=0)
    valor_pactado: float | None = Field(default=None, ge=0,
                                        description='El precio negociado, si no es el de lista')
    fecha: date | None = Field(default=None, description='Para cotizar con la tarifa de ese día')


class CotizacionSalida(BaseModel):
    servicio_id: int
    servicio: str
    personas: int
    valor_lista: float
    descuento: float
    valor_pactado: float
    moneda: str
    tarifa_id: int | None
    vigente_desde: date | None
    tasa_consular_valor: float | None
    tasa_consular_moneda: str | None
    tasa_consular_total: float | None = Field(
        default=None, description='La paga el cliente directo al consulado: no suma al pactado')
    avisos: list[str] = []


class ConvertirEntrada(BaseModel):
    servicio_id: int | None = Field(default=None, description='Si no se dice, el de la oportunidad')
    personas: int | None = Field(default=None, ge=1, le=20)
    descuento: float = Field(default=0, ge=0)
    valor_pactado: float | None = Field(default=None, ge=0)
    fecha_venta: date | None = None
    solicitantes_ids: list[int] | None = Field(
        default=None, description='Quiénes viajan. Si no se dice, todas las personas del cliente')
    pais_id: int | None = None
    observaciones: str | None = None
    abrir_tramites: bool = Field(default=True,
                                 description='Abre un trámite por persona que viaja (RF-014)')


class CasoDeVenta(BaseModel):
    id: int
    solicitante_id: int
    solicitante: str


class VentaSalida(BaseModel):
    id: int
    cliente_id: int
    cliente: str
    oportunidad_id: int | None
    servicio_id: int
    servicio: str
    fecha_venta: date
    cantidad_solicitantes: int
    valor_lista: float
    descuento: float
    valor_pactado: float
    moneda: str
    vendedor_id: int | None
    observaciones: str | None
    creado_en: datetime
    casos: list[CasoDeVenta] = []


class CopiaDeVenta(BaseModel):
    """Una de las fichas que parecen ser la misma venta."""
    negocio_id: int
    origen: str = Field(description='La hoja del Excel de la que salió, o «creada en el sistema»')
    origen_archivo: str | None = None
    origen_fila: int | None = None
    pagos: int
    pagado: float
    tramites: int


class VentaRepetida(BaseModel):
    """Un grupo de ventas que parecen ser la misma anotada dos veces (RF-040).

    Mismo cliente, mismo servicio, misma fecha y mismo valor. Viene de la carga:
    la idempotencia es por `(archivo, hoja, fila)`, así que el mismo negocio
    anotado en dos hojas del mismo libro entró dos veces.

    Trae los pagos de cada copia porque sin eso no se puede decidir: en las 16
    que dejó la carga los pagos están repartidos entre las dos, así que no se
    trata de borrar una y ya.
    """
    cliente_id: int
    cliente: str | None = None
    servicio: str | None = None
    fecha_venta: date | None = None
    valor_pactado: float
    moneda: str | None = None
    copias: list[CopiaDeVenta]


class AnularVentaEntrada(BaseModel):
    motivo: str = Field(min_length=3, max_length=400,
                        description='Qué cambió y por qué: es lo que explica el movimiento '
                                    'en los totales del mes')
