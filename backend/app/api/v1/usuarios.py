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


@router.post('/usuarios/{usuario_id}/reiniciar-mfa', status_code=status.HTTP_204_NO_CONTENT)
def reiniciar_mfa(usuario_id: int, request: Request,
                  actor: Usuarios = Depends(requiere('usuarios.editar')),
                  db: Session = Depends(get_db)):
    servicio.reiniciar_mfa(db, actor, usuario_id, ip=ip_cliente(request))


@router.get('/roles', response_model=list[esq.RolSalida])
def roles(_: Usuarios = Depends(requiere('usuarios.ver')), db: Session = Depends(get_db)):
    return [esq.RolSalida(codigo=r.codigo, nombre=r.nombre, permisos=sorted(p))
            for r, p in servicio.listar_roles(db)]
