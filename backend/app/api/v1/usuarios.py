from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.schemas import usuarios as esq
from app.services import usuarios as servicio

router = APIRouter(tags=['usuarios y roles'])


def _salida(u: Usuarios) -> esq.UsuarioSalida:
    return esq.UsuarioSalida(
        id=u.id, nombre=u.nombre, email=u.email, rol=u.rol.codigo, alcance=u.alcance,
        activo=u.activo, mfa_habilitado=u.mfa_habilitado,
        debe_cambiar_password=u.debe_cambiar_password,
        bloqueado=bool(u.bloqueado_hasta and u.bloqueado_hasta > datetime.now(timezone.utc)),
        ultimo_acceso=u.ultimo_acceso, creado_en=u.creado_en)


@router.get('/usuarios', response_model=list[esq.UsuarioSalida])
def listar(_: Usuarios = Depends(requiere('usuarios.ver')), db: Session = Depends(get_db)):
    return [_salida(u) for u in servicio.listar(db)]


@router.post('/usuarios', response_model=esq.PasswordTemporalSalida,
             status_code=status.HTTP_201_CREATED)
def crear(datos: esq.UsuarioCrear, request: Request,
          actor: Usuarios = Depends(requiere('usuarios.crear')), db: Session = Depends(get_db)):
    u, temporal = servicio.crear(db, actor, nombre=datos.nombre, email=datos.email, rol=datos.rol,
                                 alcance=datos.alcance, ip=ip_cliente(request))
    return esq.PasswordTemporalSalida(usuario=_salida(u), password_temporal=temporal)


@router.patch('/usuarios/{usuario_id}', response_model=esq.UsuarioSalida)
def editar(usuario_id: int, datos: esq.UsuarioEditar, request: Request,
           actor: Usuarios = Depends(requiere('usuarios.editar')), db: Session = Depends(get_db)):
    u = servicio.editar(db, actor, usuario_id, **datos.model_dump(exclude_unset=True),
                        ip=ip_cliente(request))
    return _salida(u)


@router.post('/usuarios/{usuario_id}/restablecer-password', response_model=esq.PasswordTemporalSalida)
def restablecer_password(usuario_id: int, request: Request,
                         actor: Usuarios = Depends(requiere('usuarios.editar')),
                         db: Session = Depends(get_db)):
    temporal = servicio.restablecer_password(db, actor, usuario_id, ip=ip_cliente(request))
    return esq.PasswordTemporalSalida(usuario=_salida(db.get(Usuarios, usuario_id)),
                                      password_temporal=temporal)


@router.post('/usuarios/{usuario_id}/reiniciar-mfa', response_model=esq.PasswordTemporalSalida)
def reiniciar_mfa(usuario_id: int, request: Request,
                  actor: Usuarios = Depends(requiere('usuarios.editar')),
                  db: Session = Depends(get_db)):
    """Reinicia el doble factor y la contraseña a la vez: ver services.usuarios.reiniciar_mfa."""
    temporal = servicio.reiniciar_mfa(db, actor, usuario_id, ip=ip_cliente(request))
    return esq.PasswordTemporalSalida(usuario=_salida(db.get(Usuarios, usuario_id)),
                                      password_temporal=temporal)


@router.get('/usuarios/asignables', response_model=list[esq.UsuarioAsignable])
def asignables(_: Usuarios = Depends(requiere('casos.ver')), db: Session = Depends(get_db)):
    """Para el desplegable de responsable. No expone la gestión de usuarios."""
    return [esq.UsuarioAsignable(id=u.id, nombre=u.nombre, rol=u.rol.codigo)
            for u in servicio.listar(db) if u.activo]


@router.get('/roles', response_model=list[esq.RolSalida])
def roles(_: Usuarios = Depends(requiere('usuarios.ver')), db: Session = Depends(get_db)):
    return [esq.RolSalida(id=r.id, codigo=r.codigo, nombre=r.nombre, permisos=sorted(p))
            for r, p in servicio.listar_roles(db)]


@router.get('/permisos', response_model=list[esq.PermisoSalida])
def permisos(_: Usuarios = Depends(requiere('usuarios.ver')), db: Session = Depends(get_db)):
    """El catálogo completo de lo que se le puede dar a un rol.

    Lo pide la pantalla de permisos para armar las casillas con nombres en
    español. Verlo no es poder cambiarlo: para eso está el PUT de abajo.
    """
    return [esq.PermisoSalida(codigo=p.codigo, nombre=p.nombre, modulo=p.modulo)
            for p in servicio.catalogo_permisos(db)]


@router.put('/roles/{rol_id}/permisos', response_model=esq.RolSalida)
def fijar_permisos(rol_id: int, datos: esq.PermisosDeRol, request: Request,
                   actor: Usuarios = Depends(requiere('usuarios.permisos')),
                   db: Session = Depends(get_db)):
    """Cambia qué puede hacer un rol (RF-077).

    Pide `usuarios.permisos` y no `usuarios.editar`: cambiarle el perfil a una
    persona es escoger entre los que ya existen, y redefinir el perfil mismo es
    poder darse cualquier permiso del sistema. No es la misma facultad, y el día
    que la gestión de cuentas se delegue, esta no se va de regalo con ella.
    """
    rol, permisos = servicio.fijar_permisos(db, actor, rol_id, datos.permisos,
                                            ip=ip_cliente(request))
    return esq.RolSalida(id=rol.id, codigo=rol.codigo, nombre=rol.nombre,
                         permisos=sorted(permisos))
