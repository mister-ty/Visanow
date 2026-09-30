"""Ficha 360° y búsqueda global (RF-005, RF-029, RF-064).

La ficha 360° es la respuesta a lo que hoy obliga a abrir tres archivos: en una
sola pantalla, quién es el cliente, quiénes viajan con él, en qué va cada
trámite, qué citas vienen y qué ha pasado, en orden.

La cronología mezcla dos fuentes: lo que el sistema registró solo (cambios de
estado, citas, documentos) y lo que la gente anota a mano (llamadas, mensajes,
notas). Las dos cuentan la misma historia y se leen juntas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core import seguridad as seg
from app.core.errores import Invalido
from app.models.esquema import (Actividades, Casos, CasosHistorial, Citas, Clientes, Grupos,
                                Solicitantes, Usuarios)
from app.services import historial
from app.services.auditoria import auditar

TIPOS_NOTA = ('nota', 'llamada', 'whatsapp', 'correo', 'reunion')
# Una nota interna no es hablar con el cliente; las demás sí. La diferencia
# importa porque «hace 20 días que nadie lo llama» es una alerta y «hace 20 días
# que nadie escribió una nota» no lo es.
TIPOS_CONTACTO = ('llamada', 'whatsapp', 'correo', 'reunion')


# ------------------------------------------------------------------ ficha 360

def solicitantes_ids(db: Session, cliente_id: int) -> list[int]:
    grupos = select(Grupos.id).where(Grupos.cliente_contacto_id == cliente_id)
    return [i for (i,) in db.execute(
        select(Solicitantes.id).where(or_(Solicitantes.cliente_id == cliente_id,
                                          Solicitantes.grupo_id.in_(grupos))))]


def tramites_de(db: Session, cliente_id: int) -> list[Casos]:
    ids = solicitantes_ids(db, cliente_id)
    if not ids:
        return []
    return list(db.scalars(
        select(Casos).where(Casos.solicitante_id.in_(ids))
        .options(selectinload(Casos.solicitante), selectinload(Casos.estado),
                 selectinload(Casos.responsable), selectinload(Casos.pais))
        .order_by(Casos.ultima_actividad_en.desc())))


def proximas_citas(db: Session, cliente_id: int, limite: int = 5) -> list[Citas]:
    ids = solicitantes_ids(db, cliente_id)
    if not ids:
        return []
    casos = select(Casos.id).where(Casos.solicitante_id.in_(ids))
    return list(db.scalars(
        select(Citas).where(Citas.caso_id.in_(casos),
                            Citas.estado.notin_(('cancelada', 'realizada')),
                            Citas.inicia_en >= datetime.now(timezone.utc))
        .options(selectinload(Citas.caso).selectinload(Casos.solicitante))
        .order_by(Citas.inicia_en).limit(limite)))


@dataclass
class Suceso:
    cuando: datetime
    tipo: str               # 'sistema' o el tipo de la nota
    titulo: str
    detalle: str | None
    usuario: str | None
    caso_id: int | None = None


def cronologia(db: Session, cliente_id: int, limite: int = 60) -> list[Suceso]:
    casos = [c.id for c in tramites_de(db, cliente_id)]
    sucesos: list[Suceso] = []

    if casos:
        filas = list(db.scalars(select(CasosHistorial).where(CasosHistorial.caso_id.in_(casos))
                                .options(selectinload(CasosHistorial.usuario))
                                .order_by(CasosHistorial.ocurrido_en.desc()).limit(limite)))
        for h, titulo in zip(filas, historial.describir(db, filas)):
            sucesos.append(Suceso(cuando=h.ocurrido_en, tipo='sistema', titulo=titulo,
                                  detalle=h.observacion, usuario=h.usuario.nombre if h.usuario else None,
                                  caso_id=h.caso_id))

    condiciones = [(Actividades.entidad == 'cliente') & (Actividades.entidad_id == cliente_id)]
    if casos:
        condiciones.append((Actividades.entidad == 'caso') & (Actividades.entidad_id.in_(casos)))
    for a in db.scalars(select(Actividades).where(or_(*condiciones))
                        .options(selectinload(Actividades.usuario))
                        .order_by(Actividades.ocurrido_en.desc()).limit(limite)):
        sucesos.append(Suceso(cuando=a.ocurrido_en, tipo=a.tipo, titulo=a.asunto or a.tipo.capitalize(),
                              detalle=a.cuerpo, usuario=a.usuario.nombre if a.usuario else None,
                              caso_id=a.entidad_id if a.entidad == 'caso' else None))

    return sorted(sucesos, key=lambda s: s.cuando, reverse=True)[:limite]


def registrar_nota(db: Session, actor: Usuarios, *, entidad: str, entidad_id: int, tipo: str,
                   asunto: str | None, cuerpo: str | None, ip: str | None = None) -> Actividades:
    """Una llamada, un WhatsApp, una nota. Es lo que hoy vive en la columna
    «NOTAS» de los Excel y se pierde (RF-012, RF-064)."""
    if tipo not in TIPOS_NOTA:
        raise Invalido(f'Tipo inválido. Opciones: {", ".join(TIPOS_NOTA)}.')
    if not (asunto or cuerpo):
        raise Invalido('Escriba al menos el asunto o el contenido de la nota.')
    actividad = Actividades(entidad=entidad, entidad_id=entidad_id, tipo=tipo, asunto=asunto,
                            cuerpo=cuerpo, usuario_id=actor.id)
    db.add(actividad)
    if tipo in TIPOS_CONTACTO:
        # Una llamada sobre el trámite también es contacto con el cliente: se
        # sube desde el caso hasta la ficha que lo contrata.
        cliente_id = entidad_id if entidad == 'cliente' else cliente_de_caso(db, entidad_id)
        cliente = db.get(Clientes, cliente_id) if cliente_id else None
        if cliente:
            cliente.ultimo_contacto_en = datetime.now(timezone.utc)
    db.flush()
    auditar(db, operacion='insert', entidad='actividades', usuario_id=actor.id,
            entidad_id=actividad.id, despues={'entidad': entidad, 'entidad_id': entidad_id, 'tipo': tipo},
            ip=ip)
    db.commit()
    return actividad


def cliente_de_caso(db: Session, caso_id: int) -> int | None:
    """El trámite cuelga de la persona que viaja; quien contrata es el cliente
    de contacto, que puede estar en la persona o en su grupo."""
    caso = db.get(Casos, caso_id, options=[selectinload(Casos.solicitante)
                                           .selectinload(Solicitantes.grupo)])
    if caso is None:
        return None
    s = caso.solicitante
    return s.cliente_id or (s.grupo.cliente_contacto_id if s.grupo else None)


# ------------------------------------------------------------ búsqueda global

@dataclass
class Resultado:
    tipo: str               # cliente | solicitante | tramite
    id: int
    titulo: str
    detalle: str
    ruta: str
    coincidio_por: str


def buscar_global(db: Session, texto: str, limite: int = 8) -> list[Resultado]:
    """RF-029: una sola caja para nombre, teléfono, documento, correo, pasaporte,
    DS-160 o número de solicitud del SaaS. El pasaporte y el DS-160 están
    cifrados: se buscan por su índice ciego, sin descifrar la columna."""
    texto = (texto or '').strip()
    if len(texto) < 2:
        return []
    digitos = ''.join(c for c in texto if c.isdigit())
    resultados: list[Resultado] = []

    consulta: Select = (select(Clientes).where(Clientes.fusionado_en_id.is_(None)))
    condiciones = [Clientes.nombre_busqueda.like(_patron(texto)),
                   func.lower(Clientes.email) == texto.lower()]
    if digitos:
        condiciones.append(Clientes.numero_documento == digitos)
        if len(digitos) >= 7:
            condiciones.append(Clientes.telefono_normalizado == digitos[-10:])
    for c in db.scalars(consulta.where(or_(*condiciones)).order_by(Clientes.nombre).limit(limite)):
        resultados.append(Resultado(
            tipo='cliente', id=c.id, titulo=c.nombre,
            detalle=' · '.join(x for x in (c.numero_documento, c.telefono, c.email) if x) or 'sin datos de contacto',
            ruta=f'/clientes/{c.id}', coincidio_por=_por_que(texto, digitos, c)))

    # Personas: por nombre o por pasaporte exacto (columna cifrada)
    indice = seg.indice_ciego(texto)
    # Ojo: `columna == None` en SQLAlchemy se traduce a `IS NULL`, que traería a
    # todo el que no tenga documento. La condición solo se agrega si hay dígitos.
    de_persona = [Solicitantes.nombre_busqueda.like(_patron(texto)),
                  Solicitantes.pasaporte_indice == indice]
    if digitos:
        de_persona.append(Solicitantes.numero_documento == digitos)
    for s in db.scalars(
            select(Solicitantes)
            .where(Solicitantes.fusionado_en_id.is_(None), or_(*de_persona))
            .options(selectinload(Solicitantes.grupo))
            .order_by(Solicitantes.nombre).limit(limite)):
        cliente_id = s.cliente_id or (s.grupo.cliente_contacto_id if s.grupo else None)
        if cliente_id is None:
            continue
        # Quien contrata suele viajar también: sin esto saldría dos veces, como
        # cliente y como viajero, con el mismo nombre y llevando al mismo lado.
        if any(r.tipo == 'cliente' and r.id == cliente_id and r.titulo == s.nombre
               for r in resultados):
            continue
        resultados.append(Resultado(
            tipo='solicitante', id=s.id, titulo=s.nombre,
            detalle='viaja con ' + (s.grupo.nombre if s.grupo else 'ficha propia'),
            ruta=f'/clientes/{cliente_id}',
            coincidio_por='pasaporte' if s.pasaporte_indice == indice else 'nombre'))

    # Trámites: por número de solicitud del SaaS o por número de DS-160 (cifrado)
    for caso in db.scalars(
            select(Casos).where(or_(Casos.id_externo == texto, Casos.ds160_hash == indice))
            .options(selectinload(Casos.solicitante), selectinload(Casos.estado)).limit(limite)):
        resultados.append(Resultado(
            tipo='tramite', id=caso.id, titulo=f'Trámite de {caso.solicitante.nombre}',
            detalle=caso.estado.nombre, ruta=f'/casos/{caso.id}',
            coincidio_por='n.º de solicitud' if caso.id_externo == texto else 'DS-160'))

    return resultados[: limite * 2]


def _patron(texto: str):
    """Las columnas `nombre_busqueda` son `lower(sin_tildes(nombre))`; el patrón
    se normaliza igual para que «Álvarez» encuentre «alvarez» y al revés."""
    return func.lower(func.sin_tildes(f'%{texto}%'))


def _por_que(texto: str, digitos: str, c: Clientes) -> str:
    if digitos and c.numero_documento == digitos:
        return 'documento'
    if digitos and c.telefono_normalizado == digitos[-10:]:
        return 'teléfono'
    if c.email and c.email.lower() == texto.lower():
        return 'correo'
    return 'nombre'
