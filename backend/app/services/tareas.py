"""Tareas con responsable, vencimiento y prioridad (RF-060).

Una tarea es lo que alguien tiene que hacer y todavía no hizo. Hoy eso vive en
la cabeza de cada asesora, en un cuaderno o en un chat, y es la razón por la que
un trámite se queda quieto sin que nadie se entere: nadie sabía que le tocaba.

Tres decisiones que valen la pena explicar:

**Una tarea siempre cuelga de algo.** La base exige que tenga cliente, venta,
oportunidad o trámite (el `check` de `num_nonnulls`). Una tarea suelta —«llamar a
la señora»— no se puede retomar tres semanas después, porque nadie se acuerda de
cuál señora.

**Cerrar no es borrar.** Una tarea hecha o cancelada se queda con su fecha de
cierre. Lo que se hizo y lo que se decidió no hacer son las dos mitades de la
misma historia, y la segunda es la que explica por qué un trámite se detuvo.

**El vencimiento es en hora de Bogotá.** Quien escribe «vence el jueves» quiere
decir el jueves de acá. El servidor corre en UTC, así que una fecha sin zona se
guarda cinco horas antes y una tarea del jueves a las 8 de la mañana vence el
miércoles por la noche.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import Invalido, NoEncontrado
from app.models.esquema import Casos, Clientes, Negocios, Oportunidades, Tareas, Usuarios
from app.services.auditoria import auditar, instantanea
from app.services.casos import alcance_de

BOGOTA = ZoneInfo('America/Bogota')

ESTADOS = ('pendiente', 'en_curso', 'hecha', 'cancelada')
ABIERTAS = ('pendiente', 'en_curso')
CERRADAS = ('hecha', 'cancelada')
PRIORIDADES = ('baja', 'media', 'alta')
# El orden en que se muestran: lo urgente arriba, y a igual urgencia lo que
# vence antes. Una lista ordenada por id es una lista que nadie usa.
_ORDEN_PRIORIDAD = {'alta': 0, 'media': 1, 'baja': 2}


def _ahora() -> dt.datetime:
    return dt.datetime.now(BOGOTA)


def _con_zona(v: dt.datetime | dt.date | None) -> dt.datetime | None:
    """Una fecha sin hora vence al final del día, en Bogotá.

    «Vence el jueves» no significa el jueves a medianoche: significa que el
    jueves todavía está a tiempo.
    """
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=BOGOTA)
    return dt.datetime.combine(v, dt.time(23, 59), tzinfo=BOGOTA)


def _limite_de_alcance(actor: Usuarios | None):
    """Qué tareas puede ver quien no lo ve todo (RNF-03).

    Las suyas, y las de los trámites de los que es responsable. Una tarea de un
    trámite ajeno enseña el nombre del cliente y qué se está haciendo con él.
    """
    if actor is None or actor.alcance == 'todos':
        return None
    suyos = select(Casos.id).where(Casos.responsable_id == actor.id)
    return or_(Tareas.responsable_id == actor.id, Tareas.caso_id.in_(suyos))


def crear(db: Session, actor: Usuarios, datos: dict, *, ip: str | None = None) -> Tareas:
    """Una tarea nueva. Si no se dice de quién es, es de quien la crea."""
    titulo = (datos.get('titulo') or '').strip()
    if len(titulo) < 3:
        raise Invalido('Escriba de qué se trata la tarea.', codigo='falta_titulo')

    vinculos = {k: datos.get(k) for k in ('caso_id', 'negocio_id', 'oportunidad_id', 'cliente_id')}
    if not any(vinculos.values()):
        raise Invalido('Diga a qué cliente, venta, oportunidad o trámite pertenece la tarea. '
                       'Una tarea suelta no se puede retomar después.', codigo='sin_vinculo')
    for campo, modelo in (('caso_id', Casos), ('negocio_id', Negocios),
                          ('oportunidad_id', Oportunidades), ('cliente_id', Clientes)):
        if vinculos[campo] and db.get(modelo, vinculos[campo]) is None:
            raise NoEncontrado(f'No existe el registro de «{campo}».')

    prioridad = datos.get('prioridad') or 'media'
    if prioridad not in PRIORIDADES:
        raise Invalido(f'Prioridad inválida. Opciones: {", ".join(PRIORIDADES)}.')

    responsable_id = datos.get('responsable_id') or actor.id
    if db.get(Usuarios, responsable_id) is None:
        raise NoEncontrado('El responsable no existe.')

    t = Tareas(titulo=titulo, descripcion=(datos.get('descripcion') or None),
               responsable_id=responsable_id, prioridad=prioridad, estado='pendiente',
               vence_en=_con_zona(datos.get('vence_en')),
               origen=datos.get('origen') or 'manual', creado_por=actor.id, **vinculos)
    db.add(t)
    db.flush()
    auditar(db, operacion='insert', entidad='tareas', usuario_id=actor.id, entidad_id=t.id,
            despues=instantanea(t), ip=ip)
    db.commit()
    return t


def obtener(db: Session, tarea_id: int, *, actor: Usuarios | None = None) -> Tareas:
    consulta = select(Tareas).where(Tareas.id == tarea_id)
    limite = _limite_de_alcance(actor)
    if limite is not None:
        consulta = consulta.where(limite)
    t = db.scalars(consulta).first()
    if t is None:
        # 404 y no 403: decir «existe pero no la ve» ya es decir que existe.
        raise NoEncontrado('La tarea no existe.')
    return t


def cambiar(db: Session, actor: Usuarios, tarea_id: int, cambios: dict,
            *, ip: str | None = None) -> Tareas:
    """Mueve el estado, el responsable, la prioridad o el vencimiento.

    Cerrar deja la fecha de cierre; reabrir la quita, porque una tarea abierta
    con fecha de cierre es una contradicción que después nadie sabe leer.
    """
    t = obtener(db, tarea_id, actor=actor)
    antes = instantanea(t)

    if 'estado' in cambios and cambios['estado'] is not None:
        nuevo = cambios['estado']
        if nuevo not in ESTADOS:
            raise Invalido(f'Estado inválido. Opciones: {", ".join(ESTADOS)}.')
        t.estado = nuevo
        t.cerrada_en = _ahora() if nuevo in CERRADAS else None
    if cambios.get('responsable_id'):
        if db.get(Usuarios, cambios['responsable_id']) is None:
            raise NoEncontrado('El responsable no existe.')
        t.responsable_id = cambios['responsable_id']
    if cambios.get('prioridad'):
        if cambios['prioridad'] not in PRIORIDADES:
            raise Invalido(f'Prioridad inválida. Opciones: {", ".join(PRIORIDADES)}.')
        t.prioridad = cambios['prioridad']
    if 'vence_en' in cambios:
        t.vence_en = _con_zona(cambios['vence_en'])
    if cambios.get('titulo'):
        t.titulo = cambios['titulo'].strip()
    if 'descripcion' in cambios:
        t.descripcion = cambios['descripcion']

    db.flush()
    auditar(db, operacion='update', entidad='tareas', usuario_id=actor.id, entidad_id=t.id,
            antes=antes, despues=instantanea(t), ip=ip)
    db.commit()
    return t


def listar(db: Session, *, actor: Usuarios | None = None, responsable_id: int | None = None,
           estado: str | None = None, prioridad: str | None = None,
           caso_id: int | None = None, negocio_id: int | None = None,
           cliente_id: int | None = None, solo_abiertas: bool = True,
           vencidas: bool = False, pagina: int = 1,
           tamano: int = 50) -> tuple[int, list[Tareas]]:
    """Las tareas, lo urgente arriba."""
    consulta: Select = select(Tareas).options(
        selectinload(Tareas.responsable), selectinload(Tareas.caso),
        selectinload(Tareas.cliente))
    limite = _limite_de_alcance(actor)
    if limite is not None:
        consulta = consulta.where(limite)
    if estado:
        if estado not in ESTADOS:
            raise Invalido(f'Estado inválido. Opciones: {", ".join(ESTADOS)}.')
        consulta = consulta.where(Tareas.estado == estado)
    elif solo_abiertas:
        consulta = consulta.where(Tareas.estado.in_(ABIERTAS))
    if prioridad:
        consulta = consulta.where(Tareas.prioridad == prioridad)
    if responsable_id:
        consulta = consulta.where(Tareas.responsable_id == responsable_id)
    if caso_id:
        consulta = consulta.where(Tareas.caso_id == caso_id)
    if negocio_id:
        consulta = consulta.where(Tareas.negocio_id == negocio_id)
    if cliente_id:
        consulta = consulta.where(Tareas.cliente_id == cliente_id)
    if vencidas:
        consulta = consulta.where(Tareas.vence_en.is_not(None), Tareas.vence_en < _ahora(),
                                  Tareas.estado.in_(ABIERTAS))

    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    # Primero lo que ya venció, después por prioridad y por fecha de vencimiento.
    # Las sin fecha van al final: no tienen urgencia declarada.
    filas = list(db.scalars(consulta.order_by(
        Tareas.vence_en.is_(None), Tareas.vence_en, Tareas.id)))
    filas.sort(key=lambda t: (_ORDEN_PRIORIDAD.get(t.prioridad, 9),
                              t.vence_en or dt.datetime.max.replace(tzinfo=dt.timezone.utc)))
    desde = max(0, pagina - 1) * tamano
    return total, filas[desde:desde + tamano]


def resumen(db: Session, actor: Usuarios | None = None) -> dict:
    """Cuántas tiene encima quien pregunta: el número del saludo de la mañana."""
    consulta = select(Tareas).where(Tareas.estado.in_(ABIERTAS))
    limite = _limite_de_alcance(actor)
    if limite is not None:
        consulta = consulta.where(limite)
    sub = consulta.subquery()
    ahora = _ahora()
    total = db.scalar(select(func.count()).select_from(sub)) or 0
    vencidas = db.scalar(select(func.count()).select_from(sub)
                         .where(sub.c.vence_en.is_not(None), sub.c.vence_en < ahora)) or 0
    hoy = db.scalar(select(func.count()).select_from(sub)
                    .where(sub.c.vence_en.is_not(None), sub.c.vence_en >= ahora,
                           sub.c.vence_en < ahora.replace(hour=23, minute=59))) or 0
    altas = db.scalar(select(func.count()).select_from(sub)
                      .where(sub.c.prioridad == 'alta')) or 0
    return {'abiertas': total, 'vencidas': vencidas, 'vencen_hoy': hoy, 'alta_prioridad': altas}
