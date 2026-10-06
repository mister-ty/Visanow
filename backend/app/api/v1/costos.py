from datetime import date

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Comisiones, Gastos, LiquidacionesComision, Usuarios
from app.schemas import costos as esq
from app.services import comisiones as serv_comisiones
from app.services import gastos as serv_gastos

router = APIRouter(tags=['gastos y comisiones'])


def _gasto(g: Gastos) -> esq.GastoSalida:
    return esq.GastoSalida(
        id=g.id, categoria_id=g.categoria_id, categoria=g.categoria.nombre,
        concepto=g.concepto, fecha=g.fecha, monto=float(g.monto), moneda=g.moneda,
        estado=g.estado, negocio_id=g.negocio_id, caso_id=g.caso_id,
        es_directo=bool(g.negocio_id or g.caso_id), observacion=g.observacion,
        creado_en=g.creado_en)


def _comision(c: Comisiones) -> esq.ComisionSalida:
    regla = c.regla_aplicada or {}
    return esq.ComisionSalida(
        id=c.id, negocio_id=c.negocio_id, vendedor_id=c.vendedor_id,
        vendedor=c.vendedor.nombre if c.vendedor else None,
        base_calculo=float(c.base_calculo), monto=float(c.monto), estado=c.estado,
        periodo=c.periodo, porcentaje_aplicado=regla.get('porcentaje_aplicado'),
        escalon=regla.get('escalon'), explicacion=regla.get('explicacion'),
        liquidacion_id=c.liquidacion_id, creado_en=c.creado_en)


def _liquidacion(db: Session, liq: LiquidacionesComision) -> esq.LiquidacionSalida:
    incluidas = list(db.scalars(select(Comisiones)
                                .where(Comisiones.liquidacion_id == liq.id)))
    return esq.LiquidacionSalida(
        id=liq.id, vendedor_id=liq.vendedor_id,
        vendedor=liq.vendedor.nombre if liq.vendedor else None,
        periodo=liq.periodo, total=float(liq.total), cantidad=liq.cantidad, estado=liq.estado,
        observaciones=liq.observaciones, creada_en=liq.creada_en, pagada_en=liq.pagada_en,
        comisiones=[_comision(c) for c in incluidas])


# --------------------------------------------------------------------- gastos

@router.post('/gastos', response_model=esq.GastoSalida, status_code=status.HTTP_201_CREATED)
def registrar_gasto(datos: esq.GastoCrear, request: Request,
                    actor: Usuarios = Depends(requiere('gastos.crear')),
                    db: Session = Depends(get_db)):
    """Un gasto general o directo (RF-053).

    Si lleva venta o trámite es directo y se le resta a esa venta; si no, es
    gasto de la casa. La diferencia es la que decide si una venta fue buen
    negocio.
    """
    return _gasto(serv_gastos.registrar(db, actor, datos.model_dump(exclude_unset=True),
                                        ip=ip_cliente(request)))


@router.get('/gastos', response_model=esq.PaginaGastos)
def listar_gastos(categoria_id: int | None = None, negocio_id: int | None = None,
                  caso_id: int | None = None, solo_directos: bool = False,
                  desde: date | None = None, hasta: date | None = None,
                  incluir_anulados: bool = False, pagina: int = 1, tamano: int = 50,
                  _: Usuarios = Depends(requiere('gastos.ver')), db: Session = Depends(get_db)):
    total, suma, filas = serv_gastos.listar(
        db, categoria_id=categoria_id, negocio_id=negocio_id, caso_id=caso_id,
        solo_directos=solo_directos, desde=desde, hasta=hasta,
        incluir_anulados=incluir_anulados, pagina=pagina, tamano=tamano)
    return esq.PaginaGastos(total=total, suma=suma, pagina=pagina, tamano=tamano,
                            items=[_gasto(g) for g in filas])


@router.get('/gastos/por-categoria', response_model=list[esq.GastoPorCategoria])
def gastos_por_categoria(desde: date | None = None, hasta: date | None = None,
                         _: Usuarios = Depends(requiere('gastos.ver')),
                         db: Session = Depends(get_db)):
    return [esq.GastoPorCategoria(categoria=n, cuantos=c, total=t)
            for n, c, t in serv_gastos.por_categoria(db, desde, hasta)]


@router.post('/gastos/{gasto_id}/anular', response_model=esq.GastoSalida)
def anular_gasto(gasto_id: int, datos: esq.AnularEntrada, request: Request,
                 actor: Usuarios = Depends(requiere('gastos.editar')),
                 db: Session = Depends(get_db)):
    """Anular, nunca borrar: un gasto borrado es plata que salió sin rastro."""
    return _gasto(serv_gastos.anular(db, actor, gasto_id, datos.motivo, ip=ip_cliente(request)))


# ----------------------------------------------------------------- comisiones

@router.get('/comisiones', response_model=list[esq.ComisionSalida])
def listar_comisiones(vendedor_id: int | None = None, periodo: date | None = None,
                      estado: esq.EstadoComision | None = None,
                      _: Usuarios = Depends(requiere('comisiones.ver')),
                      db: Session = Depends(get_db)):
    """Las comisiones, con el porqué de cada una.

    Cada fila lleva congelada la regla que se le aplicó (RN-07), así que el
    cálculo se puede explicar meses después sin reconstruir qué decía la tabla
    ese día.
    """
    return [_comision(c) for c in serv_comisiones.comisiones_de(
        db, vendedor_id=vendedor_id, periodo=periodo, estado=estado)]


@router.get('/comisiones/pendientes', response_model=list[esq.ComisionSalida])
def pendientes(vendedor_id: int, periodo: date,
               _: Usuarios = Depends(requiere('comisiones.ver')),
               db: Session = Depends(get_db)):
    """Lo que entraría en el corte: causado, del periodo y sin liquidar."""
    return [_comision(c) for c in serv_comisiones.pendientes(db, vendedor_id, periodo)]


@router.post('/ventas/{negocio_id}/comision/recalcular',
             response_model=esq.ComisionSalida | None)
def recalcular(negocio_id: int, request: Request,
               actor: Usuarios = Depends(requiere('comisiones.editar')),
               db: Session = Depends(get_db)):
    """Recalcula con la regla vigente a la fecha de la venta.

    No toca las ya liquidadas: esa plata ya se pagó y cambiarla a posteriori es
    reescribir la historia de un pago.
    """
    c = serv_comisiones.recalcular(db, actor, negocio_id, ip=ip_cliente(request))
    return _comision(c) if c else None


@router.post('/liquidaciones', response_model=esq.LiquidacionSalida,
             status_code=status.HTTP_201_CREATED)
def liquidar(datos: esq.LiquidarEntrada, request: Request,
             actor: Usuarios = Depends(requiere('comisiones.editar')),
             db: Session = Depends(get_db)):
    """El corte del periodo (RF-052).

    Las comisiones que entran quedan bloqueadas y no pueden volver a entrar en
    otro corte. Es la diferencia entre un reporte y el registro de un pago.
    """
    liq = serv_comisiones.liquidar(db, actor, datos.vendedor_id, datos.periodo,
                                   observaciones=datos.observaciones, ip=ip_cliente(request))
    return _liquidacion(db, liq)


@router.post('/liquidaciones/{liquidacion_id}/pagada', response_model=esq.LiquidacionSalida)
def marcar_pagada(liquidacion_id: int, request: Request,
                  actor: Usuarios = Depends(requiere('comisiones.editar')),
                  db: Session = Depends(get_db)):
    liq = serv_comisiones.marcar_pagada(db, actor, liquidacion_id, ip=ip_cliente(request))
    return _liquidacion(db, liq)


@router.post('/liquidaciones/{liquidacion_id}/anular', response_model=esq.LiquidacionSalida)
def anular_liquidacion(liquidacion_id: int, datos: esq.AnularEntrada, request: Request,
                       actor: Usuarios = Depends(requiere('comisiones.editar')),
                       db: Session = Depends(get_db)):
    """Deshace el corte y devuelve las comisiones a «causada».

    No se borra: queda la liquidación anulada con su motivo, para que la
    historia muestre que hubo un corte y por qué se deshizo.
    """
    liq = serv_comisiones.anular(db, actor, liquidacion_id, datos.motivo, ip=ip_cliente(request))
    return _liquidacion(db, liq)
