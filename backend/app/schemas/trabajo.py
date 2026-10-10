"""Tareas y alertas: lo que hay que hacer y lo que se está pasando."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

EstadoTarea = Literal['pendiente', 'en_curso', 'hecha', 'cancelada']
Prioridad = Literal['baja', 'media', 'alta']
EstadoAlerta = Literal['nueva', 'vista', 'resuelta', 'pospuesta']
Severidad = Literal['baja', 'media', 'alta']


class TareaCrear(BaseModel):
    titulo: str = Field(min_length=3, max_length=200)
    descripcion: str | None = None
    caso_id: int | None = None
    negocio_id: int | None = None
    oportunidad_id: int | None = None
    cliente_id: int | None = Field(
        default=None,
        description='Al menos uno de los cuatro: una tarea suelta no se puede retomar')
    responsable_id: int | None = Field(default=None, description='Si no se dice, quien la crea')
    prioridad: Prioridad = 'media'
    vence_en: date | datetime | None = Field(
        default=None, description='En hora de Bogotá. Sin hora, vence al final del día')


class TareaCambiar(BaseModel):
    titulo: str | None = Field(default=None, min_length=3, max_length=200)
    descripcion: str | None = None
    estado: EstadoTarea | None = None
    responsable_id: int | None = None
    prioridad: Prioridad | None = None
    vence_en: date | datetime | None = None


class TareaSalida(BaseModel):
    id: int
    titulo: str
    descripcion: str | None
    estado: EstadoTarea
    prioridad: Prioridad
    vence_en: datetime | None
    vencida: bool = Field(description='Ya pasó su fecha y sigue abierta')
    caso_id: int | None
    negocio_id: int | None
    oportunidad_id: int | None
    cliente_id: int | None
    cliente: str | None = None
    responsable_id: int
    responsable: str | None
    origen: Literal['manual', 'automatica']
    cerrada_en: datetime | None
    creado_en: datetime


class PaginaTareas(BaseModel):
    total: int
    pagina: int
    tamano: int
    items: list[TareaSalida]


class ResumenTareas(BaseModel):
    abiertas: int
    vencidas: int
    vencen_hoy: int
    alta_prioridad: int


class AlertaSalida(BaseModel):
    id: int
    tipo: str = Field(description='Código del tipo configurado en la matriz')
    tipo_nombre: str
    severidad: Severidad
    mensaje: str
    estado: EstadoAlerta
    caso_id: int | None
    negocio_id: int | None
    oportunidad_id: int | None
    cita_id: int | None
    destinatario_id: int | None
    vence_en: datetime | None
    pospuesta_hasta: datetime | None
    generada_en: datetime
    resuelta_en: datetime | None


class PaginaAlertas(BaseModel):
    total: int
    pagina: int
    tamano: int
    items: list[AlertaSalida]


class CambiarAlerta(BaseModel):
    estado: EstadoAlerta
    hasta: datetime | None = Field(
        default=None,
        description='Obligatorio al posponer: una alerta pospuesta sin fecha no vuelve nunca')


class GenerarEntrada(BaseModel):
    codigos: list[str] | None = Field(
        default=None, description='Solo estos tipos. Si no se dice, todos los activos')


class GenerarSalida(BaseModel):
    creadas: int
    por_tipo: dict[str, int]
    tipos_sin_regla: list[str] = Field(
        description='Configurados pero todavía sin regla que los evalúe')


class ResumenAlertas(BaseModel):
    alta: int
    media: int
    baja: int
    total: int


class TipoAlertaSalida(BaseModel):
    """La matriz configurable (RF-062): cambiarla es editar una fila."""
    id: int
    codigo: str
    nombre: str
    entidad: str
    anticipacion_valor: int = Field(
        description='Positivo avisa antes del hecho; negativo, después')
    anticipacion_unidad: Literal['horas', 'dias', 'dias_habiles']
    repeticiones: list[int]
    severidad: Severidad
    canal: str
    destinatario_rol_id: int | None = None
    destinatario_rol: str | None = Field(
        default=None, description='A quién le llega: el nombre del rol, para mostrarlo')
    activo: bool
    tiene_regla: bool = Field(description='Si ya existe la consulta que lo evalúa')


class CambiarTipoAlerta(BaseModel):
    """Lo que la administradora puede ajustar de un tipo de alerta (RF-062).

    El código, el nombre y la entidad no están: identifican la regla que la
    evalúa y cambiarlos la dejaría sin evaluar. Lo demás es la decisión del
    negocio sobre cuándo avisar, a quién y con qué urgencia.
    """
    anticipacion_valor: int | None = Field(
        default=None, ge=-365, le=365,
        description='Positivo avisa antes del hecho; negativo, después')
    anticipacion_unidad: Literal['horas', 'dias', 'dias_habiles'] | None = None
    repeticiones: list[int] | None = Field(
        default=None, max_length=10,
        description='A los cuántos días vuelve a avisar: [7, 15] insiste dos veces')
    severidad: Severidad | None = None
    canal: Literal['interna', 'correo', 'whatsapp'] | None = None
    destinatario_rol_id: int | None = None
    activo: bool | None = None
