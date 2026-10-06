"""Pagos, plan de cuotas y ajustes (RF-040 a RF-046).

El problema que resuelve se ve en los archivos actuales: los abonos viven en
columnas fijas —«Abono 1», «Abono 2», «Abono 3»— y seis ventas ya las llenaron
las tres. No hay dónde registrar un cuarto pago. Aquí un pago es una fila, así
que caben los que sean (RN-02).

Y el saldo **no se guarda**: sale de la vista `v_estado_financiero`, que resta
los pagos y los ajustes del valor pactado. Guardar el saldo en una columna es
lo que hace que dos lugares digan números distintos, que es exactamente lo que
pasa hoy entre las hojas PAGOS y REV PAGOS: 37 millones de deuda fantasma.

**La bandeja de no identificados.** Llega una consignación y no siempre se sabe
de quién es: el que consigna puede ser el papá, la empresa o un amigo. El pago
entra igual, sin negocio, y queda en una bandeja hasta que alguien lo asigne.
Es mejor que perderlo o que inventarle dueño.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import Conflicto, Invalido, NoEncontrado
from app.models.esquema import (AjustesNegocio, CuotasNegocio, Negocios, Pagos, Parametros,
                                Usuarios)
from app.services import comisiones
from app.services.auditoria import auditar, instantanea

BOGOTA = ZoneInfo('America/Bogota')

# Un ajuste que sube la deuda va en positivo y uno que la baja en negativo. La
# base lo exige con un check, y aquí se traduce para que quien llama no tenga
# que acordarse del signo.
SUBEN_LA_DEUDA = ('cargo', 'reembolso')
BAJAN_LA_DEUDA = ('descuento', 'condonacion')


def _hoy() -> dt.date:
    return dt.datetime.now(BOGOTA).date()


def parametro(db: Session, clave: str, por_defecto):
    p = db.get(Parametros, clave)
    return p.valor if p is not None else por_defecto


# ------------------------------------------------------------- plan de cuotas

def plan_de_cuotas(db: Session, actor: Usuarios, negocio_id: int, *,
                   reparto: list[int] | None = None, plazo_dias: int | None = None,
                   ip: str | None = None) -> list[CuotasNegocio]:
    """Parte la venta en anticipo y saldo, con fecha para cada uno.

    Sin esto la cartera vencida sale en cero: `v_cartera` compara lo pagado
    contra lo que ya era exigible, y lo exigible sale de las cuotas. Una venta
    sin plan de cuotas no vence nunca, así que nadie la cobra.

    El reparto por defecto (20 % y 80 %) y el plazo (30 días) viven en
    `parametros`, no en el código: los cambia la administradora sin tocar nada.
    """
    negocio = db.get(Negocios, negocio_id)
    if negocio is None:
        raise NoEncontrado('La venta no existe.')
    if db.scalar(select(func.count()).select_from(CuotasNegocio)
                 .where(CuotasNegocio.negocio_id == negocio_id)):
        raise Conflicto('Esta venta ya tiene plan de cuotas.', codigo='ya_tiene_cuotas')

    reparto = reparto or parametro(db, 'cartera.anticipos_porcentaje', [20, 80])
    plazo = plazo_dias if plazo_dias is not None else int(
        parametro(db, 'cartera.plazo_saldo_dias', 30))
    if sum(reparto) != 100:
        raise Invalido(f'El reparto tiene que sumar 100 %, y suma {sum(reparto)}.')

    total = Decimal(str(negocio.valor_pactado))
    if total <= 0:
        raise Invalido('La venta no tiene valor pactado: no hay nada que repartir.',
                       codigo='sin_valor_pactado')

    cuotas, acumulado = [], Decimal('0')
    for i, porcentaje in enumerate(reparto, start=1):
        ultima = i == len(reparto)
        # La última cuota lleva el residuo, para que las cuotas sumen exactamente
        # el valor pactado y no sobre ni falte un peso por redondeo.
        monto = (total - acumulado) if ultima else (total * Decimal(porcentaje) / 100).quantize(
            Decimal('1'))
        acumulado += monto
        if monto <= 0:
            continue
        cuota = CuotasNegocio(
            negocio_id=negocio_id, numero=i,
            concepto='anticipo' if i == 1 else ('saldo' if ultima else f'cuota {i}'),
            monto=monto,
            fecha_pactada=negocio.fecha_venta if i == 1
            else negocio.fecha_venta + dt.timedelta(days=plazo))
        db.add(cuota)
        cuotas.append(cuota)

    db.flush()
    auditar(db, operacion='insert', entidad='cuotas_negocio', usuario_id=actor.id,
            entidad_id=negocio_id,
            despues={'cuotas': [{'numero': c.numero, 'monto': str(c.monto),
                                 'fecha': c.fecha_pactada.isoformat()} for c in cuotas]}, ip=ip)
    db.commit()
    return cuotas


def cuotas_de(db: Session, negocio_id: int) -> list[CuotasNegocio]:
    return list(db.scalars(select(CuotasNegocio).where(CuotasNegocio.negocio_id == negocio_id)
                           .order_by(CuotasNegocio.numero)))


# -------------------------------------------------------------------- pagos

def registrar(db: Session, actor: Usuarios, datos: dict, ip: str | None = None) -> Pagos:
    """Un pago. Si no se sabe de qué venta es, entra sin venta y queda en la
    bandeja de no identificados (RF-043)."""
    monto = Decimal(str(datos.get('monto_bruto') or 0))
    if monto <= 0:
        raise Invalido('El monto del pago tiene que ser mayor que cero.')
    costo = Decimal(str(datos.get('costo_medio') or 0))
    if costo > monto:
        raise Invalido('El costo del medio de pago no puede ser mayor que el pago.',
                       codigo='costo_mayor_que_pago')

    negocio_id = datos.get('negocio_id')
    if negocio_id and db.get(Negocios, negocio_id) is None:
        raise NoEncontrado('La venta no existe.')

    pago = Pagos(
        negocio_id=negocio_id, fecha=datos.get('fecha') or _hoy(),
        monto_bruto=monto, costo_medio=costo,
        moneda=datos.get('moneda') or 'COP',
        medio_pago_id=datos.get('medio_pago_id'), banco_cuenta_id=datos.get('banco_cuenta_id'),
        referencia=datos.get('referencia'), comprobante_url=datos.get('comprobante_url'),
        # Sin venta no está confirmado contra nada: queda marcado para que se vea
        # en la bandeja y nadie lo cuente como ingreso de un cliente.
        estado=datos.get('estado') or ('confirmado' if negocio_id else 'no_identificado'),
        observacion=datos.get('observacion'), pagador_nombre=datos.get('pagador_nombre'),
        registrado_por=actor.id)
    db.add(pago)
    db.flush()
    auditar(db, operacion='insert', entidad='pagos', usuario_id=actor.id, entidad_id=pago.id,
            despues=instantanea(pago), ip=ip)
    db.commit()
    # Si este pago cerró la venta, la comisión pasa a causada (D-03)
    if pago.negocio_id:
        comisiones.revisar_causacion(db, actor, pago.negocio_id, ip=ip)
    return pago


def asignar(db: Session, actor: Usuarios, pago_id: int, negocio_id: int,
            ip: str | None = None) -> Pagos:
    """Le pone dueño a un pago que llegó suelto."""
    pago = db.get(Pagos, pago_id)
    if pago is None:
        raise NoEncontrado('El pago no existe.')
    if db.get(Negocios, negocio_id) is None:
        raise NoEncontrado('La venta no existe.')
    if pago.negocio_id == negocio_id:
        return pago
    antes = instantanea(pago)
    pago.negocio_id = negocio_id
    if pago.estado == 'no_identificado':
        pago.estado = 'confirmado'
    db.flush()
    auditar(db, operacion='update', entidad='pagos', usuario_id=actor.id, entidad_id=pago.id,
            antes=antes, despues=instantanea(pago), ip=ip)
    db.commit()
    comisiones.revisar_causacion(db, actor, negocio_id, ip=ip)
    return pago


def cambiar_estado(db: Session, actor: Usuarios, pago_id: int, estado: str,
                   observacion: str | None = None, ip: str | None = None) -> Pagos:
    """Marcar un pago como reversado o duplicado.

    No se borra nunca: un pago que se borra es plata que desaparece del
    historial sin dejar rastro. Se marca, y deja de sumar al saldo.
    """
    pago = db.get(Pagos, pago_id)
    if pago is None:
        raise NoEncontrado('El pago no existe.')
    if estado not in ('confirmado', 'pendiente', 'no_identificado', 'reversado', 'duplicado'):
        raise Invalido(f'Estado de pago inválido: «{estado}».')
    antes = instantanea(pago)
    pago.estado = estado
    if observacion:
        pago.observacion = observacion
    db.flush()
    auditar(db, operacion='update', entidad='pagos', usuario_id=actor.id, entidad_id=pago.id,
            antes=antes, despues=instantanea(pago), ip=ip)
    db.commit()
    # Reversar un pago puede devolver la comisión a provisional: no se paga
    # comisión de plata que no entró.
    if pago.negocio_id:
        comisiones.revisar_causacion(db, actor, pago.negocio_id, ip=ip)
    return pago


def listar(db: Session, *, negocio_id: int | None = None, sin_asignar: bool = False,
           desde: dt.date | None = None, hasta: dt.date | None = None,
           pagina: int = 1, tamano: int = 50) -> tuple[int, list[Pagos]]:
    consulta: Select = select(Pagos).options(selectinload(Pagos.negocio),
                                             selectinload(Pagos.medio_pago))
    if negocio_id:
        consulta = consulta.where(Pagos.negocio_id == negocio_id)
    if sin_asignar:
        consulta = consulta.where(Pagos.negocio_id.is_(None))
    if desde:
        consulta = consulta.where(Pagos.fecha >= desde)
    if hasta:
        consulta = consulta.where(Pagos.fecha <= hasta)
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = list(db.scalars(consulta.order_by(Pagos.fecha.desc(), Pagos.id.desc())
                            .offset((pagina - 1) * tamano).limit(tamano)))
    return total, filas


def pagos_de(db: Session, negocio_id: int) -> list[Pagos]:
    return list(db.scalars(select(Pagos).where(Pagos.negocio_id == negocio_id)
                           .options(selectinload(Pagos.medio_pago))
                           .order_by(Pagos.fecha, Pagos.id)))


# ------------------------------------------------------------------ ajustes

def ajustar(db: Session, actor: Usuarios, negocio_id: int, *, tipo: str, monto: float,
            motivo: str, fecha: dt.date | None = None, ip: str | None = None) -> AjustesNegocio:
    """Reembolsos, cargos, descuentos posteriores y condonaciones (RF-045).

    Quien llama dice el monto siempre en positivo y el tipo decide el signo: un
    cargo sube la deuda y un descuento la baja. Guardar el signo a mano es la
    clase de error que no falla, solo deja la cartera al revés.

    El motivo es obligatorio: un ajuste sin motivo es plata que cambió de lugar
    sin que nadie pueda explicar por qué.
    """
    if db.get(Negocios, negocio_id) is None:
        raise NoEncontrado('La venta no existe.')
    if tipo not in SUBEN_LA_DEUDA + BAJAN_LA_DEUDA:
        raise Invalido(f'Tipo de ajuste inválido: «{tipo}». '
                       f'Opciones: {", ".join(SUBEN_LA_DEUDA + BAJAN_LA_DEUDA)}.')
    if not motivo or not motivo.strip():
        raise Invalido('Escriba el motivo del ajuste.', codigo='falta_motivo')
    if monto <= 0:
        raise Invalido('El monto del ajuste se escribe en positivo; el tipo decide el signo.')

    con_signo = Decimal(str(monto)) if tipo in SUBEN_LA_DEUDA else -Decimal(str(monto))
    ajuste = AjustesNegocio(negocio_id=negocio_id, tipo=tipo, monto=con_signo,
                            motivo=motivo.strip(), autorizado_por=actor.id,
                            fecha=fecha or _hoy())
    db.add(ajuste)
    db.flush()
    auditar(db, operacion='insert', entidad='ajustes_negocio', usuario_id=actor.id,
            entidad_id=ajuste.id, despues=instantanea(ajuste), ip=ip)
    db.commit()
    # Un cargo o un reembolso cambian el saldo, y con él si la comisión se ganó
    comisiones.revisar_causacion(db, actor, negocio_id, ip=ip)
    return ajuste


def ajustes_de(db: Session, negocio_id: int) -> list[AjustesNegocio]:
    return list(db.scalars(select(AjustesNegocio)
                           .where(AjustesNegocio.negocio_id == negocio_id)
                           .order_by(AjustesNegocio.fecha, AjustesNegocio.id)))
