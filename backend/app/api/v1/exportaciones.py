from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, usuario_operativo
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.services import exportacion as servicio

router = APIRouter(prefix='/exportaciones', tags=['exportaciones'])

TIPOS = {
    'csv': 'text/csv; charset=utf-8',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


@router.get('/{lista}')
def exportar(lista: Literal['clientes', 'casos', 'cartera', 'comisiones'], request: Request,
             formato: Literal['xlsx', 'csv'] = 'xlsx',
             texto: str | None = None, archivados: bool = False,
             estado: str | None = None, responsable_id: int | None = None,
             pais_id: int | None = None, incluir_finalizados: bool = False,
             sin_asignar: bool = False,
             solo_vencida: bool = False, vendedor_id: int | None = None,
             desde_dias: int | None = None, periodo: date | None = None,
             actor: Usuarios = Depends(usuario_operativo), db: Session = Depends(get_db)):
    """Descarga una lista con los mismos filtros de su pantalla (RF-075).

    El permiso es `<módulo>.exportar` y se comprueba en el servicio, porque
    depende de la lista pedida. Cada descarga queda registrada en la auditoría
    con quién fue y cuántas filas se llevó (RNF-07).
    """
    filtros = {'texto': texto, 'archivados': archivados, 'estado': estado,
               'responsable_id': responsable_id, 'pais_id': pais_id,
               'incluir_finalizados': incluir_finalizados, 'sin_asignar': sin_asignar,
               'solo_vencida': solo_vencida,
               'vendedor_id': vendedor_id, 'desde_dias': desde_dias, 'periodo': periodo}
    cuerpo, _ = servicio.exportar(db, actor, lista, formato, filtros, ip=ip_cliente(request))
    return Response(cuerpo, media_type=TIPOS[formato], headers={
        'Content-Disposition': f'attachment; filename="{lista}.{formato}"'})
