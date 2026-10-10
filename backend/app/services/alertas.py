"""Centro de alertas: lo que está por vencerse o ya se venció (RF-061, RF-062).

Una alerta no es una notificación más. Es la respuesta a «¿qué se me está
pasando?», que hoy nadie puede contestar sin abrir trámite por trámite. Por eso
viven en una bandeja con estado, y no en un correo que se lee una vez.

**La matriz es configurable y vive en la base** (`alertas_tipos`, RF-062). Cada
tipo dice con cuánta anticipación avisar, en qué unidad, con qué severidad y
cada cuántos días insistir. Cambiar «avisar de la cita del CAS con 7 días» a 10
es editar una fila, no tocar el código ni desplegar.

Un valor de anticipación **positivo avisa antes** del hecho (la cita es en 7
días) y uno **negativo avisa después** (el saldo venció hace 1 día). Esa es toda
la gramática, y con ella los trece tipos sembrados se expresan sin casos
especiales.

**`clave_dedupe` es lo que impide la avalancha.** Generar se puede correr cada
hora sin que la misma alerta aparezca sesenta veces: la clave lleva el tipo, la
entidad y qué repetición es. Y si alguien ya la resolvió, no vuelve a nacer.

**Resolver no la borra.** Queda con quién la resolvió y cuándo. Una bandeja que
se vacía sin dejar rastro no sirve para saber si el equipo está respondiendo o
solo cerrando.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.core.errores import Invalido, NoEncontrado
from app.models.esquema import Alertas, AlertasTipos, Casos, Usuarios
from app.services.auditoria import auditar, instantanea

BOGOTA = ZoneInfo('America/Bogota')

ESTADOS = ('nueva', 'vista', 'resuelta', 'pospuesta')
ABIERTAS = ('nueva', 'vista', 'pospuesta')


def _ahora() -> dt.datetime:
    return dt.datetime.now(BOGOTA)


# --------------------------------------------------------------- las reglas
#
# Cada regla devuelve filas con: entidad_id, los vínculos que apliquen, el
# destinatario y el texto. El umbral lo pone el tipo configurado, no la regla,
# que es lo que hace que la matriz sirva de algo.

@dataclass
class Regla:
    """Una consulta que encuentra a quién hay que avisarle, y de qué."""
    sql: str
    mensaje: str          # plantilla con los campos que devuelve la consulta
    # La columna de `alertas` donde va la entidad. Puede no haber: que la fuente
    # del SaaS lleve una semana sin sincronizar no cuelga de ningún trámite.
    vinculo: str | None = None


# El intervalo se arma en SQL desde el tipo: valor positivo mira hacia adelante,
# negativo hacia atrás. `:corte` es «ahora más la anticipación».
REGLAS: dict[str, Regla] = {
    'lead_sin_contacto': Regla(
        sql="""select o.id as entidad_id, o.asesor_id as destinatario, c.nombre as quien,
                      o.creado_en as cuando
                 from oportunidades o
                 join clientes c on c.id = o.cliente_id
                 join estados_comerciales e on e.id = o.estado_id
                where e.es_cierre = false and o.ultimo_contacto_en is null
                  and o.creado_en <= :corte""",
        vinculo='oportunidad_id',
        mensaje='{quien}: lead sin contactar desde que entró.'),

    'oport_sin_accion': Regla(
        sql="""select o.id as entidad_id, o.asesor_id as destinatario, c.nombre as quien,
                      o.proxima_accion_fecha as cuando, o.proxima_accion as accion
                 from oportunidades o
                 join clientes c on c.id = o.cliente_id
                 join estados_comerciales e on e.id = o.estado_id
                where e.es_cierre = false and o.proxima_accion_fecha is not null
                  and o.proxima_accion_fecha <= :corte""",
        vinculo='oportunidad_id',
        mensaje='{quien}: vencida la próxima acción «{accion}».'),

    'cliente_sin_info': Regla(
        sql="""select ca.id as entidad_id, ca.responsable_id as destinatario,
                      so.nombre as quien, ca.ultima_actividad_en as cuando
                 from casos ca
                 join solicitantes so on so.id = ca.solicitante_id
                 join estados_operativos eo on eo.id = ca.estado_id
                where eo.es_final = false and eo.codigo in ('registrado', 'documentos')
                  and ca.ultima_actividad_en <= :corte""",
        vinculo='caso_id',
        mensaje='{quien}: esperando documentos del cliente.'),

    'caso_sin_movimiento': Regla(
        sql="""select ca.id as entidad_id, ca.responsable_id as destinatario,
                      so.nombre as quien, ca.ultima_actividad_en as cuando
                 from casos ca
                 join solicitantes so on so.id = ca.solicitante_id
                 join estados_operativos eo on eo.id = ca.estado_id
                where eo.es_final = false and ca.ultima_actividad_en <= :corte""",
        vinculo='caso_id',
        mensaje='{quien}: el trámite no se mueve.'),

    'pago_inicial_pendiente': Regla(
        sql="""select n.id as entidad_id, n.vendedor_id as destinatario, c.nombre as quien,
                      n.fecha_venta as cuando
                 from negocios n
                 join clientes c on c.id = n.cliente_id
                 join v_estado_financiero f on f.negocio_id = n.id
                where f.total_pagado = 0 and f.saldo > 0 and n.fecha_venta <= :corte""",
        vinculo='negocio_id',
        mensaje='{quien}: la venta no tiene ni un abono.'),

    'saldo_por_vencer': Regla(
        sql="""select n.id as entidad_id, n.vendedor_id as destinatario, c.nombre as quien,
                      min(q.fecha_pactada) as cuando
                 from negocios n
                 join clientes c on c.id = n.cliente_id
                 join v_estado_financiero f on f.negocio_id = n.id
                 join cuotas_negocio q on q.negocio_id = n.id
                where f.saldo > 0 and q.fecha_pactada between current_date and :corte
                group by n.id, n.vendedor_id, c.nombre""",
        vinculo='negocio_id',
        mensaje='{quien}: se le vence una cuota.'),

    'saldo_vencido': Regla(
        # La vista da los dias de mora, no la fecha en que se vencio: se
        # reconstruye restandolos de hoy, que es lo mismo y no inventa columnas.
        sql="""select n.id as entidad_id, n.vendedor_id as destinatario, c.nombre as quien,
                      (current_date - v.dias_mora) as cuando, v.dias_mora as dias
                 from v_cartera v
                 join negocios n on n.id = v.negocio_id
                 join clientes c on c.id = n.cliente_id
                where v.dias_mora > 0
                  and (current_date - v.dias_mora) <= cast(:corte as date)""",
        vinculo='negocio_id',
        mensaje='{quien}: saldo vencido hace {dias} días.'),

    'cita_cas': Regla(
        sql="""select ci.id as entidad_id, ca.responsable_id as destinatario,
                      so.nombre as quien, ci.inicia_en as cuando
                 from citas ci
                 join casos ca on ca.id = ci.caso_id
                 join solicitantes so on so.id = ca.solicitante_id
                where ci.tipo in ('cas', 'biometria')
                  and ci.estado in ('pendiente','programada','confirmada','reprogramada')
                  and ci.inicia_en between now() and :corte""",
        vinculo='cita_id',
        mensaje='{quien}: cita del CAS.'),

    'preparacion_pendiente': Regla(
        sql="""select ci.id as entidad_id, ca.responsable_id as destinatario,
                      so.nombre as quien, ci.inicia_en as cuando
                 from citas ci
                 join casos ca on ca.id = ci.caso_id
                 join solicitantes so on so.id = ca.solicitante_id
                where ci.tipo = 'entrevista'
                  and ci.estado in ('pendiente','programada','confirmada','reprogramada')
                  and ci.inicia_en between now() and :corte
                  and not exists (select 1 from citas p where p.caso_id = ca.id
                                   and p.tipo = 'preparacion' and p.estado <> 'cancelada')""",
        vinculo='cita_id',
        mensaje='{quien}: entrevista cerca y sin preparación agendada.'),

    'entrevista_proxima': Regla(
        sql="""select ci.id as entidad_id, ca.responsable_id as destinatario,
                      so.nombre as quien, ci.inicia_en as cuando
                 from citas ci
                 join casos ca on ca.id = ci.caso_id
                 join solicitantes so on so.id = ca.solicitante_id
                where ci.tipo = 'entrevista'
                  and ci.estado in ('pendiente','programada','confirmada','reprogramada')
                  and ci.inicia_en between now() and :corte""",
        vinculo='cita_id',
        mensaje='{quien}: entrevista.'),

    'resultado_no_registrado': Regla(
        sql="""select ci.id as entidad_id, ca.responsable_id as destinatario,
                      so.nombre as quien, ci.inicia_en as cuando
                 from citas ci
                 join casos ca on ca.id = ci.caso_id
                 join solicitantes so on so.id = ca.solicitante_id
                where ci.tipo = 'entrevista' and ci.inicia_en <= :corte
                  and ci.estado <> 'cancelada' and ca.resultado is null""",
        vinculo='cita_id',
        mensaje='{quien}: la entrevista ya pasó y no se registró el resultado.'),

    'pasaporte_por_entregar': Regla(
        sql="""select ca.id as entidad_id, ca.responsable_id as destinatario,
                      so.nombre as quien, ca.resultado_fecha as cuando
                 from casos ca
                 join solicitantes so on so.id = ca.solicitante_id
                 join estados_operativos eo on eo.id = ca.estado_id
                where ca.resultado = 'aprobada' and eo.es_final = false
                  and ca.resultado_fecha is not null and ca.resultado_fecha <= :corte""",
        vinculo='caso_id',
        mensaje='{quien}: visa aprobada, falta entregar el pasaporte.'),

    # Sin vinculo: es la fuente entera, no un tramite. `entidad_id` es la ultima
    # sincronizacion, que es lo que hace que la clave de deduplicacion cambie
    # cuando vuelve a fallar y no cuando sigue fallando lo mismo.
    'sync_saas_fallida': Regla(
        # Dispara por dos motivos que no son el mismo: la ultima importacion
        # fallo, o funciono pero lleva mucho sin correr. Anunciarlos con el
        # mismo texto hace que quien lea «fallida» de una importacion que si
        # funciono salga a buscar un problema que no existe, y que el dia que
        # una de verdad falle no se distinga de la otra. `que_paso` las separa.
        sql="""select s.id as entidad_id, null::bigint as destinatario,
                      s.ocurrido_en as cuando, s.intentos as intentos,
                      coalesce(s.detalle, 'sin detalle') as detalle,
                      case when s.resultado = 'error'
                           then 'La importación del SaaS falló tras ' ||
                                s.intentos || ' intento(s)'
                           else 'El SaaS lleva ' ||
                                round(extract(epoch from (now() - s.ocurrido_en)) / 3600)::int ||
                                ' horas sin importarse; la última sí funcionó'
                      end as que_paso
                 from sincronizaciones s
                where s.origen = 'saas'
                  and s.id = (select max(id) from sincronizaciones where origen = 'saas')
                  and (s.resultado = 'error' or s.ocurrido_en <= :corte)""",
        mensaje='{que_paso}: {detalle}.'),
}


def _corte(tipo: AlertasTipos, ahora: dt.datetime):
    """Hasta qué fecha mira la regla, según lo configurado en la matriz.

    Positivo mira hacia adelante —la cita es dentro de 7 días—; negativo hacia
    atrás —el trámite lleva 5 días hábiles quieto—. Los días hábiles se
    aproximan con semanas de cinco: no hay calendario de festivos de Colombia en
    la base, y fingir precisión que no se tiene es peor que redondear a la vista.
    """
    v, u = tipo.anticipacion_valor, tipo.anticipacion_unidad
    if u == 'horas':
        return ahora + dt.timedelta(hours=v)
    if u == 'dias_habiles':
        return ahora + dt.timedelta(days=v * 7 / 5)
    return ahora + dt.timedelta(days=v)


def _ocurrencia(tipo: AlertasTipos, cuando, ahora: dt.datetime) -> int:
    """Qué repetición toca, para que insistir no sea repetir.

    Un tipo con `repeticiones = [7, 15]` vuelve a avisar a los 7 y a los 15 días.
    La ocurrencia entra en la clave de deduplicación, así que la segunda alerta
    es otra fila y no un duplicado de la primera.
    """
    reps = list(tipo.repeticiones or [])
    if not reps or cuando is None:
        return 0
    if isinstance(cuando, dt.datetime):
        dias = (ahora - cuando).days
    elif isinstance(cuando, dt.date):
        dias = (ahora.date() - cuando).days
    else:
        return 0
    pasadas = [r for r in sorted(reps) if dias >= r]
    return pasadas[-1] if pasadas else 0


def generar(db: Session, actor: Usuarios, *, codigos: list[str] | None = None,
            ip: str | None = None) -> dict:
    """Recorre la matriz y crea lo que falte. Se puede correr cada hora.

    No borra ni cierra nada: una alerta que ya no aplica se resuelve sola cuando
    alguien atiende el caso, y mientras tanto quedarse es el punto.
    """
    ahora = _ahora()
    tipos = db.scalars(select(AlertasTipos).where(AlertasTipos.activo.is_(True))
                       .order_by(AlertasTipos.id)).all()
    creadas, por_tipo, sin_regla = 0, {}, []

    for tipo in tipos:
        if codigos and tipo.codigo not in codigos:
            continue
        regla = REGLAS.get(tipo.codigo)
        if regla is None:
            # `sync_saas_fallida` necesita la sincronización del SaaS, que es la
            # actividad 5.3: se dice en vez de fingir que se evaluó.
            sin_regla.append(tipo.codigo)
            continue

        filas = db.execute(text(regla.sql), {'corte': _corte(tipo, ahora)}).mappings().all()
        nuevas = 0
        for f in filas:
            ocurrencia = _ocurrencia(tipo, f.get('cuando'), ahora)
            clave = f'{tipo.codigo}:{f["entidad_id"]}:{ocurrencia}'
            if db.scalar(select(Alertas.id).where(Alertas.clave_dedupe == clave)):
                continue
            db.add(Alertas(
                tipo_id=tipo.id, clave_dedupe=clave, estado='nueva',
                destinatario_id=f.get('destinatario'),
                mensaje=regla.mensaje.format(**{k: (v if v is not None else '')
                                                for k, v in f.items()}),
                vence_en=f['cuando'] if isinstance(f.get('cuando'), dt.datetime) else None,
                **({regla.vinculo: f['entidad_id']} if regla.vinculo else {})))
            nuevas += 1
        if nuevas:
            por_tipo[tipo.codigo] = nuevas
            creadas += nuevas

    if creadas:
        auditar(db, operacion='insert', entidad='alertas', usuario_id=actor.id,
                despues={'creadas': creadas, 'por_tipo': por_tipo}, ip=ip)
    db.commit()
    return {'creadas': creadas, 'por_tipo': por_tipo, 'tipos_sin_regla': sin_regla}


# ------------------------------------------------------------------ bandeja

def _limite_de_alcance(actor: Usuarios | None):
    """Quien no lo ve todo ve sus alertas y las de sus trámites (RNF-03).

    Una alerta lleva el nombre del cliente y qué se le está pasando: mostrarla
    sin filtrar es enseñar el trámite de otro por la puerta de atrás.
    """
    if actor is None or actor.alcance == 'todos':
        return None
    suyos = select(Casos.id).where(Casos.responsable_id == actor.id)
    return or_(Alertas.destinatario_id == actor.id, Alertas.caso_id.in_(suyos))


def bandeja(db: Session, *, actor: Usuarios | None = None, estado: str | None = None,
            severidad: str | None = None, solo_abiertas: bool = True,
            pagina: int = 1, tamano: int = 50) -> tuple[int, list[Alertas]]:
    consulta = (select(Alertas).join(AlertasTipos, AlertasTipos.id == Alertas.tipo_id)
                .options(selectinload(Alertas.tipo), selectinload(Alertas.caso)))
    limite = _limite_de_alcance(actor)
    if limite is not None:
        consulta = consulta.where(limite)
    if estado:
        if estado not in ESTADOS:
            raise Invalido(f'Estado inválido. Opciones: {", ".join(ESTADOS)}.')
        consulta = consulta.where(Alertas.estado == estado)
    elif solo_abiertas:
        # Una pospuesta vuelve sola cuando se cumple su plazo.
        consulta = consulta.where(Alertas.estado.in_(ABIERTAS), or_(
            Alertas.pospuesta_hasta.is_(None), Alertas.pospuesta_hasta <= _ahora()))
    if severidad:
        consulta = consulta.where(AlertasTipos.severidad == severidad)

    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    orden = func.array_position(text("array['alta','media','baja']"), AlertasTipos.severidad)
    filas = list(db.scalars(consulta.order_by(orden, Alertas.generada_en.desc())
                            .offset(max(0, pagina - 1) * tamano).limit(tamano)))
    return total, filas


def obtener(db: Session, alerta_id: int, *, actor: Usuarios | None = None) -> Alertas:
    consulta = select(Alertas).where(Alertas.id == alerta_id)
    limite = _limite_de_alcance(actor)
    if limite is not None:
        consulta = consulta.where(limite)
    a = db.scalars(consulta).first()
    if a is None:
        raise NoEncontrado('La alerta no existe.')
    return a


def cambiar_estado(db: Session, actor: Usuarios, alerta_id: int, estado: str, *,
                   hasta: dt.datetime | None = None, ip: str | None = None) -> Alertas:
    """Vista, resuelta o pospuesta (RF-061).

    Posponer exige hasta cuándo: una alerta pospuesta «para después» no vuelve
    nunca, y lo que no vuelve es lo mismo que no existió.
    """
    if estado not in ESTADOS:
        raise Invalido(f'Estado inválido. Opciones: {", ".join(ESTADOS)}.')
    a = obtener(db, alerta_id, actor=actor)
    antes = instantanea(a)

    if estado == 'pospuesta':
        if hasta is None:
            raise Invalido('Diga hasta cuándo se pospone.', codigo='falta_fecha')
        if hasta.tzinfo is None:
            hasta = hasta.replace(tzinfo=BOGOTA)
        if hasta <= _ahora():
            raise Invalido('La fecha para retomarla ya pasó.', codigo='fecha_pasada')
        a.pospuesta_hasta = hasta
    else:
        a.pospuesta_hasta = None
    if estado == 'resuelta':
        a.resuelta_en, a.resuelta_por = _ahora(), actor.id
    else:
        a.resuelta_en, a.resuelta_por = None, None
    a.estado = estado

    db.flush()
    auditar(db, operacion='update', entidad='alertas', usuario_id=actor.id, entidad_id=a.id,
            antes=antes, despues=instantanea(a), ip=ip)
    db.commit()
    return a


def resumen(db: Session, actor: Usuarios | None = None) -> dict:
    """Cuántas hay abiertas y de qué gravedad: el número del encabezado."""
    consulta = (select(AlertasTipos.severidad, func.count().label('cuantas'))
                .join(Alertas, Alertas.tipo_id == AlertasTipos.id)
                .where(Alertas.estado.in_(ABIERTAS)))
    limite = _limite_de_alcance(actor)
    if limite is not None:
        consulta = consulta.where(limite)
    salida = {'alta': 0, 'media': 0, 'baja': 0}
    for sev, cuantas in db.execute(consulta.group_by(AlertasTipos.severidad)):
        salida[sev] = cuantas
    salida['total'] = sum(salida[s] for s in ('alta', 'media', 'baja'))
    return salida
