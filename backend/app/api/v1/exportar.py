from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere, usuario_operativo
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.services import exportar as servicio

router = APIRouter(prefix='/exportar', tags=['exportación'])

TIPOS = {'csv': 'text/csv; charset=utf-8',
         'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}


class RecursosSalida(BaseModel):
    recursos: list[str] = Field(description='Lo que este usuario puede exportar')


class ExportacionSalida(BaseModel):
    id: int
    usuario: str
    recurso: str
    formato: str
    filas: int
    ip: str | None
    ocurrido_en: datetime
    filtros: dict


@router.get('/recursos', response_model=RecursosSalida)
def recursos(actor: Usuarios = Depends(usuario_operativo), db: Session = Depends(get_db)):
    """Qué puede exportar quien pregunta.

    La pantalla no debería ofrecer un botón que va a devolver 403.
    """
    return RecursosSalida(recursos=servicio.disponibles(db, actor))


@router.get('/historial', response_model=list[ExportacionSalida])
def historial(limite: int = 50, _: Usuarios = Depends(requiere('auditoria.ver')),
              db: Session = Depends(get_db)):
    """Quién exportó qué y cuándo (RNF-07).

    Es lo que se mira el día que un archivo con datos de clientes aparece donde
    no debía.
    """
    return [ExportacionSalida(**f) for f in servicio.historial(db, limite)]


@router.get('/{recurso}')
def descargar(recurso: str, request: Request, formato: Literal['xlsx', 'csv'] = 'xlsx',
              actor: Usuarios = Depends(usuario_operativo), db: Session = Depends(get_db)):
    """El archivo, con las columnas que este usuario puede ver (RF-075).

    Las columnas sensibles se omiten según el permiso, no se devuelve un error:
    operaciones necesita la lista de trámites para trabajar; lo que no necesita
    es cuánto pagó cada cliente. La cabecera `X-Columnas-Omitidas` dice cuáles
    se dejaron por fuera, para que la pantalla pueda avisarlo.
    """
    cuerpo, archivo, filas, omitidas = servicio.generar(
        db, actor, recurso, formato, ip=ip_cliente(request))
    return Response(cuerpo, media_type=TIPOS[formato], headers={
        'Content-Disposition': f'attachment; filename="{archivo}"',
        'X-Filas': str(filas),
        'X-Columnas-Omitidas': ', '.join(omitidas)})
