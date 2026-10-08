"""Comisiones: cálculo, causación y liquidación (RF-050, RF-051, RF-052).

La regla la dio la administradora el 03/10/2026 y está sembrada en
`comisiones_reglas`, no escrita acá:

> Angie comisiona el 7 % del valor de la venta. Sobre sus primeras diez ventas
> de servicio premium del periodo se le paga el 10 %, y de la once en adelante
> vuelve al 7 %. La renovación no cuenta para esas diez. La comisión se gana
> cuando el cliente termina de pagar toda la venta, no al cerrarla. Y la base es
> solo el valor del servicio: la tasa consular es plata del consulado.

**Por qué la regla vive en una fila y no en el código.** RN-07 exige que cada
venta conserve la regla que tenía el día que se hizo. Si en enero cambia el
porcentaje, las comisiones de octubre no se mueven. Por eso la comisión guarda
una copia íntegra de la regla en `regla_aplicada`, incluido el escalón que le
tocó y por qué: el cálculo se puede explicar meses después sin tener que
reconstruir qué decía la tabla ese día.

**Los tres estados.** `provisional` al cerrar la venta, `causada` cuando el
cliente termina de pagar —que es cuando se gana de verdad— y `liquidada` cuando
entra en un corte. Una comisión liquidada no vuelve a entrar en otro: ahí está
la diferencia entre un reporte y un registro de pago.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.core.errores import Conflicto, Invalido, NoEncontrado
from app.models.esquema import (AjustesNegocio, Comisiones, ComisionesReglas,
                                LiquidacionesComision, Negocios, Pagos, Servicios, Usuarios)
from app.services.auditoria import auditar, instantanea

BOGOTA = ZoneInfo('America/Bogota')
CENTAVO = Decimal('1')

# Las comisiones ya pagadas no se tocan; las demás se pueden recalcular.
MODIFICABLES = ('provisional', 'causada')


def _periodo_de(fecha: dt.date) -> dt.date:
    """El primer día del mes. Es la llave del corte."""
    return fecha.replace(day=1)


def regla_para(db: Session, vendedor_id: int, fecha: dt.date) -> ComisionesReglas | None:
    """La regla que regía para esa vendedora ese día.

    Primero la suya —atada por id— y si no tiene, una general. Siempre por
    vigencia y no «la última»: una venta de hace tres meses se comisiona con la
    regla de hace tres meses.

    Antes esto adivinaba: como las reglas sembradas no guardaban el id de su
    dueña, se emparejaba exigiendo que el nombre de la regla empezara por el
    primer nombre de la usuaria. Cuando no adivinaba —«Isa» contra la regla
    «Yas — 7 %…»— devolvía la primera regla sin vendedora, que es la de Angie, y
    le regalaba su escalón del 10 % a quien fuera. La regla ahora se amarra por
    id en el seed y en la migración 0010, y una regla sin dueña queda inactiva:
    tiene que pagarle a nadie, no a todas.

    La regla general existe y es la del 4 %: «yas ponle el 4 % de la venta y a
    los demás» (07/10). Quien venda y no tenga regla propia cae ahí. Devolver
    None solo pasa si ni siquiera hay regla general, y entonces no se comisiona.
    """
    base = (select(ComisionesReglas)
            .where(ComisionesReglas.activo.is_(True),
                   ComisionesReglas.vigente_desde <= fecha,
                   (ComisionesReglas.vigente_hasta.is_(None))
                   | (ComisionesReglas.vigente_hasta >= fecha))
            .order_by(ComisionesReglas.vigente_desde.desc(), ComisionesReglas.id.desc()))
    propia = db.scalars(base.where(ComisionesReglas.vendedor_id == vendedor_id)).first()
    if propia:
        return propia
    return db.scalars(base.where(ComisionesReglas.vendedor_id.is_(None))).first()


@dataclass
class Calculo:
    base: Decimal
    porcentaje: Decimal
    monto: Decimal
    escalon: str
    posicion_en_la_meta: int | None
    explicacion: str
    regla: dict


def _es_premium(definicion: dict, codigo_servicio: str | None) -> bool:
    cuentan = definicion.get('servicios_que_cuentan_para_la_meta') or []
    excluidos = definicion.get('servicios_excluidos_de_la_meta') or []
    if not codigo_servicio or codigo_servicio in excluidos:
        return False
    return codigo_servicio in cuentan


def _base_de_calculo(db: Session, negocio: Negocios, regla: ComisionesReglas) -> Decimal:
    """Sobre cuánto se comisiona.

    La tasa consular no entra: son dólares que el cliente le paga directamente
    al consulado, así que nunca pasan por las cuentas de VisaNow. Como el
    servicio de tasa es de tipo `recaudo_terceros`, basta con mirar el tipo.
    """
    servicio = db.get(Servicios, negocio.servicio_id)
    excluidos = (regla.definicion or {}).get('excluye_de_la_base') or []
    if servicio is not None and servicio.tipo in excluidos:
        return Decimal('0')

    if regla.base == 'vendido':
        return Decimal(str(negocio.valor_pactado))
    # Las otras dos bases miran lo que de verdad entró: «cobrado» es el bruto y
    # «neto_recibido» descuenta lo que se llevó la pasarela o el banco.
    columna = Pagos.monto_neto if regla.base == 'neto_recibido' else Pagos.monto_bruto
    cobrado = db.scalar(select(func.coalesce(func.sum(columna), 0))
                        .where(Pagos.negocio_id == negocio.id,
                               Pagos.estado == 'confirmado'))
    return Decimal(str(cobrado or 0))


def _posicion_en_la_meta(db: Session, negocio: Negocios, definicion: dict) -> int | None:
    """Qué número de venta premium es ésta, para esa vendedora, en ese periodo.

    Si es la primera, devuelve 1. Se cuenta por fecha de venta y, cuando dos
    caen el mismo día, por el orden en que se registraron: tiene que ser
    determinista, porque de ahí sale si le pagan el 10 % o el 7 %.
    """
    cuentan = definicion.get('servicios_que_cuentan_para_la_meta') or []
    if not cuentan:
        return None
    periodo = _periodo_de(negocio.fecha_venta)
    siguiente_mes = (periodo + dt.timedelta(days=32)).replace(day=1)

    anteriores = db.execute(
        select(func.count())
        .select_from(Negocios)
        .join(Servicios, Servicios.id == Negocios.servicio_id)
        .where(Negocios.vendedor_id == negocio.vendedor_id,
               Negocios.fecha_venta >= periodo,
               Negocios.fecha_venta < siguiente_mes,
               Servicios.codigo.in_(cuentan),
               (Negocios.fecha_venta < negocio.fecha_venta)
               | ((Negocios.fecha_venta == negocio.fecha_venta) & (Negocios.id < negocio.id)))
    ).scalar() or 0
    return anteriores + 1


def calcular(db: Session, negocio: Negocios, regla: ComisionesReglas) -> Calculo:
    """Cuánto le corresponde a la vendedora por esta venta, y por qué."""
    definicion = regla.definicion or {}
    base = _base_de_calculo(db, negocio, regla)
    servicio = db.get(Servicios, negocio.servicio_id)
    codigo = servicio.codigo if servicio else None

    porcentaje_base = Decimal(str(definicion.get('porcentaje_base', regla.porcentaje or 0)))
    porcentaje = porcentaje_base
    escalon = 'base'
    posicion = None
    explicacion = f'{porcentaje_base} % del valor de la venta.'

    if base == 0:
        explicacion = (f'El servicio «{codigo}» es recaudo de terceros: la tasa consular la paga '
                       f'el cliente directamente al consulado, así que no comisiona.')
    elif _es_premium(definicion, codigo):
        posicion = _posicion_en_la_meta(db, negocio, definicion)
        meta = definicion.get('meta_cantidad') or regla.meta_cantidad
        porcentaje_meta = definicion.get('porcentaje_meta')
        if meta and porcentaje_meta and posicion and posicion <= int(meta):
            porcentaje = Decimal(str(porcentaje_meta))
            escalon = 'meta'
            explicacion = (f'Venta premium n.º {posicion} del periodo: entra en las primeras '
                           f'{meta}, así que se paga al {porcentaje} % en vez del '
                           f'{porcentaje_base} %.')
        elif posicion:
            explicacion = (f'Venta premium n.º {posicion} del periodo: pasa de las primeras '
                           f'{meta}, así que vuelve al {porcentaje_base} %.')

    monto = (base * porcentaje / 100).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    return Calculo(
        base=base, porcentaje=porcentaje, monto=monto, escalon=escalon,
        posicion_en_la_meta=posicion, explicacion=explicacion,
        # La copia íntegra de la regla más lo que se decidió: es lo que permite
        # explicar el cálculo meses después sin reconstruir la tabla (RN-07).
        regla=dict(definicion) | {
            'regla_id': regla.id, 'regla_nombre': regla.nombre, 'base': regla.base,
            'porcentaje_aplicado': float(porcentaje), 'escalon': escalon,
            'posicion_en_la_meta': posicion, 'explicacion': explicacion,
            'congelada_en': dt.datetime.now(BOGOTA).isoformat(),
        })


# ------------------------------------------------------------- ciclo de vida

def registrar(db: Session, actor: Usuarios, negocio_id: int, *,
              ip: str | None = None) -> Comisiones | None:
    """Crea la comisión provisional de una venta (RF-051).

    Devuelve None cuando no hay a quién comisionarle o cuando el servicio no
    comisiona: una venta sin vendedor no es un error, es una venta que nadie
    cerró a nombre propio.
    """
    negocio = db.get(Negocios, negocio_id)
    if negocio is None:
        raise NoEncontrado('La venta no existe.')
    if not negocio.vendedor_id:
        return None

    regla = regla_para(db, negocio.vendedor_id, negocio.fecha_venta)
    if regla is None:
        return None

    existente = db.scalar(select(Comisiones).where(Comisiones.negocio_id == negocio_id,
                                                   Comisiones.vendedor_id == negocio.vendedor_id))
    if existente is not None:
        return existente

    c = calcular(db, negocio, regla)
    if c.monto <= 0:
        return None

    comision = Comisiones(negocio_id=negocio_id, vendedor_id=negocio.vendedor_id,
                          regla_id=regla.id, regla_aplicada=c.regla,
                          base_calculo=c.base, monto=c.monto, estado='provisional',
                          periodo=_periodo_de(negocio.fecha_venta))
    db.add(comision)
    db.flush()
    auditar(db, operacion='insert', entidad='comisiones', usuario_id=actor.id,
            entidad_id=comision.id, despues=instantanea(comision), ip=ip)
    db.commit()

    # Una venta premium no solo toma su puesto en el cupo del 10 %: si entró con
    # fecha anterior a otras del mismo mes, les corre un puesto a todas las de
    # atrás, y la que sale del cupo tiene que volver al 7 %.
    if c.posicion_en_la_meta is not None:
        reorden = reordenar_periodo(db, actor, negocio.vendedor_id, comision.periodo, ip=ip)
        _avisar_congeladas(db, actor, negocio.vendedor_id, reorden, ip=ip)

    # Nace con el estado que le corresponde. Las ventas que trajo la migración
    # llegaron pagadas y sin vendedora, así que cuando finanzas descubre de quién
    # era y se registra la comisión, no va a haber otro pago que la cause: nacía
    # provisional y se quedaba ahí para siempre.
    revisar_causacion(db, actor, negocio_id, ip=ip)
    db.refresh(comision)
    return comision


def saldo_en_plata(db: Session, negocio_id: int) -> Decimal | None:
    """Lo que el cliente todavía debe en plata, sin contar lo condonado.

    El saldo de la vista baja con las condonaciones, y condonar no es pagar:
    lleva el saldo a cero sin que entre un peso. La comisión se gana «cuando el
    cliente termina de pagar toda la venta», así que para decidir si se ganó hay
    que mirar la plata y no el saldo contable.

    El descuento sí cuenta, porque ahí el precio bajó de verdad: el cliente que
    paga el resto terminó de pagar lo que quedó acordado.
    """
    saldo = db.execute(text('select saldo from v_estado_financiero where negocio_id = :n'),
                       {'n': negocio_id}).scalar()
    if saldo is None:
        return None
    condonado = db.scalar(select(func.coalesce(func.sum(AjustesNegocio.monto), 0))
                          .where(AjustesNegocio.negocio_id == negocio_id,
                                 AjustesNegocio.tipo == 'condonacion')) or 0
    # Las condonaciones se guardan en negativo: devolverlas vuelve a subir el saldo.
    return Decimal(str(saldo)) - Decimal(str(condonado))


def revisar_causacion(db: Session, actor: Usuarios, negocio_id: int,
                      ip: str | None = None) -> Comisiones | None:
    """La comisión se gana cuando el cliente termina de pagar (D-03).

    Se llama después de registrar un pago: si ya no debe plata, la comisión pasa
    de provisional a causada. Si vuelve a deber —un pago reversado, un cargo—,
    vuelve a provisional: no se puede pagar una comisión de plata que no entró.

    Lo condonado no cuenta como pagado. Antes sí, porque se leía el saldo de la
    vista: condonar la venta entera dejaba el saldo en cero y causaba la comisión
    sobre una venta de la que no entró un peso, y esa comisión era liquidable.
    """
    comision = db.scalar(select(Comisiones).where(Comisiones.negocio_id == negocio_id))
    if comision is None or comision.estado not in MODIFICABLES:
        return comision

    saldo = saldo_en_plata(db, negocio_id)
    pagada_entera = saldo is not None and saldo <= 0
    nuevo = 'causada' if pagada_entera else 'provisional'
    if comision.estado == nuevo:
        return comision

    antes = instantanea(comision)
    comision.estado = nuevo
    db.flush()
    auditar(db, operacion='update', entidad='comisiones', usuario_id=actor.id,
            entidad_id=comision.id, antes=antes, despues=instantanea(comision), ip=ip)
    db.commit()
    return comision


def recalcular(db: Session, actor: Usuarios, negocio_id: int,
               ip: str | None = None) -> Comisiones | None:
    """Vuelve a calcular con la regla vigente a la fecha de la venta.

    Sirve cuando se corrige el valor pactado o la vendedora. No toca las
    liquidadas: esa plata ya se pagó y cambiarla a posteriori es reescribir la
    historia de un pago.
    """
    comision = db.scalar(select(Comisiones).where(Comisiones.negocio_id == negocio_id))
    if comision is None:
        return registrar(db, actor, negocio_id, ip=ip)
    if comision.estado not in MODIFICABLES:
        raise Conflicto('Esa comisión ya se liquidó: no se puede recalcular.',
                        codigo='comision_liquidada')

    negocio = db.get(Negocios, negocio_id)
    regla = regla_para(db, comision.vendedor_id, negocio.fecha_venta)
    if regla is None:
        return comision
    c = calcular(db, negocio, regla)
    antes = instantanea(comision)
    comision.regla_id, comision.regla_aplicada = regla.id, c.regla
    comision.base_calculo, comision.monto = c.base, c.monto
    db.flush()
    auditar(db, operacion='update', entidad='comisiones', usuario_id=actor.id,
            entidad_id=comision.id, antes=antes, despues=instantanea(comision), ip=ip)
    db.commit()

    # Corregir el valor pactado o la fecha de una venta premium cambia el reparto
    # del cupo del mes, no solo esta comisión.
    if c.posicion_en_la_meta is not None:
        reorden = reordenar_periodo(db, actor, comision.vendedor_id, comision.periodo, ip=ip)
        _avisar_congeladas(db, actor, comision.vendedor_id, reorden, ip=ip)
    revisar_causacion(db, actor, negocio_id, ip=ip)
    db.refresh(comision)
    return comision


@dataclass
class Reordenamiento:
    """Lo que cambió al volver a numerar el cupo de un mes."""
    corregidas: list[int]
    congeladas_fuera_de_meta: list[int]


def reordenar_periodo(db: Session, actor: Usuarios, vendedor_id: int, periodo: dt.date, *,
                      ip: str | None = None) -> Reordenamiento:
    """Vuelve a numerar el cupo del 10 % de un mes, de la primera venta a la última.

    El cupo se reparte por orden de fecha de venta, así que una venta que se
    registra hoy con fecha de la semana pasada no solo toma su puesto: les corre
    un puesto a todas las que venían detrás. Sin esto, la que salía del cupo se
    quedaba con el 10 % congelado y el mes terminaba con once comisiones al 10 %
    contra una meta de diez, y con dos filas afirmando ser la misma venta n.º 3.

    No es reescribir la historia. RN-07 congela la regla, y la regla dice que las
    primeras diez del mes van al 10 %; quién es «de las primeras diez» depende de
    qué ventas existen, y eso cambia cuando aparece una atrasada.

    Lo liquidado no se toca: esa plata ya salió. Pero si una comisión ya pagada
    quedó al escalón de la meta sin cupo, se devuelve en
    `congeladas_fuera_de_meta` para que el próximo corte no se cierre como si
    nada hubiera pasado.
    """
    primero = _periodo_de(periodo)
    corregidas: list[int] = []
    congeladas: list[int] = []

    del_mes = list(db.scalars(
        select(Comisiones).join(Negocios, Negocios.id == Comisiones.negocio_id)
        .where(Comisiones.vendedor_id == vendedor_id,
               Comisiones.periodo == primero,
               Comisiones.estado != 'anulada')
        .order_by(Negocios.fecha_venta, Negocios.id)))

    # Con una sola comisión en el mes no hay a quién correrle el puesto, y quien
    # llama acaba de calcularla. Es el caso corriente y se sale temprano.
    if len(del_mes) <= 1:
        return Reordenamiento(corregidas=[], congeladas_fuera_de_meta=[])

    for comision in del_mes:
        negocio = db.get(Negocios, comision.negocio_id)
        regla = regla_para(db, vendedor_id, negocio.fecha_venta)
        if regla is None:
            continue
        c = calcular(db, negocio, regla)
        guardada = comision.regla_aplicada or {}

        if comision.estado not in MODIFICABLES:
            if guardada.get('escalon') == 'meta' and c.escalon != 'meta':
                congeladas.append(comision.id)
            continue
        # Se compara también la posición: dos comisiones al mismo porcentaje pero
        # con la misma posición congelada dejan el mes diciendo una mentira.
        if (guardada.get('porcentaje_aplicado') == float(c.porcentaje)
                and guardada.get('posicion_en_la_meta') == c.posicion_en_la_meta
                and Decimal(str(comision.monto)) == c.monto):
            continue

        antes = instantanea(comision)
        comision.regla_id, comision.regla_aplicada = regla.id, c.regla
        comision.base_calculo, comision.monto = c.base, c.monto
        db.flush()
        auditar(db, operacion='update', entidad='comisiones', usuario_id=actor.id,
                entidad_id=comision.id, antes=antes,
                despues=instantanea(comision) | {'motivo': 'reparto del cupo del mes'}, ip=ip)
        corregidas.append(comision.id)

    if corregidas:
        db.commit()
    return Reordenamiento(corregidas=corregidas, congeladas_fuera_de_meta=congeladas)


# ------------------------------------------------------------- liquidación

def pendientes(db: Session, vendedor_id: int, periodo: dt.date) -> list[Comisiones]:
    """Lo que entraría en el corte: causado, sin liquidar, de este periodo o de
    uno anterior que se quedó por fuera.

    Lo de «o anterior» hace falta. Una comisión se causa cuando el cliente
    termina de pagar, y eso puede caer después de que el corte de su mes ya se
    cerró. Antes esa comisión se quedaba causada para siempre: el corte de su mes
    no se puede repetir y el del mes siguiente no la miraba, así que era plata que
    la vendedora se había ganado y no se le iba a pagar nunca.

    Cada comisión lleva su propio periodo, así que el corte de junio que arrastra
    una de mayo lo dice en la fila y no esconde de cuándo era.
    """
    return list(db.scalars(
        select(Comisiones)
        .where(Comisiones.vendedor_id == vendedor_id,
               Comisiones.periodo <= _periodo_de(periodo),
               Comisiones.estado == 'causada',
               Comisiones.liquidacion_id.is_(None))
        .options(selectinload(Comisiones.negocio))
        .order_by(Comisiones.periodo, Comisiones.id)))


def _puestos_repetidos(db: Session, vendedor_id: int, periodo: dt.date) -> list[int]:
    """Los puestos del cupo que más de una comisión del mes dice ocupar.

    Después de re-numerar no debería haber ninguno. Si hay, es un error de plata
    —dos ventas cobrando el mismo cupo del 10 %— y el corte no se cierra a
    ciegas: puede pasar si dos ventas del mismo día entran a la vez.
    """
    puestos: dict[int, int] = {}
    for c in db.scalars(select(Comisiones)
                        .where(Comisiones.vendedor_id == vendedor_id,
                               Comisiones.periodo == _periodo_de(periodo),
                               Comisiones.estado != 'anulada')):
        n = (c.regla_aplicada or {}).get('posicion_en_la_meta')
        if n is not None:
            puestos[n] = puestos.get(n, 0) + 1
    return sorted(n for n, cuantas in puestos.items() if cuantas > 1)


def _avisar_congeladas(db: Session, actor: Usuarios, vendedor_id: int,
                       reorden: 'Reordenamiento', ip: str | None = None) -> None:
    """Deja rastro de la plata que se pagó al 10 % y hoy no tiene cupo.

    Una venta con fecha atrasada puede sacar del cupo a una comisión que ya se
    liquidó. Esa plata ya salió y no se puede recalcular, así que lo único
    honesto es que quede anotado quién y por qué: sin esto, el sobrepago
    desaparece sin que nadie se entere.
    """
    if not reorden.congeladas_fuera_de_meta:
        return
    auditar(db, operacion='alerta', entidad='comisiones', usuario_id=actor.id,
            despues={'vendedor_id': vendedor_id,
                     'comisiones': reorden.congeladas_fuera_de_meta,
                     'motivo': 'una venta con fecha anterior las sacó del cupo del 10 %, '
                               'pero ya estaban liquidadas: esa plata ya salió'}, ip=ip)
    db.commit()


def liquidar(db: Session, actor: Usuarios, vendedor_id: int, periodo: dt.date, *,
             observaciones: str | None = None,
             ip: str | None = None) -> LiquidacionesComision:
    """El corte del periodo (RF-052).

    Las comisiones que entran quedan en estado `liquidada` y apuntan al corte,
    así que no pueden volver a entrar en otro. Es la diferencia entre un reporte
    y el registro de que esa plata ya se pagó.
    """
    if db.get(Usuarios, vendedor_id) is None:
        raise NoEncontrado('La vendedora no existe.')
    primero = _periodo_de(periodo)

    abierta = db.scalar(select(LiquidacionesComision)
                        .where(LiquidacionesComision.vendedor_id == vendedor_id,
                               LiquidacionesComision.periodo == primero,
                               LiquidacionesComision.estado != 'anulada'))
    if abierta is not None:
        raise Conflicto(f'Ya hay una liquidación de ese periodo (la #{abierta.id}). '
                        f'Anúlela antes de hacer otra.', codigo='periodo_ya_liquidado')

    # Antes de cerrar la plata se reparte otra vez el cupo de cada mes que entra
    # en el corte: si entró una venta con fecha atrasada, las posiciones de ese
    # mes ya no son las mismas.
    for mes in sorted({c.periodo for c in pendientes(db, vendedor_id, primero)}):
        reordenar_periodo(db, actor, vendedor_id, mes, ip=ip)
        repetidos = _puestos_repetidos(db, vendedor_id, mes)
        if repetidos:
            cuales = ', '.join('n.º %d' % n for n in repetidos)
            raise Conflicto(
                f'Dos ventas de {mes:%m/%Y} reclaman el mismo puesto del cupo ({cuales}), '
                f'así que el reparto del 10 % no cuadra y el corte pagaría de más. '
                f'Recalcule las comisiones de ese mes antes de cerrarlo.',
                codigo='cupo_inconsistente')

    comisiones = pendientes(db, vendedor_id, primero)
    if not comisiones:
        raise Invalido('No hay comisiones causadas sin liquidar hasta ese periodo. '
                       'Una comisión se causa cuando el cliente termina de pagar.',
                       codigo='sin_comisiones')

    total = sum((Decimal(str(c.monto)) for c in comisiones), Decimal('0'))
    liquidacion = LiquidacionesComision(
        vendedor_id=vendedor_id, periodo=primero, total=total, cantidad=len(comisiones),
        estado='abierta', observaciones=observaciones, liquidada_por=actor.id)
    db.add(liquidacion)
    db.flush()

    for c in comisiones:
        c.estado = 'liquidada'
        c.liquidacion_id = liquidacion.id
    db.flush()
    auditar(db, operacion='insert', entidad='liquidaciones_comision', usuario_id=actor.id,
            entidad_id=liquidacion.id,
            despues={'periodo': primero.isoformat(), 'total': str(total),
                     'comisiones': [c.id for c in comisiones]}, ip=ip)
    db.commit()
    return liquidacion


def marcar_pagada(db: Session, actor: Usuarios, liquidacion_id: int,
                  ip: str | None = None) -> LiquidacionesComision:
    liquidacion = db.get(LiquidacionesComision, liquidacion_id)
    if liquidacion is None:
        raise NoEncontrado('La liquidación no existe.')
    if liquidacion.estado != 'abierta':
        raise Conflicto(f'La liquidación está «{liquidacion.estado}».', codigo='estado_invalido')
    antes = instantanea(liquidacion)
    liquidacion.estado = 'pagada'
    liquidacion.pagada_en = dt.datetime.now(BOGOTA)
    db.flush()
    auditar(db, operacion='update', entidad='liquidaciones_comision', usuario_id=actor.id,
            entidad_id=liquidacion.id, antes=antes, despues=instantanea(liquidacion), ip=ip)
    db.commit()
    return liquidacion


def anular(db: Session, actor: Usuarios, liquidacion_id: int, motivo: str,
           ip: str | None = None) -> LiquidacionesComision:
    """Deshace el corte y devuelve las comisiones a «causada».

    No se borra: queda la liquidación anulada con su motivo, para que la
    historia muestre que hubo un corte y por qué se deshizo.
    """
    liquidacion = db.get(LiquidacionesComision, liquidacion_id)
    if liquidacion is None:
        raise NoEncontrado('La liquidación no existe.')
    if not motivo or not motivo.strip():
        raise Invalido('Escriba por qué se anula la liquidación.', codigo='falta_motivo')
    antes = instantanea(liquidacion)
    devueltas = list(db.scalars(select(Comisiones)
                                .where(Comisiones.liquidacion_id == liquidacion_id)))
    ventas = [c.negocio_id for c in devueltas]
    for c in devueltas:
        c.estado = 'causada'
        c.liquidacion_id = None
    liquidacion.estado = 'anulada'
    liquidacion.observaciones = f'{liquidacion.observaciones or ""}\nAnulada: {motivo}'.strip()
    db.flush()
    auditar(db, operacion='update', entidad='liquidaciones_comision', usuario_id=actor.id,
            entidad_id=liquidacion.id, antes=antes, despues=instantanea(liquidacion), ip=ip)
    db.commit()

    # Devolverlas a «causada» a ciegas dejaba listas para el próximo corte
    # comisiones cuya venta se quedó sin pagar DESPUÉS del corte: un reverso del
    # banco no las tocaba porque ya estaban liquidadas. Se vuelve a mirar el saldo.
    for negocio_id in ventas:
        revisar_causacion(db, actor, negocio_id, ip=ip)
    db.refresh(liquidacion)
    return liquidacion


def descuadres(db: Session, vendedor_id: int | None = None) -> list[dict]:
    """Comisiones ganadas o ya pagadas sobre ventas que todavía deben plata.

    Es el invariante del módulo: ninguna comisión causada o liquidada puede
    pertenecer a una venta que no está pagada. Se rompe por el camino que el
    estado no alcanza a cubrir —el banco reversa un pago **después** del corte, y
    la comisión ya liquidada no se puede devolver a provisional porque esa plata
    ya se giró—, y hasta ahora nada lo vigilaba.

    No corrige nada a propósito: devuelve la lista para que alguien la mire. El
    centro de alertas la va a mostrar; mientras tanto, al menos se puede
    consultar.
    """
    filtro = 'and c.vendedor_id = :v' if vendedor_id else ''
    filas = db.execute(text(f"""
        select c.id, c.negocio_id, c.vendedor_id, c.monto, c.estado, c.periodo,
               f.saldo - coalesce(cond.condonado, 0) as debe,
               l.id as liquidacion_id, l.estado as corte
          from comisiones c
          join v_estado_financiero f on f.negocio_id = c.negocio_id
          left join liquidaciones_comision l on l.id = c.liquidacion_id
          left join lateral (
                select sum(monto) as condonado from ajustes_negocio a
                 where a.negocio_id = c.negocio_id and a.tipo = 'condonacion') cond on true
         where c.estado in ('causada', 'liquidada')
           and f.saldo - coalesce(cond.condonado, 0) > 0
           {filtro}
         order by c.periodo desc, c.id
    """), {'v': vendedor_id} if vendedor_id else {}).mappings().all()
    return [dict(f) for f in filas]


def comisiones_de(db: Session, *, vendedor_id: int | None = None, periodo: dt.date | None = None,
                  estado: str | None = None) -> list[Comisiones]:
    consulta = select(Comisiones).options(selectinload(Comisiones.negocio),
                                          selectinload(Comisiones.vendedor))
    if vendedor_id:
        consulta = consulta.where(Comisiones.vendedor_id == vendedor_id)
    if periodo:
        consulta = consulta.where(Comisiones.periodo == _periodo_de(periodo))
    if estado:
        consulta = consulta.where(Comisiones.estado == estado)
    return list(db.scalars(consulta.order_by(Comisiones.periodo.desc(), Comisiones.id)))
