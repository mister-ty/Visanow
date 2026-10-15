from datetime import date, datetime

from pydantic import BaseModel, Field

#: Cuándo llegó el lead, que no es cuándo se digitó: un lead transcrito de la
#: hoja de pauta o del formulario de Google se escribe días después. Vacía
#: significa hoy. Quién lo digitó y a qué hora queda en la auditoría.
FECHA_DE_LLEGADA = 'Cuándo llegó el lead. Vacía: hoy'


class OportunidadCrear(BaseModel):
    cliente_id: int
    fecha: date | None = Field(default=None, description=FECHA_DE_LLEGADA)
    servicio_id: int | None = Field(default=None, description='Qué le interesa')
    pais_id: int | None = None
    canal_id: int | None = Field(default=None, description='Por dónde llegó')
    campania_id: int | None = Field(default=None, description='La campaña del catálogo')
    campania: str | None = Field(default=None, max_length=120,
                                 description='La campaña o el influencer, si no está en catálogo')
    referido_por_cliente_id: int | None = Field(default=None, description='Quién lo recomendó')
    asesor_id: int | None = Field(default=None, description='Si no se dice, queda a nombre de quien lo crea')
    valor_estimado: float | None = None
    proxima_accion: str = Field(min_length=3, max_length=200)
    proxima_accion_fecha: date | None = None


class OportunidadEditar(BaseModel):
    fecha: date | None = Field(default=None, description=FECHA_DE_LLEGADA)
    servicio_id: int | None = None
    pais_id: int | None = None
    canal_id: int | None = None
    campania_id: int | None = None
    campania: str | None = Field(default=None, max_length=120)
    referido_por_cliente_id: int | None = None
    asesor_id: int | None = None
    valor_estimado: float | None = None
    proxima_accion: str | None = Field(default=None, max_length=200)
    proxima_accion_fecha: date | None = None


class OportunidadSalida(BaseModel):
    id: int
    cliente_id: int
    cliente: str
    estado: str
    estado_nombre: str
    es_cierre: bool
    asesor: str | None
    asesor_id: int | None
    servicio_id: int | None
    pais_id: int | None
    canal_id: int | None
    campania_id: int | None
    campania: str | None
    # De dónde salió el cliente: el canal, la campaña y quién lo recomendó. Es
    # la respuesta a «fuente» del RF-010; la decisión de no abrir una columna
    # aparte está escrita en services/oportunidades.py.
    referido_por_cliente_id: int | None
    referido_por: str | None = Field(default=None, description='El nombre de quien lo recomendó')
    valor_estimado: float | None
    proxima_accion: str | None
    proxima_accion_fecha: date | None
    dias_sin_contacto: int
    ultimo_contacto_en: datetime | None
    motivo_perdida_id: int | None
    # El motivo con nombre y con la nota: un «3» no explica por qué se perdió un
    # negocio, y es lo único que queda de ese negocio (RF-015).
    motivo_perdida: str | None = None
    motivo_perdida_nombre: str | None = None
    motivo_perdida_nota: str | None = None
    creado_en: datetime = Field(description='Cuándo llegó el lead')
    cerrado_en: datetime | None


class PaginaOportunidades(BaseModel):
    total: int
    pagina: int
    tamano: int
    items: list[OportunidadSalida]


class PasoEmbudo(BaseModel):
    codigo: str
    nombre: str
    orden: int
    es_cierre: bool
    cuantas: int
    valor_estimado: float


class MoverOportunidad(BaseModel):
    codigo_destino: str
    motivo_perdida: str | None = Field(default=None, description='Obligatorio al cerrar como perdida')
    nota: str | None = None
    proxima_accion: str | None = Field(default=None, max_length=200,
                                       description='Obligatoria mientras siga abierta')


class ContactoOportunidad(BaseModel):
    proxima_accion: str | None = Field(default=None, max_length=200)
    proxima_accion_fecha: date | None = None
