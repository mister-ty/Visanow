"""Rentabilidad por negocio, servicio y periodo (RF-054).

El permiso es `pagos.ver`, el mismo de los tableros de plata. No es casualidad:
aqui se ven comisiones, gastos y margen, que es exactamente «lo de la
contabilidad» que la administradora dijo el 29/09 que operaciones no ve.
Operaciones se crea con alcance «todos» porque tiene que ver todos los
tramites, asi que si esto se cuidara por alcance entraria sin problema. Ver
plata es un permiso.

El alcance (RNF-03) se revisa en el servicio, no aqui: los filtros de la
pantalla se pueden no enviar, y un control de acceso que se puede apagar desde
la API no es un control de acceso.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import requiere
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.schemas import rentabilidad as esq
from app.services import rentabilidad as servicio

router = APIRouter(prefix='/rentabilidad', tags=['rentabilidad'])

Desde = Query(default=None, description='Fecha de venta, inclusive')
Hasta = Query(default=None, description='Fecha de venta, inclusive')


def _filtros(desde, hasta, servicio_id, vendedor_id) -> servicio.Filtros:
    return servicio.Filtros(desde=desde, hasta=hasta, servicio_id=servicio_id,
                            vendedor_id=vendedor_id)


@router.get('', response_model=esq.InformeSalida)
def informe(desde: date | None = Desde, hasta: date | None = Hasta,
            servicio_id: int | None = None, vendedor_id: int | None = None,
            actor: Usuarios = Depends(requiere('pagos.ver')),
            db: Session = Depends(get_db)):
    """El margen del periodo, y el mismo margen cortado por servicio y por mes.

    «Ingreso neto menos comisiones, gastos directos y costos»: las cuatro
    cifras viajan aparte para que la resta se pueda rehacer a mano.
    """
    datos = servicio.informe(db, actor, _filtros(desde, hasta, servicio_id, vendedor_id))
    return esq.InformeSalida(
        total=esq.MargenSalida(**datos.total.__dict__),
        por_servicio=[esq.MargenSalida(**m.__dict__) for m in datos.por_servicio],
        por_periodo=[esq.MargenSalida(**m.__dict__) for m in datos.por_periodo])


@router.get('/ventas', response_model=esq.PaginaVentas)
def ventas(desde: date | None = Desde, hasta: date | None = Hasta,
           servicio_id: int | None = None, vendedor_id: int | None = None,
           orden: esq.OrdenVentas = 'peores', pagina: int = 1, tamano: int = Query(50, le=200),
           actor: Usuarios = Depends(requiere('pagos.ver')),
           db: Session = Depends(get_db)):
    """Una fila por venta. Por omision las peores primero: son las que hay que mirar."""
    total, filas = servicio.por_negocio(
        db, actor, _filtros(desde, hasta, servicio_id, vendedor_id),
        orden=orden, pagina=pagina, tamano=tamano)
    return esq.PaginaVentas(total=total, pagina=pagina, tamano=tamano,
                            items=[esq.MargenVentaSalida(**m.__dict__) for m in filas])


@router.get('/ventas/{negocio_id}', response_model=esq.MargenVentaSalida)
def venta(negocio_id: int, actor: Usuarios = Depends(requiere('pagos.ver')),
          db: Session = Depends(get_db)):
    """Que dejo esta venta, pieza por pieza."""
    return esq.MargenVentaSalida(**servicio.de_la_venta(db, actor, negocio_id).__dict__)
