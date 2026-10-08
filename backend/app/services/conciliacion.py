"""Conciliar el extracto del banco contra los pagos (RF-044).

La administradora explicó el 07/10/2026 cómo lo resuelve hoy:

> «el cliente manda el soporte por whatsapp y también me llega la notificación
> del correo, entonces a veces el nombre es el de ellos otras veces es de otra
> persona, pero a la final el cliente nos avisa y nos comparte el pantallazo»

Esa frase decide todo el diseño de este módulo.

**No se cruza por nombre.** Muchas veces quien consigna no es el cliente —paga el
esposo, la mamá, un amigo—, así que cruzar por nombre produciría asignaciones
falsas. Y una asignación falsa es peor que no asignar: deja una venta marcada
como pagada con plata de otro, y nadie lo descubre hasta que el cliente reclama.
Además, en el extracto real 182 de 192 movimientos dicen apenas «TRANSFERENCIA
CTA SUC VIRTUAL», así que no habría ni de dónde sacar el nombre.

**Se cruza por valor y fecha, y solo cuando no hay duda.** Si un movimiento
calza con exactamente un pago, se propone. Si calza con varios, no se adivina:
se muestran los dos y alguien decide. El automático existe para ahorrarle las
que son obvias, no para reemplazarla.

**Lo que no cruza no desaparece.** Queda en la bandeja, que es donde ella hace lo
que ya hacía en la columna CLIENTE del Excel. Y lo que no es plata de un cliente
—intereses de ahorro de cinco pesos, reversos de compras, plata personal— se
descarta con su motivo, que es distinto de borrarlo.

La regla de oro del módulo: **este servicio nunca decide solo que una venta quedó
pagada.** Propone; la persona confirma. Lo único que hace sin preguntar es
descartar nada y proponer lo evidente.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import Conflicto, Invalido, NoEncontrado
from app.models.esquema import MovimientosBanco, Negocios, Pagos, Usuarios
from app.services import pagos as serv_pagos
from app.services.auditoria import auditar, instantanea

BOGOTA = ZoneInfo('America/Bogota')

# El banco puede fechar un día distinto al del comprobante que manda el cliente:
# una transferencia de la noche aparece al día siguiente, y un fin de semana
# corre hasta el lunes. Tres días cubre eso sin volver ambiguo todo el mes.
DIAS_DE_GRACIA = 3

ESTADOS = ('sin_conciliar', 'conciliado', 'parcial', 'duplicado',
           'reversado', 'descartado')
# Una vez que el movimiento apunta a un pago, cambiarle el estado sin
# deshacer primero dejaría el cruce colgando.
CUADRADOS = ('conciliado', 'parcial')


def huella(banco: str, fecha: dt.date, valor: Decimal | float,
           descripcion: str | None, fila: int | None) -> str:
    """Identifica una línea del extracto para no importarla dos veces.

    Entra la fila de origen porque un mismo banco puede tener dos movimientos
    idénticos el mismo día —dos clientes que consignan 200.000— y son dos, no
    uno. Sin la fila, el segundo se perdería en cada importación.
    """
    crudo = f'{banco}|{fecha:%Y-%m-%d}|{Decimal(str(valor)):.2f}|{descripcion or ""}|{fila or ""}'
    return hashlib.sha256(crudo.encode('utf-8')).hexdigest()


# ------------------------------------------------------------- importación

@dataclass
class Importacion:
    """Lo que dejó una importación del extracto."""
    nuevos: int
    repetidos: int
    sin_fecha: int
    sin_valor: int
    movimientos: list[int]

    @property
    def leidos(self) -> int:
        return self.nuevos + self.repetidos + self.sin_fecha + self.sin_valor


def importar(db: Session, actor: Usuarios, filas: list[dict], *,
             archivo: str | None = None, hoja: str | None = None,
             ip: str | None = None) -> Importacion:
    """Mete las líneas del extracto, sin duplicar lo que ya estaba (RF-044).

    Se puede correr dos veces el mismo archivo sin consecuencias: la huella
    bloquea el repetido. Es la misma garantía que ya tiene la migración de los
    Excel, y por la misma razón: el que importa no debería tener que acordarse
    de si ya lo hizo.

    Una fila sin fecha o sin valor no se importa ni se inventa: se cuenta aparte
    para que quede dicho que esas líneas del archivo no entraron.
    """
    res = Importacion(nuevos=0, repetidos=0, sin_fecha=0, sin_valor=0, movimientos=[])

    for n, f in enumerate(filas, start=1):
        fecha = f.get('fecha')
        if isinstance(fecha, dt.datetime):
            fecha = fecha.date()
        if not isinstance(fecha, dt.date):
            res.sin_fecha += 1
            continue
        valor = f.get('valor')
        if valor is None or Decimal(str(valor)) == 0:
            res.sin_valor += 1
            continue

        banco = (f.get('banco') or 'SIN BANCO').strip()[:60]
        fila = f.get('fila', n)
        h = huella(banco, fecha, valor, f.get('descripcion'), fila)
        if db.scalar(select(MovimientosBanco.id).where(MovimientosBanco.huella == h)):
            res.repetidos += 1
            continue

        m = MovimientosBanco(
            banco=banco, fecha=fecha, valor=Decimal(str(valor)),
            descripcion=(f.get('descripcion') or None),
            referencia=(f.get('referencia') or None),
            moneda=(f.get('moneda') or 'COP'),
            banco_cuenta_id=f.get('banco_cuenta_id'),
            nota_cliente=(f.get('nota_cliente') or None),
            nota_abono=(f.get('nota_abono') or None),
            observacion=(f.get('observacion') or None),
            estado='sin_conciliar', huella=h,
            origen_archivo=archivo, origen_hoja=hoja, origen_fila=fila)
        db.add(m)
        db.flush()
        res.nuevos += 1
        res.movimientos.append(m.id)

    if res.nuevos:
        auditar(db, operacion='insert', entidad='movimientos_banco', usuario_id=actor.id,
                despues={'archivo': archivo, 'hoja': hoja, 'nuevos': res.nuevos,
                         'repetidos': res.repetidos}, ip=ip)
    db.commit()
    return res


# ------------------------------------------------------------------ cruce

@dataclass
class Candidato:
    """Un pago que podría ser este movimiento, y por qué."""
    pago_id: int
    negocio_id: int | None
    cliente: str | None
    fecha: dt.date
    monto: float
    dias_de_diferencia: int
    exacto: bool


def candidatos(db: Session, movimiento: MovimientosBanco, *,
               dias: int = DIAS_DE_GRACIA) -> list[Candidato]:
    """Los pagos que calzan por valor y fecha. Por nombre, nunca.

    Solo se miran pagos que no estén ya cuadrados contra otro movimiento: la
    misma plata no puede cuadrar dos veces.
    """
    ya_cuadrados = select(MovimientosBanco.pago_id).where(
        MovimientosBanco.pago_id.is_not(None), MovimientosBanco.estado == 'conciliado')
    desde = movimiento.fecha - dt.timedelta(days=dias)
    hasta = movimiento.fecha + dt.timedelta(days=dias)

    filas = db.scalars(
        select(Pagos)
        .where(Pagos.monto_bruto == movimiento.valor,
               Pagos.fecha >= desde, Pagos.fecha <= hasta,
               Pagos.moneda == movimiento.moneda,
               Pagos.estado.in_(('confirmado', 'no_identificado')),
               Pagos.id.not_in(ya_cuadrados))
        .options(selectinload(Pagos.negocio).selectinload(Negocios.cliente))
        .order_by(Pagos.fecha, Pagos.id)).all()

    salida = []
    for p in filas:
        cliente = None
        if p.negocio is not None and p.negocio.cliente is not None:
            cliente = p.negocio.cliente.nombre
        salida.append(Candidato(
            pago_id=p.id, negocio_id=p.negocio_id, cliente=cliente,
            fecha=p.fecha, monto=float(p.monto_bruto),
            dias_de_diferencia=abs((p.fecha - movimiento.fecha).days),
            exacto=p.fecha == movimiento.fecha))
    # Primero el del mismo día: es el que tiene más probabilidad de ser.
    salida.sort(key=lambda c: (c.dias_de_diferencia, c.pago_id))
    return salida


def obtener(db: Session, movimiento_id: int) -> MovimientosBanco:
    m = db.get(MovimientosBanco, movimiento_id)
    if m is None:
        raise NoEncontrado('El movimiento del banco no existe.')
    return m


def sugerencias(db: Session, movimiento_id: int, *,
                dias: int = DIAS_DE_GRACIA) -> tuple[MovimientosBanco, list[Candidato]]:
    m = obtener(db, movimiento_id)
    return m, candidatos(db, m, dias=dias)


def cruzar_automatico(db: Session, actor: Usuarios, *, desde: dt.date | None = None,
                      hasta: dt.date | None = None, dias: int = DIAS_DE_GRACIA,
                      ip: str | None = None) -> dict:
    """Cuadra solas las que no tienen duda, y deja el resto a la vista.

    «Sin duda» es estricto a propósito: un solo pago candidato y del mismo día.
    Si hay dos pagos de 200.000 esa semana, los dos se quedan sin cuadrar y
    alguien decide, porque equivocarse aquí es marcar pagada la venta de otro.
    """
    consulta = select(MovimientosBanco).where(MovimientosBanco.estado == 'sin_conciliar')
    if desde:
        consulta = consulta.where(MovimientosBanco.fecha >= desde)
    if hasta:
        consulta = consulta.where(MovimientosBanco.fecha <= hasta)

    cuadrados, ambiguos, sin_candidato = 0, 0, 0
    for m in db.scalars(consulta.order_by(MovimientosBanco.fecha, MovimientosBanco.id)):
        posibles = candidatos(db, m, dias=dias)
        exactos = [c for c in posibles if c.exacto]
        if len(exactos) == 1:
            _enlazar(db, actor, m, exactos[0].pago_id, automatico=True, ip=ip)
            cuadrados += 1
        elif posibles:
            ambiguos += 1
        else:
            sin_candidato += 1
    db.commit()
    return {'cuadrados': cuadrados, 'ambiguos': ambiguos, 'sin_candidato': sin_candidato}


# ------------------------------------------------------------ conciliación

def _enlazar(db: Session, actor: Usuarios, m: MovimientosBanco, pago_id: int, *,
             automatico: bool = False, ip: str | None = None) -> MovimientosBanco:
    pago = db.get(Pagos, pago_id)
    if pago is None:
        raise NoEncontrado('El pago no existe.')
    otro = db.scalar(select(MovimientosBanco)
                     .where(MovimientosBanco.pago_id == pago_id,
                            MovimientosBanco.id != m.id))
    if otro is not None:
        raise Conflicto(f'Ese pago ya está cuadrado contra el movimiento #{otro.id}. '
                        f'La misma plata no puede entrar dos veces.',
                        codigo='pago_ya_conciliado')
    if Decimal(str(pago.monto_bruto)) != Decimal(str(m.valor)):
        raise Invalido(f'El movimiento es de {m.valor:,.0f} y el pago de '
                       f'{pago.monto_bruto:,.0f}. Si de verdad son el mismo, corrija primero '
                       f'el valor del pago.', codigo='valores_distintos')

    antes = instantanea(m)
    m.pago_id = pago_id
    m.estado = 'conciliado'
    m.conciliado_por = actor.id
    m.conciliado_en = dt.datetime.now(BOGOTA)
    db.flush()
    auditar(db, operacion='update', entidad='movimientos_banco', usuario_id=actor.id,
            entidad_id=m.id, antes=antes,
            despues=instantanea(m) | {'automatico': automatico}, ip=ip)
    return m


def conciliar(db: Session, actor: Usuarios, movimiento_id: int, *,
              pago_id: int | None = None, negocio_id: int | None = None,
              ip: str | None = None) -> MovimientosBanco:
    """Cuadra un movimiento contra un pago, o contra una venta creando el pago.

    Lo segundo es el caso de ella: el cliente avisa por WhatsApp que consignó,
    pero el pago todavía no está registrado. Entonces el movimiento del banco es
    la evidencia y de ahí nace el pago, con la fecha y el valor del banco, que
    son más confiables que los que alguien teclee después.
    """
    m = obtener(db, movimiento_id)
    if m.estado in CUADRADOS:
        raise Conflicto(f'El movimiento ya está cuadrado contra el pago #{m.pago_id}.',
                        codigo='ya_conciliado')
    if (pago_id is None) == (negocio_id is None):
        raise Invalido('Diga contra qué se cuadra: un pago que ya existe o la venta a la '
                       'que hay que abonarle.', codigo='falta_destino')

    if negocio_id is not None:
        if db.get(Negocios, negocio_id) is None:
            raise NoEncontrado('La venta no existe.')
        pago = serv_pagos.registrar(db, actor, {
            'negocio_id': negocio_id, 'fecha': m.fecha, 'monto_bruto': float(m.valor),
            'moneda': m.moneda, 'banco_cuenta_id': m.banco_cuenta_id,
            'referencia': m.referencia,
            'observacion': f'Creado al cuadrar el movimiento del banco #{m.id} '
                           f'({m.banco}, {m.fecha:%d/%m/%Y}).',
        }, ip=ip)
        pago_id = pago.id

    _enlazar(db, actor, m, pago_id, ip=ip)
    db.commit()
    db.refresh(m)
    return m


def descartar(db: Session, actor: Usuarios, movimiento_id: int, motivo: str,
              ip: str | None = None) -> MovimientosBanco:
    """Marca un movimiento como «no es plata de un cliente», con su razón.

    En el extracto real hay intereses de ahorro de cinco pesos, reversos de
    compras y plata personal. Descartar no es borrar: la línea sigue ahí con el
    motivo, porque el extracto tiene que seguir cuadrando con el banco.
    """
    m = obtener(db, movimiento_id)
    if m.estado in CUADRADOS:
        raise Conflicto('Ese movimiento ya está cuadrado contra un pago. Deshaga el cuadre '
                        'antes de descartarlo.', codigo='ya_conciliado')
    if not motivo or not motivo.strip():
        raise Invalido('Escriba por qué este movimiento no es un pago de cliente.',
                       codigo='falta_motivo')
    antes = instantanea(m)
    m.estado = 'descartado'
    m.motivo_descarte = motivo.strip()[:300]
    db.flush()
    auditar(db, operacion='update', entidad='movimientos_banco', usuario_id=actor.id,
            entidad_id=m.id, antes=antes, despues=instantanea(m), ip=ip)
    db.commit()
    return m


def marcar_parcial(db: Session, actor: Usuarios, movimiento_id: int, pago_id: int,
                   ip: str | None = None) -> MovimientosBanco:
    """El movimiento cubre solo una parte de un pago, o al revés.

    Pasa de dos formas, y las dos son corrientes: el cliente paga una venta con
    dos transferencias, o manda una sola que cubre dos ventas. No se puede decir
    que cuadra uno a uno, pero tampoco es cierto que no tenga que ver. Queda
    marcado como parcial, apuntando al pago, y el extracto muestra que ese cruce
    está a medias en vez de darlo por cerrado.
    """
    m = obtener(db, movimiento_id)
    if m.estado in CUADRADOS:
        raise Conflicto(f'El movimiento ya está cuadrado contra el pago #{m.pago_id}. '
                        f'Deshaga el cruce antes de volver a marcarlo.',
                        codigo='ya_conciliado')
    pago = db.get(Pagos, pago_id)
    if pago is None:
        raise NoEncontrado('El pago no existe.')
    if Decimal(str(pago.monto_bruto)) == Decimal(str(m.valor)):
        raise Invalido('El movimiento y el pago son del mismo valor: eso no es un cruce '
                       'parcial, es un cuadre. Use «conciliar».', codigo='mismo_valor')

    antes = instantanea(m)
    m.estado = 'parcial'
    m.pago_id = pago_id
    m.conciliado_por = actor.id
    m.conciliado_en = dt.datetime.now(BOGOTA)
    db.flush()
    auditar(db, operacion='update', entidad='movimientos_banco', usuario_id=actor.id,
            entidad_id=m.id, antes=antes, despues=instantanea(m), ip=ip)
    db.commit()
    return m


def marcar_duplicado(db: Session, actor: Usuarios, movimiento_id: int,
                     duplicado_de_id: int, ip: str | None = None) -> MovimientosBanco:
    """El banco reportó dos veces la misma transferencia.

    Se marca la repetida y se apunta a la buena. No se borra, porque el extracto
    tiene que seguir cuadrando línea por línea contra lo que mandó el banco; lo
    que cambia es que deja de pedir que alguien le encuentre dueño.
    """
    m = obtener(db, movimiento_id)
    if m.estado in CUADRADOS:
        raise Conflicto('Ese movimiento ya está cuadrado contra un pago. Deshaga el cruce '
                        'antes de marcarlo repetido.', codigo='ya_conciliado')
    if duplicado_de_id == movimiento_id:
        raise Invalido('Un movimiento no puede ser repetido de sí mismo.',
                       codigo='duplicado_de_si_mismo')
    original = db.get(MovimientosBanco, duplicado_de_id)
    if original is None:
        raise NoEncontrado('El movimiento del que sería repetido no existe.')
    if original.estado == 'duplicado':
        raise Invalido(f'El movimiento #{duplicado_de_id} ya está marcado como repetido de '
                       f'otro. Apunte al original.', codigo='cadena_de_duplicados')

    antes = instantanea(m)
    m.estado = 'duplicado'
    m.duplicado_de_id = duplicado_de_id
    m.pago_id = None
    db.flush()
    auditar(db, operacion='update', entidad='movimientos_banco', usuario_id=actor.id,
            entidad_id=m.id, antes=antes, despues=instantanea(m), ip=ip)
    db.commit()
    return m


def marcar_reversado(db: Session, actor: Usuarios, movimiento_id: int, motivo: str,
                     ip: str | None = None) -> MovimientosBanco:
    """La plata entró y se devolvió.

    En el extracto real hay varias: «Reverso COMPRA INTLTRI». No es plata de la
    empresa aunque aparezca como ingreso, así que no puede quedar esperando a que
    alguien le encuentre un cliente.
    """
    m = obtener(db, movimiento_id)
    if m.estado in CUADRADOS:
        raise Conflicto('Ese movimiento ya está cuadrado contra un pago. Deshaga el cruce '
                        'antes de marcarlo reversado.', codigo='ya_conciliado')
    if not motivo or not motivo.strip():
        raise Invalido('Escriba por qué se reversó este movimiento.', codigo='falta_motivo')
    antes = instantanea(m)
    m.estado = 'reversado'
    m.motivo_descarte = motivo.strip()[:300]
    db.flush()
    auditar(db, operacion='update', entidad='movimientos_banco', usuario_id=actor.id,
            entidad_id=m.id, antes=antes, despues=instantanea(m), ip=ip)
    db.commit()
    return m


def deshacer(db: Session, actor: Usuarios, movimiento_id: int,
             ip: str | None = None) -> MovimientosBanco:
    """Devuelve un movimiento a la bandeja. No borra el pago que se le creó.

    Si al cuadrar se creó un pago, ese pago queda y hay que anularlo aparte: lo
    que se deshace acá es la afirmación de que esta línea del banco es ese pago,
    no el registro de que entró la plata.
    """
    m = obtener(db, movimiento_id)
    if m.estado == 'sin_conciliar':
        return m
    antes = instantanea(m)
    m.estado = 'sin_conciliar'
    m.pago_id = None
    m.motivo_descarte = None
    m.duplicado_de_id = None
    m.conciliado_por = None
    m.conciliado_en = None
    db.flush()
    auditar(db, operacion='update', entidad='movimientos_banco', usuario_id=actor.id,
            entidad_id=m.id, antes=antes, despues=instantanea(m), ip=ip)
    db.commit()
    return m


# ------------------------------------------------------------------ lectura

def bandeja(db: Session, *, estado: str | None = 'sin_conciliar',
            desde: dt.date | None = None, hasta: dt.date | None = None,
            banco: str | None = None, pagina: int = 1,
            tamano: int = 50) -> tuple[int, float, list[MovimientosBanco]]:
    """Lo que falta por cuadrar, de lo más reciente a lo más viejo."""
    consulta = select(MovimientosBanco)
    if estado:
        if estado not in ESTADOS:
            raise Invalido(f'Estado inválido: «{estado}». Opciones: {", ".join(ESTADOS)}.')
        consulta = consulta.where(MovimientosBanco.estado == estado)
    if desde:
        consulta = consulta.where(MovimientosBanco.fecha >= desde)
    if hasta:
        consulta = consulta.where(MovimientosBanco.fecha <= hasta)
    if banco:
        consulta = consulta.where(MovimientosBanco.banco.ilike(f'%{banco}%'))

    sub = consulta.subquery()
    total = db.scalar(select(func.count()).select_from(sub)) or 0
    suma = db.scalar(select(func.coalesce(func.sum(sub.c.valor), 0))) or 0
    # El cliente se muestra en cada fila de la bandeja. Sin traerlo de una, cada
    # movimiento cuesta tres consultas mas y una bandeja de 200 lineas se vuelve
    # seiscientas idas a la base.
    filas = list(db.scalars(
        consulta.options(selectinload(MovimientosBanco.pago)
                         .selectinload(Pagos.negocio)
                         .selectinload(Negocios.cliente))
        .order_by(MovimientosBanco.fecha.desc(), MovimientosBanco.id.desc())
        .offset(max(0, pagina - 1) * tamano).limit(tamano)))
    return total, float(suma), filas


def resumen(db: Session, *, desde: dt.date | None = None,
            hasta: dt.date | None = None) -> dict:
    """Cuánto del extracto está cuadrado y cuánto no.

    Es el número que dice si la conciliación va al día, y el que se compara
    contra el banco al cerrar el mes.
    """
    consulta = select(MovimientosBanco.estado,
                      func.count().label('cuantos'),
                      func.coalesce(func.sum(MovimientosBanco.valor), 0).label('total'))
    if desde:
        consulta = consulta.where(MovimientosBanco.fecha >= desde)
    if hasta:
        consulta = consulta.where(MovimientosBanco.fecha <= hasta)

    por_estado = {e: {'cuantos': 0, 'total': 0.0} for e in ESTADOS}
    for estado, cuantos, total in db.execute(consulta.group_by(MovimientosBanco.estado)):
        por_estado[estado] = {'cuantos': cuantos, 'total': float(total)}
    return por_estado
