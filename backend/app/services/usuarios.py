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

# Quien tenga cualquiera de estos permisos debe usar doble factor (RNF-02),
# sea cual sea su rol. Se decide por permisos y no por una lista de roles para
# que un rol nuevo, o uno ampliado, no quede por fuera sin que nadie lo note:
# así se detectó que solo_lectura veía comisiones, gastos, usuarios y auditoría
# con la sola contraseña. pagos.ver no está porque comercial y operaciones
# necesitan saber si un cliente pagó para poder atenderlo.
PERMISOS_SENSIBLES = frozenset({
    'usuarios.ver', 'auditoria.ver', 'comisiones.ver', 'gastos.ver', 'ajustes.ver',
    'pagos.crear', 'pagos.editar', 'pagos.eliminar',
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


def _admins_activos(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Usuarios).join(Roles)
                     .where(Roles.codigo == ROL_ADMIN, Usuarios.activo.is_(True)))


def listar(db: Session) -> list[Usuarios]:
    return list(db.scalars(select(Usuarios).order_by(Usuarios.nombre)))


def listar_roles(db: Session) -> list[tuple[Roles, set[str]]]:
    return [(r, permisos_de_rol(db, r.id)) for r in db.scalars(select(Roles).order_by(Roles.id))]


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
