"""Consultar la auditoría: quién hizo qué, cuándo y sobre qué (RF-076).

La auditoría se escribía desde el primer día y hasta hoy nadie podía leerla.
Eso es medio control: toda la política de datos dice «el día que un archivo con
clientes aparezca donde no debía, se mira quién lo sacó», y hasta ahora había
que entrar a la base de datos para mirarlo.

Lo que no muestra, porque no está guardado, son los datos que identifican a una
persona: la auditoría anota que cambió el teléfono de un cliente, no cuál era.
La tabla es inalterable (RNF-05), así que lo que entrara ahí sobreviviría a
cualquier anonimización posterior (RNF-09). Ver `app/services/auditoria.py`.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import requiere
from app.db.session import get_db
from app.models.esquema import Auditoria, Usuarios
from app.services.auditoria import sin_datos_personales

router = APIRouter(prefix='/auditoria', tags=['auditoría'])


def _servible(entidad: str, d: dict | None) -> dict | None:
    """Oculta los datos personales OTRA VEZ, al momento de servir.

    No sobra: hasta hoy la auditoría guardaba el registro completo, y esas filas
    siguen ahí -la tabla es inalterable, no se pueden limpiar-. Si el visor se
    fiara de que lo guardado ya viene limpio, abrirlo sería la forma de
    recuperar el nombre y el teléfono de cualquiera, incluida una persona ya
    anonimizada.

    Lo mismo vale hacia adelante: si algún día un servicio audita saltándose el
    ayudante, el que sirve los datos no tiene por qué confiar en eso.
    """
    return sin_datos_personales(entidad, d)


class RegistroSalida(BaseModel):
    id: int
    ocurrido_en: datetime
    usuario_id: int | None
    usuario: str | None = Field(description='El nombre vive en la tabla de usuarios, '
                                            'no en el registro')
    operacion: str
    entidad: str
    entidad_id: int | None
    ip: str | None
    campos: list[str] = Field(description='Qué cambió, para leer la lista de un vistazo')
    antes: dict | None
    despues: dict | None


class PaginaAuditoria(BaseModel):
    total: int
    pagina: int
    tamano: int
    items: list[RegistroSalida]


class FiltrosSalida(BaseModel):
    """Lo que de verdad hay registrado, para que los filtros no ofrezcan vacíos."""
    entidades: list[str]
    operaciones: list[str]


@router.get('/filtros', response_model=FiltrosSalida)
def filtros(_: Usuarios = Depends(requiere('auditoria.ver')),
            db: Session = Depends(get_db)):
    """Las entidades y operaciones que existen en la tabla.

    Se sacan de los datos y no de una lista escrita a mano: una lista escrita a
    mano se queda vieja el día que aparece una entidad nueva, y el filtro que
    no se ofrece es un registro que nadie va a encontrar.
    """
    return FiltrosSalida(
        entidades=[r for (r,) in db.execute(
            select(Auditoria.entidad).distinct().order_by(Auditoria.entidad))],
        operaciones=[r for (r,) in db.execute(
            select(Auditoria.operacion).distinct().order_by(Auditoria.operacion))])


@router.get('', response_model=PaginaAuditoria)
def listar(entidad: str | None = None, operacion: str | None = None,
           usuario_id: int | None = None, entidad_id: int | None = None,
           desde: datetime | None = None, hasta: datetime | None = None,
           pagina: int = Query(default=1, ge=1),
           tamano: int = Query(default=50, ge=1, le=200),
           _: Usuarios = Depends(requiere('auditoria.ver')),
           db: Session = Depends(get_db)):
    """El registro, del más reciente al más viejo (RF-076, RNF-05).

    Sin filtros son miles de líneas y no sirve de nada; con `entidad` y
    `entidad_id` responde la pregunta que de verdad se hace: qué le pasó a este
    cliente, a este trámite, a este pago.
    """
    cond = []
    if entidad:
        cond.append(Auditoria.entidad == entidad)
    if operacion:
        cond.append(Auditoria.operacion == operacion)
    if usuario_id:
        cond.append(Auditoria.usuario_id == usuario_id)
    if entidad_id:
        cond.append(Auditoria.entidad_id == entidad_id)
    if desde:
        cond.append(Auditoria.ocurrido_en >= desde)
    if hasta:
        cond.append(Auditoria.ocurrido_en <= hasta)

    total = db.scalar(select(func.count()).select_from(Auditoria).where(*cond)) or 0
    filas = db.execute(
        select(Auditoria, Usuarios.nombre)
        .outerjoin(Usuarios, Usuarios.id == Auditoria.usuario_id)
        .where(*cond)
        .order_by(Auditoria.id.desc())
        .limit(tamano).offset((pagina - 1) * tamano)).all()

    return PaginaAuditoria(total=total, pagina=pagina, tamano=tamano, items=[
        RegistroSalida(
            id=a.id, ocurrido_en=a.ocurrido_en, usuario_id=a.usuario_id, usuario=nombre,
            operacion=a.operacion, entidad=a.entidad, entidad_id=a.entidad_id,
            ip=str(a.ip) if a.ip else None,
            campos=sorted((a.despues or {}).keys() | (a.antes or {}).keys()),
            antes=_servible(a.entidad, a.antes), despues=_servible(a.entidad, a.despues))
        for a, nombre in filas])
