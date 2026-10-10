"""Conservar, anonimizar y eliminar datos personales (RNF-09).

La Ley 1581 de 2012 le da a cualquier persona el derecho a que le borren sus
datos. El Código de Comercio obliga a conservar la contabilidad. Las dos cosas
son ciertas al mismo tiempo, y de ahí sale el diseño de este módulo:

**Si la persona tiene plata de por medio, se anonimiza; si no, se elimina.**
Anonimizar quita lo que identifica —nombre, documento, pasaporte, teléfono,
correo, DS-160— y deja en pie las ventas y los pagos. Las cuentas siguen
cuadrando y nadie puede saber de quién eran. Eliminar borra todo rastro, y solo
se puede cuando no hay nada contable que conservar: un lead que nunca compró.

**Lo que se borra no se puede deshacer, así que primero se dice qué va a pasar.**
`evaluar` responde antes de tocar nada: qué se va a anonimizar, qué se va a
eliminar, y por qué. Es la diferencia entre atender un derecho y perder datos.

**El índice ciego también se va.** `pasaporte_indice` y `ds160_hash` no guardan
el dato, pero permiten confirmar una corazonada: quien tenga el pasaporte de
alguien puede preguntarle al sistema si esa persona estuvo. Anonimizar sin
borrarlos sería dejar la puerta entreabierta.

**Queda el rastro de que se hizo.** La auditoría registra quién lo pidió, quién
lo ejecutó y cuándo, sin volver a escribir los datos que se estaban quitando:
un registro de anonimización que incluya el nombre no anonimiza nada.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errores import Conflicto, Invalido, NoEncontrado
from app.models.esquema import Clientes, Usuarios
from app.services.auditoria import auditar

BOGOTA = ZoneInfo('America/Bogota')

# Lo que queda en lugar del dato. Se ve a simple vista que fue a propósito y no
# un error de carga, que es lo que pasaría con una cadena vacía.
MARCA = 'ANONIMIZADO'

# Años que se conservan los datos de alguien que ya no es cliente. El Código de
# Comercio pide diez para los libros; la contabilidad sobrevive a la
# anonimización, así que este plazo es para los datos personales, no para ella.
ANIOS_DE_CONSERVACION = 5


@dataclass
class Evaluacion:
    """Qué pasaría si se atiende la solicitud, antes de tocar nada."""
    cliente_id: int
    nombre: str
    puede_eliminarse: bool
    personas: int = 0
    ventas: int = 0
    pagos: int = 0
    tramites: int = 0
    razon: str = ''
    advertencias: list[str] = field(default_factory=list)


def _ahora() -> dt.datetime:
    return dt.datetime.now(BOGOTA)


def evaluar(db: Session, cliente_id: int) -> Evaluacion:
    """Qué se puede hacer con los datos de este cliente, y por qué.

    Se consulta antes de ejecutar. Borrar no se puede deshacer, y la persona
    que atiende la solicitud tiene derecho a saber qué va a pasar.
    """
    cliente = db.get(Clientes, cliente_id)
    if cliente is None:
        raise NoEncontrado('El cliente no existe.')

    cuentas = db.execute(text("""
        select (select count(*) from solicitantes s
                 where s.cliente_id = :c or s.grupo_id in
                       (select id from grupos where cliente_contacto_id = :c)) as personas,
               (select count(*) from negocios   where cliente_id = :c) as ventas,
               (select count(*) from pagos p join negocios n on n.id = p.negocio_id
                 where n.cliente_id = :c) as pagos,
               (select count(*) from casos ca join negocios n on n.id = ca.negocio_id
                 where n.cliente_id = :c) as tramites"""), {'c': cliente_id}).mappings().one()

    e = Evaluacion(cliente_id=cliente_id, nombre=cliente.nombre,
                   puede_eliminarse=cuentas['ventas'] == 0 and cuentas['pagos'] == 0,
                   **{k: cuentas[k] for k in ('personas', 'ventas', 'pagos', 'tramites')})

    if e.puede_eliminarse:
        e.razon = ('No tiene ventas ni pagos: no hay nada contable que conservar, '
                   'así que se puede eliminar por completo.')
    else:
        e.razon = (f'Tiene {e.ventas} venta(s) y {e.pagos} pago(s). La contabilidad hay que '
                   f'conservarla, así que se anonimiza: se quita lo que identifica a la '
                   f'persona y las cuentas siguen cuadrando.')
    if e.tramites:
        e.advertencias.append(
            f'{e.tramites} trámite(s) quedan sin nombre pero con su historia: sirve para '
            f'estadísticas y no permite saber de quién era.')
    if cliente.archivado:
        e.advertencias.append('El cliente ya estaba archivado.')
    return e


def _personas_de(db: Session, cliente_id: int) -> list[int]:
    return [i for (i,) in db.execute(text("""
        select id from solicitantes
         where cliente_id = :c
            or grupo_id in (select id from grupos where cliente_contacto_id = :c)"""),
        {'c': cliente_id})]


def anonimizar(db: Session, actor: Usuarios, cliente_id: int, motivo: str, *,
               ip: str | None = None) -> Evaluacion:
    """Quita lo que identifica y deja en pie la contabilidad (RNF-09).

    No borra filas: las ventas, los pagos y los trámites siguen ahí, porque son
    los libros de la empresa. Lo que desaparece es de quién eran.
    """
    if not motivo or len(motivo.strip()) < 5:
        raise Invalido('Escriba por qué se anonimiza: una solicitud del titular, el plazo '
                       'de conservación cumplido, una orden.', codigo='falta_motivo')
    e = evaluar(db, cliente_id)
    personas = _personas_de(db, cliente_id)
    sello = _ahora().strftime('%Y%m%d%H%M%S')
    p = {'c': cliente_id, 'marca': MARCA, 'etiqueta': f'{MARCA}-{sello}'}

    db.execute(text("""
        update clientes
           set nombre = :etiqueta, tipo_documento = null, numero_documento = null,
               telefono = null, email = null, observaciones = :marca, archivado = true
         where id = :c"""), p)

    if personas:
        # El indice ciego se va con el dato: no guarda el pasaporte, pero deja
        # confirmar que alguien estuvo, y eso tambien identifica.
        db.execute(text("""
            update solicitantes
               set nombre = :etiqueta, tipo_documento = null, numero_documento = null,
                   pasaporte = null, pasaporte_indice = null, fecha_nacimiento = null,
                   telefono = null, email = null, observaciones = :marca
             where id = any(:ids)"""), p | {'ids': personas})

        db.execute(text("""
            update casos set ds160_numero_cifrado = null, ds160_hash = null
             where solicitante_id = any(:ids)"""), {'ids': personas})

    db.execute(text("""
        update grupos set nombre = cast(:etiqueta as varchar),
                          observaciones = cast(:marca as text)
         where cliente_contacto_id = :c"""), p)

    # El nombre de quien consigna y las notas libres de los pagos: ahi se escribe
    # de todo, incluidos datos de la persona.
    db.execute(text("""
        update pagos set pagador_nombre = null, observacion = cast(:marca as text)
          from negocios n
         where pagos.negocio_id = n.id and n.cliente_id = :c
           and (pagos.pagador_nombre is not null or pagos.observacion is not null)"""), p)

    # Las actividades son texto libre: una nota de llamada puede tener el
    # telefono, la direccion o el numero de pasaporte.
    db.execute(text("""
        update actividades set asunto = cast(:marca as varchar),
                               cuerpo = cast(:marca as text), direccion = null
         where (entidad = 'cliente' and entidad_id = :c)
            or (entidad = 'solicitante' and entidad_id = any(:ids))"""),
        p | {'ids': personas or [0]})

    db.execute(text("""
        update documentos set nombre = cast(:marca as varchar), url = null, ruta = null
         where (entidad = 'cliente' and entidad_id = :c)
            or (entidad = 'solicitante' and entidad_id = any(:ids))"""),
        p | {'ids': personas or [0]})

    # El registro NO repite los datos que se acaban de quitar: una auditoria de
    # anonimizacion que incluya el nombre no anonimiza nada.
    auditar(db, operacion='anonimizar', entidad='clientes', usuario_id=actor.id,
            entidad_id=cliente_id,
            despues={'motivo': motivo.strip(), 'personas': len(personas),
                     'ventas': e.ventas, 'pagos': e.pagos, 'marca': p['etiqueta']}, ip=ip)
    db.commit()
    return e


def eliminar(db: Session, actor: Usuarios, cliente_id: int, motivo: str, *,
             ip: str | None = None) -> Evaluacion:
    """Borra todo rastro. Solo cuando no hay nada contable que conservar.

    Si tiene ventas o pagos se niega y dice que use `anonimizar`: borrar la
    contabilidad no es un derecho del titular ni una facultad de la empresa.
    """
    if not motivo or len(motivo.strip()) < 5:
        raise Invalido('Escriba por qué se elimina.', codigo='falta_motivo')
    e = evaluar(db, cliente_id)
    if not e.puede_eliminarse:
        raise Conflicto(
            f'Ese cliente tiene {e.ventas} venta(s) y {e.pagos} pago(s), y la contabilidad '
            f'hay que conservarla. Use anonimizar: quita lo que identifica a la persona y '
            f'deja las cuentas cuadrando.', codigo='tiene_contabilidad')

    personas = _personas_de(db, cliente_id)
    p = {'c': cliente_id, 'ids': personas or [0]}
    for sql in (
        "delete from actividades where (entidad='cliente' and entidad_id=:c) "
        "   or (entidad='solicitante' and entidad_id = any(:ids))",
        "delete from documentos  where (entidad='cliente' and entidad_id=:c) "
        "   or (entidad='solicitante' and entidad_id = any(:ids))",
        'delete from tareas where cliente_id = :c',
        'delete from casos_historial where caso_id in '
        '  (select id from casos where solicitante_id = any(:ids))',
        'delete from casos_checklist where caso_id in '
        '  (select id from casos where solicitante_id = any(:ids))',
        'delete from citas where caso_id in '
        '  (select id from casos where solicitante_id = any(:ids))',
        'delete from alertas where caso_id in '
        '  (select id from casos where solicitante_id = any(:ids))',
        'delete from casos where solicitante_id = any(:ids)',
        'delete from solicitantes where id = any(:ids)',
        'delete from grupos where cliente_contacto_id = :c',
        'delete from oportunidades where cliente_id = :c',
        'delete from clientes where id = :c',
    ):
        db.execute(text(sql), p)

    auditar(db, operacion='eliminar', entidad='clientes', usuario_id=actor.id,
            entidad_id=cliente_id,
            despues={'motivo': motivo.strip(), 'personas': len(personas)}, ip=ip)
    db.commit()
    e.razon = 'Eliminado por completo: no tenía ventas ni pagos.'
    return e


def vencidos(db: Session, anios: int = ANIOS_DE_CONSERVACION) -> list[dict]:
    """Clientes sin actividad desde hace más del plazo de conservación.

    No borra nada: los lista. Depurar automáticamente datos de personas es la
    clase de automatismo que un día se lleva lo que no debía, y aquí lo que se
    pierde no se recupera.
    """
    if anios < 1:
        raise Invalido('El plazo de conservación es de al menos un año.')
    return [dict(f) for f in db.execute(text("""
        select c.id, c.nombre, c.creado_en::date as desde,
               greatest(c.creado_en,
                        coalesce(c.ultimo_contacto_en, c.creado_en),
                        coalesce((select max(n.fecha_venta)::timestamptz
                                    from negocios n where n.cliente_id = c.id),
                                 c.creado_en)) ::date as ultima_senal,
               (select count(*) from negocios n where n.cliente_id = c.id) as ventas
          from clientes c
         where c.nombre not like :marca
           and greatest(c.creado_en,
                        coalesce(c.ultimo_contacto_en, c.creado_en),
                        coalesce((select max(n.fecha_venta)::timestamptz
                                    from negocios n where n.cliente_id = c.id),
                                 c.creado_en)) < now() - make_interval(years => :anios)
         order by ultima_senal"""),
        {'anios': anios, 'marca': f'{MARCA}%'}).mappings()]


def ya_anonimizados(db: Session) -> int:
    return db.scalar(select(text('count(*)')).select_from(Clientes)
                     .where(Clientes.nombre.like(f'{MARCA}%'))) or 0
