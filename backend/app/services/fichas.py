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
from urllib.parse import quote

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.core import seguridad as seg
from app.core.errores import Invalido
from app.models.esquema import (
    Actividades,
    Casos,
    CasosHistorial,
    Citas,
    Clientes,
    Documentos,
    Grupos,
    Negocios,
    Pagos,
    Solicitantes,
    Usuarios,
)
from app.services import casos as serv_casos
from app.services import documentos as serv_docs
from app.services import historial
from app.services.auditoria import auditar
from app.services.pagos import referencia_contiene
from app.services.usuarios import permisos_de_rol

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
    #: El documento del que habla el suceso, cuando lo hay (RF-064). Viene
    #: vacío tanto si no se adjuntó nada como si el documento no es para los
    #: ojos de quien está leyendo; la pantalla no tiene por qué distinguirlos,
    #: porque decir «hay un adjunto reservado» ya revela lo que se esconde.
    adjunto: dict | None = None


def cronologia(db: Session, cliente_id: int, *, actor: Usuarios | None = None,
               limite: int = 60) -> list[Suceso]:
    """La historia del cliente: lo que registró el sistema y lo que anotó la
    gente, con su autor y con sus adjuntos (RF-064).

    Recibe quién lee, y no por cortesía: la cronología se le muestra a
    cualquiera que pueda abrir la ficha, y entre los adjuntos puede haber un
    pasaporte escaneado, que no lo ve cualquiera. Sin actor no muestra ningún
    adjunto: de los dos lados, lo seguro es no mostrar.
    """
    casos = [c.id for c in tramites_de(db, cliente_id)]
    sucesos: list[Suceso] = []
    # Una sola vez para toda la lista, no una por adjunto.
    permisos = permisos_de_rol(db, actor.rol_id) if actor is not None else set()

    if casos:
        filas = list(db.scalars(select(CasosHistorial).where(CasosHistorial.caso_id.in_(casos))
                                .options(selectinload(CasosHistorial.usuario))
                                .order_by(CasosHistorial.ocurrido_en.desc()).limit(limite)))
        # strict: un titulo por fila. Sin esto, si describir devolviera
        # menos, la cronologia perderia sucesos sin que nada avisara.
        for h, titulo in zip(filas, historial.describir(db, filas), strict=True):
            sucesos.append(Suceso(cuando=h.ocurrido_en, tipo='sistema', titulo=titulo,
                                  detalle=h.observacion, usuario=h.usuario.nombre if h.usuario else None,
                                  caso_id=h.caso_id))

    condiciones = [(Actividades.entidad == 'cliente') & (Actividades.entidad_id == cliente_id)]
    if casos:
        condiciones.append((Actividades.entidad == 'caso') & (Actividades.entidad_id.in_(casos)))
    for a in db.scalars(select(Actividades).where(or_(*condiciones))
                        .options(selectinload(Actividades.usuario),
                                 selectinload(Actividades.documento))
                        .order_by(Actividades.ocurrido_en.desc()).limit(limite)):
        sucesos.append(Suceso(cuando=a.ocurrido_en, tipo=a.tipo, titulo=a.asunto or a.tipo.capitalize(),
                              detalle=a.cuerpo, usuario=a.usuario.nombre if a.usuario else None,
                              caso_id=a.entidad_id if a.entidad == 'caso' else None,
                              adjunto=_adjunto_visible(actor, a.documento, permisos)))

    return sorted(sucesos, key=lambda s: s.cuando, reverse=True)[:limite]


def _adjunto_visible(actor: Usuarios | None, doc: Documentos | None,
                     permisos: set[str]) -> dict | None:
    """El adjunto del suceso, o nada si no le corresponde a quien lee.

    La regla de quién puede ver un documento la pone el módulo de documentos y
    se consulta allá: si acá se escribiera otra vez, el día que se cambie una
    quedaría abierta la otra. Lo que se abre por la cronología es exactamente lo
    mismo que se abre por la pantalla de documentos, ni más ni menos.
    """
    if doc is None or not serv_docs.visible_para(actor, doc, permisos=permisos):
        return None
    return {'id': doc.id, 'nombre': doc.nombre, 'almacenamiento': doc.almacenamiento,
            'url': doc.url, 'mime': doc.mime, 'restringido': doc.restringido}


def registrar_nota(db: Session, actor: Usuarios, *, entidad: str, entidad_id: int, tipo: str,
                   asunto: str | None, cuerpo: str | None, documento_id: int | None = None,
                   ip: str | None = None) -> Actividades:
    """Una llamada, un WhatsApp, una nota, con el documento del que habla.

    Es lo que hoy vive en la columna «NOTAS» de los Excel y se pierde (RF-012,
    RF-064). El adjunto es un documento que ya está en la ficha: acá no se sube
    nada, se cuelga del suceso lo que el módulo de documentos ya guardó.
    """
    if tipo not in TIPOS_NOTA:
        raise Invalido(f'Tipo inválido. Opciones: {", ".join(TIPOS_NOTA)}.')
    if not (asunto or cuerpo):
        raise Invalido('Escriba al menos el asunto o el contenido de la nota.')
    if documento_id is not None:
        _exigir_adjunto(db, actor, entidad=entidad, entidad_id=entidad_id,
                        documento_id=documento_id)
    actividad = Actividades(entidad=entidad, entidad_id=entidad_id, tipo=tipo, asunto=asunto,
                            cuerpo=cuerpo, usuario_id=actor.id, documento_id=documento_id)
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
            entidad_id=actividad.id, ip=ip,
            despues={'entidad': entidad, 'entidad_id': entidad_id, 'tipo': tipo,
                     'documento_id': documento_id})
    db.commit()
    return actividad


def _exigir_adjunto(db: Session, actor: Usuarios, *, entidad: str, entidad_id: int,
                    documento_id: int) -> None:
    """Que el documento que se va a colgar del suceso se pueda colgar de verdad.

    El id llega en el cuerpo de la petición, así que no se puede dar por bueno.
    Son dos comprobaciones, las dos de control de acceso, y por eso viven acá en
    el servicio y no en la ruta: una comprobación que solo está en la ruta se la
    salta cualquiera que llame la API directo (RNF-03).

    - Que quien anota pueda ver ese documento. Lo decide `documentos.obtener`,
      que es el mismo portero de la pantalla de documentos: el permiso sobre la
      ficha de la que cuelga, el alcance del trámite y el permiso de reservados.
      Si no le corresponde responde «no existe», igual que allá, porque decir
      «existe pero no es para usted» ya cuenta que hay algo reservado.
    - Que el documento sea de ESTE cliente. La cronología se le muestra a
      cualquiera que pueda abrir la ficha, así que colgar ahí el documento de
      otro cliente le pondría el nombre de ese archivo delante de gente que no
      tiene nada que ver con él.
    """
    doc = serv_docs.obtener(db, actor, documento_id)
    cliente_id = entidad_id if entidad == 'cliente' else cliente_de_caso(db, entidad_id)
    if cliente_id is None or _cliente_del_documento(db, doc) != cliente_id:
        raise Invalido('Ese documento no es de este cliente: adjunte uno de los que están '
                       'en su ficha.', codigo='adjunto_ajeno')


def _cliente_del_documento(db: Session, doc: Documentos) -> int | None:
    """De qué cliente es un documento, cuelgue de donde cuelgue.

    Un documento va pegado a una ficha, a una persona, a un trámite o a una
    venta, y todas esas cosas terminan en un cliente. Los de un pago o un gasto
    no: esos son de la contabilidad, no son de nadie en particular, y por eso no
    tienen cronología de cliente donde colgarse.
    """
    if doc.entidad == 'cliente':
        return doc.entidad_id
    if doc.entidad == 'solicitante':
        s = db.get(Solicitantes, doc.entidad_id,
                   options=[selectinload(Solicitantes.grupo)])
        if s is None:
            return None
        return s.cliente_id or (s.grupo.cliente_contacto_id if s.grupo else None)
    if doc.entidad == 'caso':
        return cliente_de_caso(db, doc.entidad_id)
    if doc.entidad == 'negocio':
        negocio = db.get(Negocios, doc.entidad_id)
        return negocio.cliente_id if negocio else None
    return None


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
    tipo: str               # cliente | solicitante | tramite | pago
    id: int
    titulo: str
    detalle: str
    ruta: str
    coincidio_por: str


def buscar_global(db: Session, texto: str, *, actor: Usuarios | None = None,
                  limite: int = 8) -> list[Resultado]:
    """RF-029: una sola caja para nombre, teléfono, documento, correo, pasaporte,
    DS-160, número de solicitud del SaaS o referencia de pago. El pasaporte y el
    DS-160 están cifrados: se buscan por su índice ciego, sin descifrar la
    columna.

    El teléfono se mira en los dos lados —el del cliente de contacto y el de
    quien viaja—, porque son columnas distintas y la persona que contesta no
    siempre es la que contrata.

    Recibe quién está buscando, y no por cortesía: el buscador devuelve trámites
    y pagos, que son cosas que no todo el mundo puede ver. Un buscador que
    responde lo mismo para todos es una puerta de atrás a lo que la pantalla
    sí protege. Sin actor no devuelve ni trámites ni pagos: de los dos lados, lo
    seguro es no mostrar.
    """
    texto = (texto or '').strip()
    if len(texto) < 2:
        return []
    digitos = ''.join(c for c in texto if c.isdigit())
    resultados: list[Resultado] = []
    # Qué tiene permitido ver quien busca. Se pregunta una sola vez: el buscador
    # responde a cada letra que alguien escribe, así que no es el lugar para
    # repetir consultas de permisos.
    permisos = permisos_de_rol(db, actor.rol_id) if actor is not None else set()

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
        # El teléfono de quien viaja, que es columna propia de la persona y no
        # la del cliente de contacto. Faltaba, y es el caso de todos los días:
        # la mamá contrata y deja su número en la ficha, pero el celular que
        # contesta cuando se llama por la cita es el del muchacho. Escribirlo no
        # encontraba absolutamente nada (RF-029).
        if len(digitos) >= 7:
            de_persona.append(Solicitantes.telefono_normalizado == digitos[-10:])
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
            coincidio_por=_por_que_persona(indice, digitos, s)))

    # Trámites: por número de solicitud del SaaS o por número de DS-160 (cifrado).
    # Ver trámites es un permiso, y a un rol se le puede quitar desde la
    # administración: la ficha del cliente ya lo respeta —responde sin la parte
    # operativa y lo dice en `ve_tramites`—, y el buscador tenía que respetarlo
    # igual, o sería la rendija que deja sin efecto a lo otro.
    if 'casos.ver' in permisos:
        de_tramite = (select(Casos)
                      .where(or_(Casos.id_externo == texto, Casos.ds160_hash == indice))
                      .options(selectinload(Casos.solicitante), selectinload(Casos.estado)))
        # Y el alcance es control de acceso (RNF-03), no un filtro de pantalla,
        # así que vale aquí también. Faltaba: quien solo ve los trámites que le
        # asignaron encontraba por este buscador —escribiendo el n.º de
        # solicitud o el DS-160— trámites que no son suyos, y desde el resultado
        # los abría. Era el mismo hueco que ya se cerró en el tablero, pero por
        # la puerta del buscador.
        limite_alcance = serv_casos.alcance_de(actor)
        if limite_alcance is not None:
            de_tramite = de_tramite.where(limite_alcance)
        for caso in db.scalars(de_tramite.limit(limite)):
            resultados.append(Resultado(
                tipo='tramite', id=caso.id, titulo=f'Trámite de {caso.solicitante.nombre}',
                detalle=caso.estado.nombre, ruta=f'/casos/{caso.id}',
                coincidio_por='n.º de solicitud' if caso.id_externo == texto else 'DS-160'))

    resultados.extend(_pagos_por_referencia(db, texto, permisos=permisos, limite=limite))
    return resultados[: limite * 2]


def _pagos_por_referencia(db: Session, texto: str, *, permisos: set[str],
                          limite: int) -> list[Resultado]:
    """El pago, por la referencia del comprobante (RF-029).

    Es la pregunta que llega por WhatsApp: «ya pagué, el comprobante dice
    00123456789». Hasta ahora había que abrir la pantalla de pagos y recorrer
    la lista con los ojos, o adivinar la fecha para filtrar por rango.

    Vale la pena incluso para el pago que todavía no tiene dueño: si está en la
    bandeja de no identificados, encontrarlo por su referencia es justamente lo
    que permite asignarlo al cliente que está llamando.

    Ver plata es un permiso, no un alcance (los pagos no cuelgan de un
    responsable): quien no puede entrar a la pantalla de pagos tampoco puede
    sacarlos por el buscador. Sin esto, operaciones —que a propósito no ve la
    contabilidad— habría empezado a ver montos de clientes aquí.
    """
    if 'pagos.ver' not in permisos:
        return []

    salida: list[Resultado] = []
    for p in db.scalars(
            select(Pagos).where(referencia_contiene(Pagos.referencia, texto))
            .options(selectinload(Pagos.negocio).selectinload(Negocios.cliente))
            .order_by(Pagos.fecha.desc(), Pagos.id.desc()).limit(limite)):
        de_quien = (p.negocio.cliente.nombre if p.negocio and p.negocio.cliente
                    else 'sin identificar')
        salida.append(Resultado(
            tipo='pago', id=p.id, titulo=f'Pago de {de_quien}',
            detalle=f'{p.fecha:%d/%m/%Y} · ref. {p.referencia}',
            # Lleva a la pantalla de pagos ya filtrada por esa referencia: desde
            # ahí se ve la venta, o se le asigna dueño si llegó suelto.
            ruta=f'/pagos?referencia={quote(p.referencia or "")}',
            coincidio_por='referencia de pago'))
    return salida


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


def _por_que_persona(indice: str, digitos: str, s: Solicitantes) -> str:
    """Por qué salió esta persona. Se le muestra al que busca, y le sirve: ver
    «teléfono» al lado de un nombre que no se parece a lo que escribió es lo que
    le explica por qué está ahí."""
    if s.pasaporte_indice == indice:
        return 'pasaporte'
    if digitos and s.numero_documento == digitos:
        return 'documento'
    if digitos and s.telefono_normalizado == digitos[-10:]:
        return 'teléfono'
    return 'nombre'


# ------------------------------------------------- los bloques de la vista 360
#
# RF-005 pide nueve cosas en una sola ficha y habia dos. Lo que sigue arma las
# otras siete. Cada una se pregunta aparte y con SU permiso, porque la ficha
# responde todo junto y mezclarlos seria entregarle a operaciones los montos que
# la administradora dijo el 29/09 que no debe ver.


def oportunidades_de(db: Session, cliente_id: int) -> list[dict]:
    """Los leads del cliente, abiertos y cerrados."""
    filas = db.execute(text("""
        select o.id, ec.nombre as estado, s.nombre as servicio, p.nombre as pais,
               o.valor_estimado, o.proxima_accion, o.proxima_accion_fecha, o.creado_en
          from oportunidades o
          left join estados_comerciales ec on ec.id = o.estado_id
          left join servicios s on s.id = o.servicio_id
          left join paises p on p.id = o.pais_id
         where o.cliente_id = :c
         order by o.creado_en desc""" ), {'c': cliente_id}).mappings().all()
    return [{'id': f['id'], 'estado': f['estado'] or 'sin estado', 'servicio': f['servicio'],
             'pais': f['pais'], 'valor_estimado': float(f['valor_estimado'] or 0) or None,
             'proxima_accion': f['proxima_accion'],
             'proxima_accion_fecha': f['proxima_accion_fecha'],
             'creada_en': f['creado_en']} for f in filas]


def ventas_de(db: Session, cliente_id: int) -> list[dict]:
    """Las ventas con su saldo, que sale de la vista y nunca de una columna (RN-01)."""
    filas = db.execute(text("""
        select n.id, s.nombre as servicio, n.fecha_venta, n.cantidad_solicitantes,
               n.valor_pactado, ef.total_pagado, ef.saldo, ef.estado_financiero
          from negocios n
          left join servicios s on s.id = n.servicio_id
          left join v_estado_financiero ef on ef.negocio_id = n.id
         where n.cliente_id = :c
         order by n.fecha_venta desc, n.id desc"""), {'c': cliente_id}).mappings().all()
    return [{'id': f['id'], 'servicio': f['servicio'], 'fecha_venta': f['fecha_venta'],
             'personas': f['cantidad_solicitantes'] or 1,
             'valor_pactado': float(f['valor_pactado'] or 0),
             'pagado': float(f['total_pagado'] or 0), 'saldo': float(f['saldo'] or 0),
             'estado_financiero': f['estado_financiero'] or 'sin pagos'} for f in filas]


def pagos_de(db: Session, cliente_id: int, limite: int = 50) -> list[dict]:
    filas = db.execute(text("""
        select p.id, p.negocio_id, p.fecha, p.monto_bruto, mp.nombre as medio, p.referencia
          from pagos p
          join negocios n on n.id = p.negocio_id
          left join medios_pago mp on mp.id = p.medio_pago_id
         where n.cliente_id = :c
         order by p.fecha desc, p.id desc
         limit :l"""), {'c': cliente_id, 'l': limite}).mappings().all()
    return [{'id': f['id'], 'negocio_id': f['negocio_id'], 'fecha': f['fecha'],
             'monto': float(f['monto_bruto'] or 0), 'medio': f['medio'],
             'referencia': f['referencia']} for f in filas]


def esta_al_dia(db: Session, cliente_id: int) -> bool:
    """Si no debe nada VENCIDO. Es lo que se le responde a quien no ve montos.

    No es «no debe nada»: un cliente con cuotas al futuro esta al dia aunque
    tenga saldo, y es con quien si se puede arrancar el tramite.
    """
    vencido = db.execute(text("""
        select coalesce(sum(c.vencido), 0)
          from v_cartera c join negocios n on n.id = c.negocio_id
         where n.cliente_id = :c"""), {'c': cliente_id}).scalar()
    return float(vencido or 0) <= 0


def tareas_de(db: Session, cliente_id: int, limite: int = 20) -> list[dict]:
    """Las tareas del cliente y las de sus tramites: para quien atiende es lo mismo."""
    filas = db.execute(text("""
        select t.id, t.titulo, t.estado, t.prioridad, t.vence_en, u.nombre as responsable
          from tareas t
          left join usuarios u on u.id = t.responsable_id
         where t.cliente_id = :c
            or t.caso_id in (select ca.id from casos ca
                               join solicitantes so on so.id = ca.solicitante_id
                              where so.cliente_id = :c)
            or t.negocio_id in (select id from negocios where cliente_id = :c)
         order by (t.estado in ('hecha', 'cancelada')), t.vence_en nulls last, t.id desc
         limit :l"""), {'c': cliente_id, 'l': limite}).mappings().all()
    return [dict(f) for f in filas]


def alertas_de(db: Session, cliente_id: int, limite: int = 20) -> list[dict]:
    filas = db.execute(text("""
        select a.id, at.nombre as tipo, a.mensaje, at.severidad, a.estado, a.generada_en
          from alertas a
          join alertas_tipos at on at.id = a.tipo_id
         where a.caso_id in (select ca.id from casos ca
                               join solicitantes so on so.id = ca.solicitante_id
                              where so.cliente_id = :c)
            or a.negocio_id in (select id from negocios where cliente_id = :c)
            or a.oportunidad_id in (select id from oportunidades where cliente_id = :c)
         order by (a.estado = 'resuelta'), a.generada_en desc
         limit :l"""), {'c': cliente_id, 'l': limite}).mappings().all()
    return [{'id': f['id'], 'tipo': f['tipo'], 'mensaje': f['mensaje'],
             'severidad': f['severidad'], 'estado': f['estado'],
             'creada_en': f['generada_en']} for f in filas]


def documentos_de(db: Session, cliente_id: int, *, ve_reservados: bool) -> list[dict]:
    """Los adjuntos del cliente, de sus personas y de sus tramites, juntos.

    Para quien atiende, «los documentos de Ana» son todos, no los de la ficha
    del cliente por un lado y los del tramite por otro.

    «Sus personas» son las mismas que cuenta el resumen de la ficha: las que
    cuelgan del cliente y las que cuelgan de su grupo. Faltaban las del grupo,
    que en VisaNow son casi todas —quien contrata rara vez viaja solo—, asi que
    la ficha de una familia mostraba solo los documentos del contacto y ni los
    de los hijos ni los de sus tramites.
    """
    filas = db.execute(text("""
        with personas as (
            select id from solicitantes
             where cliente_id = :c
                or grupo_id in (select id from grupos where cliente_contacto_id = :c)
        )
        select d.id, d.nombre, d.almacenamiento, d.url, d.mime, d.restringido,
               d.entidad, d.creado_en
          from documentos d
         where (d.entidad = 'cliente' and d.entidad_id = :c)
            or (d.entidad = 'solicitante' and d.entidad_id in (select id from personas))
            or (d.entidad = 'caso' and d.entidad_id in
                  (select id from casos where solicitante_id in (select id from personas)))
            or (d.entidad = 'negocio' and d.entidad_id in
                  (select id from negocios where cliente_id = :c))
         order by d.creado_en desc"""), {'c': cliente_id}).mappings().all()
    COMO = {'cliente': 'el cliente', 'solicitante': 'una persona', 'caso': 'un trámite',
            'negocio': 'una venta'}
    return [{'id': f['id'], 'nombre': f['nombre'], 'almacenamiento': f['almacenamiento'],
             'url': f['url'], 'mime': f['mime'], 'restringido': f['restringido'],
             'sobre': COMO.get(f['entidad'], f['entidad']), 'creado_en': f['creado_en']}
            for f in filas if ve_reservados or not f['restringido']]
