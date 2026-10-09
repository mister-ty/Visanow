"""Plantillas de mensajes por evento (RF-063).

El sistema arma el mensaje; no lo envía. «Enviar» es abrir WhatsApp o el correo
con el texto ya puesto, y la persona lo manda: así nada sale a un cliente sin
que alguien lo haya leído, y no hace falta guardar credenciales de ningún canal.
"""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.deps import permisos_de_rol
from app.core.errores import Conflicto, Invalido, NoEncontrado, Prohibido
from app.models.esquema import Casos, Usuarios
from app.services import cartera as serv_cartera
from app.services.auditoria import auditar
from app.services.casos import alcance_de

EVENTOS = {
    'cita_confirmada': 'Cita confirmada',
    'cita_recordatorio': 'Recordatorio de cita',
    'saldo_pendiente': 'Saldo pendiente',
    'pago_recibido': 'Pago recibido',
    'documentos_pendientes': 'Documentos pendientes',
    'tramite_actualizado': 'Trámite actualizado',
}

VARIABLES = {
    'cliente_nombre': 'Quien compró',
    'solicitante_nombre': 'Quien viaja o hace el trámite',
    'cita_tipo': 'Tipo de la próxima cita (CAS, biometría, entrevista…)',
    'cita_fecha': 'Fecha de la próxima cita, en hora de Bogotá o la de la sede',
    'cita_hora': 'Hora de la próxima cita',
    'cita_sede': 'Sede de la próxima cita',
    'saldo': 'Saldo pendiente de la venta (lo calcula el sistema)',
    'valor_pactado': 'Valor acordado de la venta',
    'responsable_nombre': 'Responsable del trámite',
}
# Estas dos son plata: quien no ve la contabilidad no las puede imprimir
_MONETARIAS = {'saldo', 'valor_pactado'}
_PATRON = re.compile(r'\{\{\s*([a-z_]+)\s*\}\}')
_DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
_MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
          'septiembre', 'octubre', 'noviembre', 'diciembre']
_TIPOS_CITA = {'cas': 'CAS', 'biometria': 'biometría', 'entrevista': 'entrevista',
               'radicacion': 'radicación', 'preparacion': 'preparación',
               'entrega': 'entrega', 'otra': 'cita'}

_COLUMNAS = 'id, evento, nombre, canal, asunto, cuerpo, activa, actualizada_en'


def variables_de(cuerpo: str, asunto: str | None = None) -> list[str]:
    return sorted(set(_PATRON.findall(cuerpo)) | set(_PATRON.findall(asunto or '')))


def _validar(evento: str, cuerpo: str, asunto: str | None) -> None:
    if evento not in EVENTOS:
        raise Invalido(f'Evento desconocido. Opciones: {", ".join(EVENTOS)}.')
    desconocidas = [v for v in variables_de(cuerpo, asunto) if v not in VARIABLES]
    # Una variable mal escrita saldría tal cual en el mensaje al cliente
    if desconocidas:
        raise Invalido('Variables que no existen: ' + ', '.join('{{%s}}' % v for v in desconocidas)
                       + '. Disponibles: ' + ', '.join(VARIABLES) + '.')


def _fila(f) -> dict:
    return {'id': f[0], 'evento': f[1], 'nombre': f[2], 'canal': f[3], 'asunto': f[4],
            'cuerpo': f[5], 'activa': f[6], 'actualizada_en': f[7],
            'variables': variables_de(f[5], f[4])}


def listar(db: Session, *, evento: str | None = None, solo_activas: bool = True) -> list[dict]:
    filtros, p = [], {}
    if evento:
        filtros.append('evento = :e')
        p['e'] = evento
    if solo_activas:
        filtros.append('activa')
    donde = ('where ' + ' and '.join(filtros)) if filtros else ''
    return [_fila(f) for f in db.execute(
        text(f'select {_COLUMNAS} from plantillas_mensaje {donde} order by evento, nombre'), p)]


def _una(db: Session, plantilla_id: int):
    f = db.execute(text(f'select {_COLUMNAS} from plantillas_mensaje where id = :i'),
                   {'i': plantilla_id}).first()
    if f is None:
        raise NoEncontrado('La plantilla no existe.')
    return f


def crear(db: Session, actor: Usuarios, datos: dict, *, ip: str | None = None) -> dict:
    _validar(datos['evento'], datos['cuerpo'], datos.get('asunto'))
    existe = db.scalar(text("""select 1 from plantillas_mensaje
                                where evento = :evento and canal = :canal and nombre = :nombre"""),
                       datos)
    if existe:
        raise Conflicto('Ya hay una plantilla con ese nombre para ese evento y canal.')
    nueva = db.execute(text(f"""
        insert into plantillas_mensaje (evento, nombre, canal, asunto, cuerpo, creada_por)
        values (:evento, :nombre, :canal, :asunto, :cuerpo, :autor)
        returning {_COLUMNAS}"""), {**{'asunto': None}, **datos, 'autor': actor.id}).first()
    auditar(db, operacion='insert', entidad='plantillas_mensaje', usuario_id=actor.id,
            entidad_id=nueva[0], despues={'evento': datos['evento'], 'nombre': datos['nombre']},
            ip=ip)
    db.commit()
    return _fila(nueva)


def editar(db: Session, actor: Usuarios, plantilla_id: int, cambios: dict,
           *, ip: str | None = None) -> dict:
    actual = _una(db, plantilla_id)
    cuerpo = cambios.get('cuerpo', actual[5])
    asunto = cambios['asunto'] if 'asunto' in cambios else actual[4]
    _validar(actual[1], cuerpo, asunto)
    nuevo = db.execute(text(f"""
        update plantillas_mensaje
           set nombre = :nombre, asunto = :asunto, cuerpo = :cuerpo, activa = :activa,
               actualizada_en = now()
         where id = :id returning {_COLUMNAS}"""), {
        'id': plantilla_id, 'nombre': cambios.get('nombre') or actual[2], 'asunto': asunto,
        'cuerpo': cuerpo, 'activa': actual[6] if cambios.get('activa') is None else cambios['activa'],
    }).first()
    auditar(db, operacion='update', entidad='plantillas_mensaje', usuario_id=actor.id,
            entidad_id=plantilla_id, antes={'cuerpo': actual[5], 'activa': actual[6]},
            despues={'cuerpo': nuevo[5], 'activa': nuevo[6]}, ip=ip)
    db.commit()
    return _fila(nuevo)


# ----------------------------------------------------------------- generación

def _fecha_larga(d: dt.datetime) -> str:
    return f'{_DIAS[d.weekday()]} {d.day} de {_MESES[d.month - 1]} de {d.year}'


def _hora(d: dt.datetime) -> str:
    h12 = d.hour % 12 or 12
    return f'{h12}:{d.minute:02d} {"a. m." if d.hour < 12 else "p. m."}'


def _pesos(valor: float) -> str:
    return '$' + f'{valor:,.0f}'.replace(',', '.')


def _contexto(db: Session, actor: Usuarios, caso_id: int | None,
              negocio_id: int | None) -> tuple[dict, str | None, str | None]:
    if not caso_id and not negocio_id:
        raise Invalido('Indique el trámite (caso_id) o la venta (negocio_id) del mensaje.')
    limite = alcance_de(actor)
    ctx: dict[str, str] = {}
    if caso_id:
        # El alcance se aplica aquí: un mensaje con el nombre y la cita de un
        # cliente ajeno es una forma de verlo sin pasar por la lista (RNF-03)
        consulta = select(Casos.id).where(Casos.id == caso_id)
        if limite is not None:
            consulta = consulta.where(limite)
        if db.scalar(consulta) is None:
            raise NoEncontrado('El trámite no existe.')
        fila = db.execute(text("""
            select ca.negocio_id, so.nombre, u.nombre
              from casos ca join solicitantes so on so.id = ca.solicitante_id
              left join usuarios u on u.id = ca.responsable_id
             where ca.id = :c"""), {'c': caso_id}).first()
        negocio_id = fila[0]
        ctx['solicitante_nombre'] = fila[1]
        if fila[2]:
            ctx['responsable_nombre'] = fila[2]
        # La próxima cita viva: una ya realizada o cancelada no se le recuerda a nadie
        cita = db.execute(text("""
            select ci.tipo, ci.inicia_en, ci.zona_horaria, se.nombre
              from citas ci left join sedes se on se.id = ci.sede_id
             where ci.caso_id = :c and ci.estado in ('pendiente','programada','confirmada','reprogramada')
               and ci.inicia_en >= now()
             order by ci.inicia_en limit 1"""), {'c': caso_id}).first()
        if cita:
            # En la zona de la sede: una cita en EE. UU. se le dice al cliente a la hora de allá
            local = cita[1].astimezone(ZoneInfo(cita[2] or 'America/Bogota'))
            ctx['cita_tipo'] = _TIPOS_CITA.get(cita[0], cita[0])
            ctx['cita_fecha'] = _fecha_larga(local)
            ctx['cita_hora'] = _hora(local)
            if cita[3]:
                ctx['cita_sede'] = cita[3]
    elif limite is not None:
        raise Prohibido('Con su alcance solo puede generar mensajes desde un trámite suyo.',
                        codigo='sin_alcance')

    venta = db.execute(text("""
        select cl.nombre, cl.telefono, cl.email, u.nombre
          from negocios n join clientes cl on cl.id = n.cliente_id
          left join usuarios u on u.id = n.vendedor_id
         where n.id = :n"""), {'n': negocio_id}).first()
    if venta is None:
        raise NoEncontrado('La venta no existe.')
    ctx['cliente_nombre'] = venta[0]
    if venta[3] and 'responsable_nombre' not in ctx:
        ctx['responsable_nombre'] = venta[3]
    if 'pagos.ver' in permisos_de_rol(db, actor.rol_id):
        # El saldo sale de la vista, igual que en la pantalla de cartera
        estado = serv_cartera.estado_de(db, negocio_id)
        if estado:
            ctx['saldo'] = _pesos(estado.saldo)
            ctx['valor_pactado'] = _pesos(estado.valor_pactado)
    return ctx, venta[1], venta[2]


def generar(db: Session, actor: Usuarios, plantilla_id: int, *, caso_id: int | None,
            negocio_id: int | None) -> dict:
    p = _fila(_una(db, plantilla_id))
    if not p['activa']:
        raise Invalido('La plantilla está desactivada.')
    if (set(p['variables']) & _MONETARIAS
            and 'pagos.ver' not in permisos_de_rol(db, actor.rol_id)):
        raise Prohibido('Esta plantilla incluye montos y su rol no los ve.', codigo='sin_permiso')
    ctx, telefono, correo = _contexto(db, actor, caso_id, negocio_id)
    faltantes: set[str] = set()

    def poner(m: re.Match) -> str:
        clave = m.group(1)
        if clave in ctx:
            return ctx[clave]
        # Sin dato se deja la variable a la vista: un mensaje con «a las  en »
        # se manda sin darse cuenta; uno con {{cita_hora}} no
        faltantes.add(clave)
        return m.group(0)

    return {'asunto': _PATRON.sub(poner, p['asunto']) if p['asunto'] else None,
            'mensaje': _PATRON.sub(poner, p['cuerpo']), 'faltantes': sorted(faltantes),
            'telefono': telefono, 'correo': correo}
