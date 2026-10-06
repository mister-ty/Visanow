"""Gastos generales y directos (RF-053).

La diferencia entre general y directo es la que decide si una venta fue buen
negocio. La mensajería de un trámite es un gasto directo de ese caso: se le
resta a esa venta. La publicidad del mes es general: se reparte o se mira
aparte, pero no se le carga a nadie en particular.

En los archivos actuales esto no se puede distinguir: la hoja GASTOS tiene como
«categoría» nombres de personas —`yas`, `miriam`— que no son categorías sino a
quién se le pagó, y 75 de sus 78 filas no tienen fecha. Por eso la categoría
aquí viene de un catálogo y la fecha es obligatoria.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import Invalido, NoEncontrado
from app.models.esquema import Casos, CategoriasGasto, Gastos, Negocios, Usuarios
from app.services.auditoria import auditar, instantanea

BOGOTA = ZoneInfo('America/Bogota')


def registrar(db: Session, actor: Usuarios, datos: dict, ip: str | None = None) -> Gastos:
    monto = Decimal(str(datos.get('monto') or 0))
    if monto <= 0:
        raise Invalido('El monto del gasto tiene que ser mayor que cero.')
    if db.get(CategoriasGasto, datos.get('categoria_id')) is None:
        raise NoEncontrado('La categoría de gasto no existe.')
    if datos.get('negocio_id') and db.get(Negocios, datos['negocio_id']) is None:
        raise NoEncontrado('La venta no existe.')
    if datos.get('caso_id') and db.get(Casos, datos['caso_id']) is None:
        raise NoEncontrado('El trámite no existe.')

    gasto = Gastos(
        categoria_id=datos['categoria_id'], proveedor_id=datos.get('proveedor_id'),
        negocio_id=datos.get('negocio_id'), caso_id=datos.get('caso_id'),
        concepto=datos['concepto'],
        fecha=datos.get('fecha') or dt.datetime.now(BOGOTA).date(),
        monto=monto, moneda=datos.get('moneda') or 'COP',
        estado=datos.get('estado') or 'pagado',
        medio_pago_id=datos.get('medio_pago_id'), banco_cuenta_id=datos.get('banco_cuenta_id'),
        comprobante_url=datos.get('comprobante_url'), observacion=datos.get('observacion'),
        registrado_por=actor.id)
    db.add(gasto)
    db.flush()
    auditar(db, operacion='insert', entidad='gastos', usuario_id=actor.id, entidad_id=gasto.id,
            despues=instantanea(gasto), ip=ip)
    db.commit()
    return gasto


def anular(db: Session, actor: Usuarios, gasto_id: int, motivo: str,
           ip: str | None = None) -> Gastos:
    """Anular, nunca borrar: un gasto borrado es plata que salió sin rastro."""
    gasto = db.get(Gastos, gasto_id)
    if gasto is None:
        raise NoEncontrado('El gasto no existe.')
    if not motivo or not motivo.strip():
        raise Invalido('Escriba por qué se anula el gasto.', codigo='falta_motivo')
    antes = instantanea(gasto)
    gasto.estado = 'anulado'
    gasto.observacion = f'{gasto.observacion or ""}\nAnulado: {motivo}'.strip()
    db.flush()
    auditar(db, operacion='update', entidad='gastos', usuario_id=actor.id, entidad_id=gasto.id,
            antes=antes, despues=instantanea(gasto), ip=ip)
    db.commit()
    return gasto


def listar(db: Session, *, categoria_id: int | None = None, negocio_id: int | None = None,
           caso_id: int | None = None, solo_directos: bool = False,
           desde: dt.date | None = None, hasta: dt.date | None = None,
           incluir_anulados: bool = False, pagina: int = 1,
           tamano: int = 50) -> tuple[int, float, list[Gastos]]:
    consulta: Select = select(Gastos).options(selectinload(Gastos.categoria))
    if not incluir_anulados:
        consulta = consulta.where(Gastos.estado != 'anulado')
    if categoria_id:
        consulta = consulta.where(Gastos.categoria_id == categoria_id)
    if negocio_id:
        consulta = consulta.where(Gastos.negocio_id == negocio_id)
    if caso_id:
        consulta = consulta.where(Gastos.caso_id == caso_id)
    if solo_directos:
        # Directo es el que se le puede cargar a una venta o a un trámite; lo
        # demás es gasto de la casa.
        consulta = consulta.where((Gastos.negocio_id.isnot(None)) | (Gastos.caso_id.isnot(None)))
    if desde:
        consulta = consulta.where(Gastos.fecha >= desde)
    if hasta:
        consulta = consulta.where(Gastos.fecha <= hasta)

    sub = consulta.subquery()
    total = db.scalar(select(func.count()).select_from(sub)) or 0
    suma = db.scalar(select(func.coalesce(func.sum(sub.c.monto), 0))) or 0
    filas = list(db.scalars(consulta.order_by(Gastos.fecha.desc(), Gastos.id.desc())
                            .offset((pagina - 1) * tamano).limit(tamano)))
    return int(total), float(suma), filas


def directos_de_la_venta(db: Session, negocio_id: int) -> float:
    """Lo que esa venta costó de verdad: lo que se le cargó directo."""
    casos = select(Casos.id).where(Casos.negocio_id == negocio_id)
    return float(db.scalar(
        select(func.coalesce(func.sum(Gastos.monto), 0))
        .where(Gastos.estado != 'anulado',
               (Gastos.negocio_id == negocio_id) | (Gastos.caso_id.in_(casos)))) or 0)


def por_categoria(db: Session, desde: dt.date | None = None,
                  hasta: dt.date | None = None) -> list[tuple[str, int, float]]:
    consulta = (select(CategoriasGasto.nombre, func.count(Gastos.id),
                       func.coalesce(func.sum(Gastos.monto), 0))
                .join(Gastos, Gastos.categoria_id == CategoriasGasto.id)
                .where(Gastos.estado != 'anulado')
                .group_by(CategoriasGasto.id).order_by(func.sum(Gastos.monto).desc()))
    if desde:
        consulta = consulta.where(Gastos.fecha >= desde)
    if hasta:
        consulta = consulta.where(Gastos.fecha <= hasta)
    return [(n, int(c), float(s)) for n, c, s in db.execute(consulta)]
