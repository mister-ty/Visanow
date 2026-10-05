"""El embudo comercial: del lead a la venta (RF-010 a RF-015).

Hoy esto no existe en ninguna parte. La hoja `pauta` del libro de clientes tiene
145 leads de publicidad con nombre, teléfono, ciudad, interés y «calidad del
lead», pero no hay forma de saber cuáles se convirtieron: la venta aparece en
otro libro, sin decir de dónde salió el cliente. Por eso nadie puede responder
qué campaña trae clientes que compran, que es justo lo que decide dónde se pone
la plata de publicidad.

Dos reglas que vienen de cómo se trabaja de verdad:

- **Una oportunidad abierta siempre tiene próxima acción.** Es la misma regla
  que RN-04 pide para los trámites. Un lead sin próximo paso no está en el
  embudo: está olvidado, y la diferencia entre las dos cosas es la que hace que
  un negocio se caiga sin que nadie se entere.
- **Perder se explica.** Cerrar como perdido exige un motivo del catálogo
  (RF-015). «No respondió» y «precio» llevan a decisiones distintas; «se perdió»
  no lleva a ninguna.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import Invalido, NoEncontrado
from app.models.esquema import (Clientes, EstadosComerciales, MotivosPerdida, Oportunidades,
                                Usuarios)
from app.services.auditoria import auditar, instantanea

BOGOTA = ZoneInfo('America/Bogota')
ESTADO_INICIAL = 'nuevo_lead'

CAMPOS = ('servicio_id', 'pais_id', 'canal_id', 'campania_id', 'campania', 'asesor_id',
          'valor_estimado', 'proxima_accion', 'proxima_accion_fecha', 'referido_por_cliente_id')


def _ahora() -> dt.datetime:
    return dt.datetime.now(BOGOTA)


def estado(db: Session, codigo: str) -> EstadosComerciales:
    e = db.scalar(select(EstadosComerciales).where(EstadosComerciales.codigo == codigo))
    if e is None:
        raise NoEncontrado(f'El estado comercial «{codigo}» no existe.')
    return e


def obtener(db: Session, oportunidad_id: int, *, actor: Usuarios | None = None) -> Oportunidades:
    o = db.get(Oportunidades, oportunidad_id,
               options=[selectinload(Oportunidades.cliente), selectinload(Oportunidades.estado),
                        selectinload(Oportunidades.asesor)])
    if o is None:
        raise NoEncontrado('La oportunidad no existe.')
    if actor is not None and not _alcanza(actor, o):
        # Igual que en los trámites: se responde como si no existiera, porque
        # decir «existe pero no es suya» ya revela que es cliente de VisaNow.
        raise NoEncontrado('La oportunidad no existe.')
    return o


def _alcanza(actor: Usuarios, o: Oportunidades) -> bool:
    return actor.alcance == 'todos' or o.asesor_id == actor.id


def crear(db: Session, actor: Usuarios, datos: dict, ip: str | None = None) -> Oportunidades:
    """Un lead nuevo. Nace en «nuevo lead» y con asesor: sin dueño no lo
    trabaja nadie, y es el error que más se repite en los archivos actuales."""
    cliente_id = datos.get('cliente_id')
    if not cliente_id or db.get(Clientes, cliente_id) is None:
        raise NoEncontrado('El cliente no existe.')
    if not datos.get('proxima_accion'):
        raise Invalido('Escriba cuál es la próxima acción. Un lead sin próximo paso se pierde.')

    o = Oportunidades(cliente_id=cliente_id, estado_id=estado(db, ESTADO_INICIAL).id,
                      asesor_id=datos.get('asesor_id') or actor.id,
                      **{k: v for k, v in datos.items() if k in CAMPOS and k != 'asesor_id'})
    db.add(o)
    db.flush()
    auditar(db, operacion='insert', entidad='oportunidades', usuario_id=actor.id,
            entidad_id=o.id, despues=instantanea(o), ip=ip)
    db.commit()
    return o


def editar(db: Session, actor: Usuarios, oportunidad_id: int, cambios: dict,
           ip: str | None = None) -> Oportunidades:
    o = obtener(db, oportunidad_id, actor=actor)
    antes = instantanea(o)
    for campo, valor in cambios.items():
        if campo in CAMPOS:
            setattr(o, campo, valor)
    db.flush()
    auditar(db, operacion='update', entidad='oportunidades', usuario_id=actor.id,
            entidad_id=o.id, antes=antes, despues=instantanea(o), ip=ip)
    db.commit()
    return o


def mover(db: Session, actor: Usuarios, oportunidad_id: int, *, codigo_destino: str,
          motivo_perdida: str | None = None, nota: str | None = None,
          proxima_accion: str | None = None, ip: str | None = None) -> Oportunidades:
    """Mueve la oportunidad por el embudo.

    A diferencia de los trámites, aquí el orden no se controla: un lead puede
    saltar de «contactado» a «ganado» si el cliente dijo que sí de una. Lo que
    sí se exige es lo que no se puede reconstruir después: el motivo cuando se
    pierde, y la próxima acción mientras siga abierta.
    """
    o = obtener(db, oportunidad_id, actor=actor)
    destino = estado(db, codigo_destino)
    antes = instantanea(o)
    anterior = o.estado.codigo if o.estado else None

    if destino.requiere_motivo:
        if not motivo_perdida:
            raise Invalido('Diga por qué se perdió. «No respondió» y «precio» llevan a '
                           'decisiones distintas; «se perdió» no lleva a ninguna.',
                           codigo='falta_motivo')
        m = db.scalar(select(MotivosPerdida).where(MotivosPerdida.codigo == motivo_perdida))
        if m is None:
            raise Invalido(f'El motivo «{motivo_perdida}» no está en el catálogo.')
        o.motivo_perdida_id = m.id
        o.motivo_perdida_nota = nota

    if not destino.es_cierre:
        siguiente = proxima_accion or o.proxima_accion
        if not siguiente:
            raise Invalido('Escriba cuál es la próxima acción antes de mover la oportunidad.',
                           codigo='falta_proxima_accion')
        o.proxima_accion = siguiente
        o.cerrado_en = None
    else:
        o.cerrado_en = _ahora()

    o.estado_id = destino.id
    o.estado = destino
    db.flush()
    auditar(db, operacion='update', entidad='oportunidades', usuario_id=actor.id, entidad_id=o.id,
            antes=antes, despues=instantanea(o) | {'estado_anterior': anterior}, ip=ip)
    db.commit()
    return o


def registrar_contacto(db: Session, actor: Usuarios, oportunidad_id: int, *,
                       proxima_accion: str | None = None,
                       proxima_accion_fecha: dt.date | None = None,
                       ip: str | None = None) -> Oportunidades:
    """RF-012 del lado comercial: queda cuándo fue la última vez que se le habló
    y qué sigue. Es lo que alimenta la lista de «leads fríos»."""
    o = obtener(db, oportunidad_id, actor=actor)
    o.ultimo_contacto_en = _ahora()
    if proxima_accion:
        o.proxima_accion = proxima_accion
    if proxima_accion_fecha is not None:
        o.proxima_accion_fecha = proxima_accion_fecha
    db.flush()
    auditar(db, operacion='contacto', entidad='oportunidades', usuario_id=actor.id,
            entidad_id=o.id, despues={'ultimo_contacto_en': o.ultimo_contacto_en}, ip=ip)
    db.commit()
    return o


# ----------------------------------------------------------------------- listas

def listar(db: Session, *, actor: Usuarios | None = None, estado_codigo: str | None = None,
           asesor_id: int | None = None, canal_id: int | None = None,
           servicio_id: int | None = None, campania_id: int | None = None,
           incluir_cerradas: bool = False, frias_desde: int | None = None,
           texto: str | None = None, pagina: int = 1,
           tamano: int = 50) -> tuple[int, list[Oportunidades]]:
    consulta: Select = (select(Oportunidades)
                        .join(EstadosComerciales, EstadosComerciales.id == Oportunidades.estado_id)
                        .join(Clientes, Clientes.id == Oportunidades.cliente_id)
                        .options(selectinload(Oportunidades.cliente),
                                 selectinload(Oportunidades.estado),
                                 selectinload(Oportunidades.asesor)))
    if actor is not None and actor.alcance != 'todos':
        consulta = consulta.where(Oportunidades.asesor_id == actor.id)
    if not incluir_cerradas:
        consulta = consulta.where(EstadosComerciales.es_cierre.is_(False))
    if estado_codigo:
        consulta = consulta.where(EstadosComerciales.codigo == estado_codigo)
    for columna, valor in ((Oportunidades.asesor_id, asesor_id),
                           (Oportunidades.canal_id, canal_id),
                           (Oportunidades.servicio_id, servicio_id),
                           (Oportunidades.campania_id, campania_id)):
        if valor:
            consulta = consulta.where(columna == valor)
    if frias_desde:
        # Sin contacto hace más de N días, contando desde que se creó si nunca
        # se le ha hablado: un lead que nadie tocó es el más frío de todos.
        limite = _ahora() - dt.timedelta(days=frias_desde)
        consulta = consulta.where(
            func.coalesce(Oportunidades.ultimo_contacto_en, Oportunidades.creado_en) < limite)
    if texto:
        patron = func.lower(func.sin_tildes(f'%{texto}%'))
        consulta = consulta.where(or_(Clientes.nombre_busqueda.like(patron),
                                      Oportunidades.proxima_accion.ilike(f'%{texto}%')))

    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = list(db.scalars(
        consulta.order_by(EstadosComerciales.orden, Oportunidades.creado_en.desc())
        .offset((pagina - 1) * tamano).limit(tamano)))
    return total, filas


def embudo(db: Session, *, actor: Usuarios | None = None) -> list[tuple[EstadosComerciales, int, float]]:
    """Cuántas oportunidades y cuánto dinero hay en cada paso del embudo.

    Es el tablero Kanban en números: dónde se están quedando los clientes.
    """
    consulta = (select(EstadosComerciales,
                       func.count(Oportunidades.id),
                       func.coalesce(func.sum(Oportunidades.valor_estimado), 0))
                .outerjoin(Oportunidades, Oportunidades.estado_id == EstadosComerciales.id)
                .where(EstadosComerciales.activo.is_(True))
                .group_by(EstadosComerciales.id)
                .order_by(EstadosComerciales.orden))
    if actor is not None and actor.alcance != 'todos':
        consulta = consulta.where(or_(Oportunidades.asesor_id == actor.id,
                                      Oportunidades.id.is_(None)))
    return [(e, n, float(v)) for e, n, v in db.execute(consulta)]


def dias_sin_contacto(o: Oportunidades) -> int:
    referencia = o.ultimo_contacto_en or o.creado_en
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=BOGOTA)
    return (_ahora() - referencia).days
