"""Gestión de usuarios y roles (RF-025 PDF, RNF-03)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import seguridad as seg
from app.core.config import ajustes
from app.core.errores import Conflicto, Invalido, NoEncontrado, Prohibido
from app.models.esquema import Permisos, Roles, Usuarios, t_roles_permisos
from app.services.auditoria import auditar, instantanea

ALCANCES = {'todos', 'asignados', 'propios'}
ROL_ADMIN = 'administradora'

#: Quien tenga este permiso puede reescribir lo que puede hacer cualquier rol,
#: incluido el suyo: es la llave maestra de la instalación, porque con ella se
#: alcanza cualquier otro permiso. Está aparte de `usuarios.editar` a propósito
#: —cambiarle el perfil a una persona es escoger entre los que ya existen;
#: redefinir el perfil mismo es otra cosa— para que el día que la
#: administración de cuentas se delegue en alguien más no se le entregue
#: también la facultad de volverse administradora.
PERMISO_MAESTRO = 'usuarios.permisos'

# Quien tenga cualquiera de estos permisos debe usar doble factor (RNF-02),
# sea cual sea su rol. Se decide por permisos y no por una lista de roles para
# que un rol nuevo, o uno ampliado, no quede por fuera sin que nadie lo note:
# así se detectó que solo_lectura veía comisiones, gastos, usuarios y auditoría
# con la sola contraseña. pagos.ver no está porque comercial y operaciones
# necesitan saber si un cliente pagó para poder atenderlo.
PERMISOS_SENSIBLES = frozenset({
    'usuarios.ver', 'auditoria.ver', 'comisiones.ver', 'gastos.ver', 'ajustes.ver',
    'pagos.crear', 'pagos.editar', 'pagos.eliminar',
    # Con la llave maestra se llega a todo lo demás: pedir solo la contraseña
    # para usarla sería dejar la puerta de atrás abierta.
    PERMISO_MAESTRO,
})


def permisos_de_rol(db: Session, rol_id: int) -> set[str]:
    filas = db.execute(
        select(Permisos.codigo)
        .join(t_roles_permisos, t_roles_permisos.c.permiso_id == Permisos.id)
        .where(t_roles_permisos.c.rol_id == rol_id))
    return {codigo for (codigo,) in filas}


def exige_mfa(db: Session, u: Usuarios) -> bool:
    return (u.rol.codigo in ajustes().roles_con_mfa
            or bool(permisos_de_rol(db, u.rol_id) & PERMISOS_SENSIBLES))


def _rol(db: Session, codigo: str) -> Roles:
    rol = db.scalar(select(Roles).where(Roles.codigo == codigo))
    if rol is None:
        raise Invalido(f'El rol «{codigo}» no existe.', codigo='rol_inexistente')
    return rol


def _usuario(db: Session, usuario_id: int) -> Usuarios:
    u = db.get(Usuarios, usuario_id)
    if u is None:
        raise NoEncontrado('El usuario no existe.')
    return u


def _proteger_admin(actor: Usuarios, objetivo: Usuarios | None = None, rol_nuevo: str | None = None) -> None:
    """Solo una administradora toca a otra administradora o asigna ese rol.
    Hoy nadie más tiene permisos sobre usuarios; esto evita que el día que otro
    rol los reciba pueda usarlos para quedarse con la cuenta de la administradora."""
    if actor.rol.codigo == ROL_ADMIN:
        return
    if (objetivo is not None and objetivo.rol.codigo == ROL_ADMIN) or rol_nuevo == ROL_ADMIN:
        raise Prohibido('Solo una administradora puede gestionar cuentas de administradora.',
                        codigo='requiere_admin')


def _proteger_rol_admin(actor: Usuarios, rol: Roles) -> None:
    """Solo una administradora reescribe los permisos del rol administradora.

    Ese rol es la última puerta de la instalación: mientras conserve «gestionar
    permisos» —y siempre queda una administradora activa, de eso se encarga
    `editar`— hay alguien que puede volver a abrir lo que se cerró por error. Si
    desde otro rol se le pudiera recortar, quien reciba prestada la gestión de
    permisos podría cerrarle la puerta justo a quien se la prestó.
    """
    if rol.codigo == ROL_ADMIN and actor.rol.codigo != ROL_ADMIN:
        raise Prohibido('Solo una administradora puede cambiar los permisos del rol '
                        'administradora.', codigo='requiere_admin')


def _admins_activos(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Usuarios).join(Roles)
                     .where(Roles.codigo == ROL_ADMIN, Usuarios.activo.is_(True)))


def _gestores_de_permisos_activos(db: Session) -> int:
    """Cuántas personas activas podrían, ahora mismo, reescribir la matriz.

    Si llega a cero la instalación se queda sin dueña: no hay pantalla que lo
    arregle, hay que entrar a la base de datos por fuera del sistema.
    """
    return db.scalar(
        select(func.count()).select_from(Usuarios)
        .join(t_roles_permisos, t_roles_permisos.c.rol_id == Usuarios.rol_id)
        .join(Permisos, Permisos.id == t_roles_permisos.c.permiso_id)
        .where(Permisos.codigo == PERMISO_MAESTRO, Usuarios.activo.is_(True)))


def listar(db: Session) -> list[Usuarios]:
    return list(db.scalars(select(Usuarios).order_by(Usuarios.nombre)))


def listar_roles(db: Session) -> list[tuple[Roles, set[str]]]:
    return [(r, permisos_de_rol(db, r.id)) for r in db.scalars(select(Roles).order_by(Roles.id))]


def catalogo_permisos(db: Session) -> list[Permisos]:
    """Todo lo que se le puede dar a un rol, agrupable por módulo.

    La pantalla de permisos lo necesita para ofrecer casillas con nombres en
    español: sin esto habría que acordarse de memoria de los códigos, y un
    código mal escrito es un permiso que nadie recibe y nadie nota.
    """
    return list(db.scalars(select(Permisos).order_by(Permisos.modulo, Permisos.codigo)))


def fijar_permisos(db: Session, actor: Usuarios, rol_id: int, codigos: list[str], *,
                   ip: str | None = None) -> tuple[Roles, set[str]]:
    """Reescribe qué puede hacer un rol (RF-077).

    Llega la lista completa y no «agregue este, quite aquel»: la pantalla es una
    matriz de casillas y guarda lo que la administradora dejó marcado. Lo que no
    venga en la lista se le quita.

    El cambio vale en el acto y para todas las personas que tengan ese rol,
    estén o no con la pantalla abierta: los permisos se consultan en cada
    solicitud y no viajan en el token. Quitarle «ver trámites» a operaciones se
    lo quita en ese segundo a las cinco personas de operaciones. Por eso queda
    en auditoría la lista de antes y la de después, además de lo que entró y lo
    que salió: el día que alguien pregunte «¿por qué ya no puedo?», la
    respuesta está ahí y no hay que reconstruirla.

    Lo que no se deja hacer, porque deja la instalación sin dueña y solo se
    arregla entrando a la base de datos por fuera del sistema:

    - Quitarse a sí misma la llave de los permisos. Se lo pide a otra.
    - Recortarle esa llave al rol administradora desde otro rol.
    - Cualquier cambio que no deje ninguna persona activa capaz de gestionar
      permisos. Las dos reglas de arriba ya lo impiden por su lado; esta es la
      red por debajo, para que ningún camino nuevo pueda saltársela.
    """
    rol = db.get(Roles, rol_id)
    if rol is None:
        raise NoEncontrado('El rol no existe.')
    _proteger_rol_admin(actor, rol)

    pedidos = set(codigos)
    por_codigo = {c: i for c, i in db.execute(select(Permisos.codigo, Permisos.id))}
    desconocidos = sorted(pedidos - set(por_codigo))
    if desconocidos:
        raise Invalido(f'Estos permisos no existen: {", ".join(desconocidos)}.',
                       codigo='permiso_inexistente')

    antes = permisos_de_rol(db, rol_id)
    if antes == pedidos:
        # Guardar sin haber cambiado nada no es un cambio: no se audita, para
        # que el registro no se llene de ruido y lo que quede se pueda leer.
        return rol, antes

    if (PERMISO_MAESTRO in antes and PERMISO_MAESTRO not in pedidos
            and rol_id == actor.rol_id):
        raise Prohibido(
            'No puede quitarse a sí misma «gestionar permisos»: quedaría sin forma de '
            'devolvérselo. Pídale el cambio a otra administradora.', codigo='autoedicion')

    db.execute(t_roles_permisos.delete().where(t_roles_permisos.c.rol_id == rol_id))
    if pedidos:
        db.execute(t_roles_permisos.insert(),
                   [{'rol_id': rol_id, 'permiso_id': por_codigo[c]} for c in sorted(pedidos)])
    db.flush()

    if _gestores_de_permisos_activos(db) == 0:
        db.rollback()
        raise Conflicto(
            'Con este cambio no quedaría ninguna persona activa que pueda gestionar '
            'permisos, y la instalación se quedaría sin dueña.',
            codigo='ultimo_gestor_permisos')

    # Las dos listas completas, y además el resumen de lo que entró y lo que
    # salió: comparar a ojo dos listas de setenta permisos no se le puede pedir
    # a nadie. De qué rol se trata lo dice `entidad_id`; el código del rol no se
    # repite aquí porque la auditoría guarda solo lo que cambió y un dato igual
    # a los dos lados se descarta.
    auditar(db, operacion='update', entidad='roles_permisos', usuario_id=actor.id,
            entidad_id=rol.id, antes={'permisos': sorted(antes)},
            despues={'permisos': sorted(pedidos),
                     'agregados': sorted(pedidos - antes), 'quitados': sorted(antes - pedidos)},
            ip=ip)
    db.commit()
    return rol, pedidos


def crear(db: Session, actor: Usuarios | None, *, nombre: str, email: str, rol: str,
          alcance: str = 'todos', ip: str | None = None) -> tuple[Usuarios, str]:
    """Crea el usuario con una contraseña temporal que se entrega una sola vez.
    Hasta que la cambie, el usuario solo puede entrar a cambiarla."""
    if actor is not None:
        _proteger_admin(actor, rol_nuevo=rol)
    if alcance not in ALCANCES:
        raise Invalido(f'Alcance inválido. Opciones: {", ".join(sorted(ALCANCES))}.')
    if db.scalar(select(Usuarios.id).where(Usuarios.email == email)):
        raise Conflicto('Ya existe un usuario con ese correo.', codigo='email_duplicado')
    temporal = seg.password_temporal()
    u = Usuarios(nombre=nombre.strip(), email=email, password_hash=seg.hash_password(temporal),
                 rol_id=_rol(db, rol).id, alcance=alcance, debe_cambiar_password=True)
    db.add(u)
    try:
        db.flush()
    except IntegrityError:
        # Dos altas simultáneas con el mismo correo pasan ambas la comprobación
        # de arriba; el índice único detiene a la segunda.
        db.rollback()
        raise Conflicto('Ya existe un usuario con ese correo.', codigo='email_duplicado')
    auditar(db, operacion='insert', entidad='usuarios', usuario_id=actor.id if actor else None,
            entidad_id=u.id, despues=instantanea(u), ip=ip)
    db.commit()
    return u, temporal


def editar(db: Session, actor: Usuarios, usuario_id: int, *, nombre: str | None = None,
           rol: str | None = None, activo: bool | None = None, alcance: str | None = None,
           ip: str | None = None) -> Usuarios:
    u = _usuario(db, usuario_id)
    _proteger_admin(actor, u, rol)
    antes = instantanea(u)
    era_admin_activo = u.rol.codigo == ROL_ADMIN and u.activo

    if u.id == actor.id and (activo is False or (rol and rol != u.rol.codigo)):
        raise Prohibido('No puede desactivarse ni cambiarse el rol a sí misma: '
                        'lo debe hacer otra administradora.', codigo='autoedicion')
    if nombre is not None:
        u.nombre = nombre.strip()
    if rol is not None:
        u.rol_id = _rol(db, rol).id
    if activo is not None:
        u.activo = activo
    if alcance is not None:
        if alcance not in ALCANCES:
            raise Invalido(f'Alcance inválido. Opciones: {", ".join(sorted(ALCANCES))}.')
        u.alcance = alcance

    db.flush()
    db.refresh(u)
    if era_admin_activo and not (u.rol.codigo == ROL_ADMIN and u.activo) and _admins_activos(db) == 0:
        db.rollback()
        raise Conflicto('Debe quedar al menos una administradora activa.', codigo='ultima_admin')
    auditar(db, operacion='update', entidad='usuarios', usuario_id=actor.id, entidad_id=u.id,
            antes=antes, despues=instantanea(u), ip=ip)
    db.commit()
    return u


def restablecer_password(db: Session, actor: Usuarios, usuario_id: int,
                         ip: str | None = None) -> str:
    """La administradora le entrega una contraseña temporal nueva. Cierra todas
    las sesiones abiertas de ese usuario y le quita el bloqueo si lo tenía."""
    u = _usuario(db, usuario_id)
    _proteger_admin(actor, u)
    temporal = seg.password_temporal()
    u.password_hash = seg.hash_password(temporal)
    u.debe_cambiar_password = True
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    auditar(db, operacion='password_reset', entidad='usuarios', usuario_id=actor.id,
            entidad_id=u.id, despues={'por': 'administradora'}, ip=ip)
    db.commit()
    return temporal


def reiniciar_mfa(db: Session, actor: Usuarios, usuario_id: int, ip: str | None = None) -> str:
    """Para quien perdió el teléfono. Reinicia TAMBIÉN la contraseña y devuelve
    una temporal: si solo se quitara el doble factor, quien tuviera la
    contraseña por phishing podría entrar en ese intervalo y activar su propio
    teléfono antes que la dueña de la cuenta. La temporal se entrega por un
    canal aparte, y el cambio cierra todas las sesiones abiertas."""
    u = _usuario(db, usuario_id)
    _proteger_admin(actor, u)
    temporal = seg.password_temporal()
    u.mfa_habilitado = False
    u.mfa_secreto = None
    u.password_hash = seg.hash_password(temporal)
    u.debe_cambiar_password = True
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    auditar(db, operacion='mfa_reiniciado', entidad='usuarios', usuario_id=actor.id,
            entidad_id=u.id, ip=ip)
    db.commit()
    return temporal
