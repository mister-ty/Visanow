from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.services import exportacion
from app.services import tableros as servicio

router = APIRouter(prefix='/tableros', tags=['tableros'])

NombreTablero = Literal['comercial', 'operativo', 'financiero', 'ejecutivo']


class IndicadorSalida(BaseModel):
    clave: str
    nombre: str
    valor: float
    formato: Literal['numero', 'pesos', 'porcentaje']


class TablaSalida(BaseModel):
    clave: str
    titulo: str
    columnas: list[str]
    filas: list[list[str | float | int | None]]


class TableroSalida(BaseModel):
    tablero: str
    titulo: str
    indicadores: list[IndicadorSalida]
    tablas: list[TablaSalida]


def _filtros(desde, hasta, vendedor_id, servicio_id, estado) -> servicio.Filtros:
    return servicio.Filtros(desde=desde, hasta=hasta, vendedor_id=vendedor_id,
                            servicio_id=servicio_id, estado=estado)


def _limpio(v):
    # Decimal y fechas no viajan en JSON de forma uniforme: se normalizan aquí
    if hasattr(v, 'quantize'):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


@router.get('/{tablero}', response_model=TableroSalida)
def ver(tablero: NombreTablero,
        desde: date | None = Query(default=None, description='Día de Bogotá, inclusivo'),
        hasta: date | None = Query(default=None, description='Día de Bogotá, inclusivo'),
        vendedor_id: int | None = None, servicio_id: int | None = None,
        estado: str | None = Query(default=None, description='Código de estado del tablero'),
        actor: Usuarios = Depends(requiere('tableros.ver')), db: Session = Depends(get_db)):
    """Los cuatro tableros (RF-070 a RF-073) con los mismos filtros (RF-074)."""
    t = servicio.construir(db, actor, tablero, _filtros(desde, hasta, vendedor_id,
                                                        servicio_id, estado))
    return TableroSalida(
        tablero=t.tablero, titulo=t.titulo,
        indicadores=[IndicadorSalida(**i.__dict__) for i in t.indicadores],
        tablas=[TablaSalida(clave=x.clave, titulo=x.titulo, columnas=x.columnas,
                            filas=[[_limpio(v) for v in fila] for fila in x.filas])
                for x in t.tablas])


@router.get('/{tablero}/exportar')
def exportar(request: Request, tablero: NombreTablero, formato: Literal['xlsx', 'csv'] = 'xlsx',
             desde: date | None = None, hasta: date | None = None,
             vendedor_id: int | None = None, servicio_id: int | None = None,
             estado: str | None = None,
             actor: Usuarios = Depends(requiere('tableros.exportar')),
             db: Session = Depends(get_db)):
    """Exporta con los mismos filtros de la pantalla (RF-075): lo que se ve es lo que se baja."""
    filtros = _filtros(desde, hasta, vendedor_id, servicio_id, estado)
    t = servicio.construir(db, actor, tablero, filtros)
    # Un tablero financiero exportado es contabilidad fuera del sistema: queda
    # constancia de quién se lo llevó, igual que con las listas (RNF-07).
    exportacion.registrar(db, actor, f'tablero-{tablero}', formato,
                          vars(filtros),   # ya con el filtro que el alcance le impuso
                          sum(len(x.filas) for x in t.tablas), ip_cliente(request))
    db.commit()
    if formato == 'csv':
        cuerpo, tipo = servicio.a_csv(t), 'text/csv; charset=utf-8'
    else:
        cuerpo = servicio.a_xlsx(t)
        tipo = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return Response(cuerpo, media_type=tipo, headers={
        'Content-Disposition': f'attachment; filename="tablero-{tablero}.{formato}"'})
