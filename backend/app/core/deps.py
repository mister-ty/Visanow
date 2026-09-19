"""Dependencias de FastAPI: quién llama y qué puede hacer.

Tres niveles, de menos a más exigente:

- usuario_actual:    token válido, usuario activo y sesión no cerrada por cambio
                     de contraseña. Sirve para /auth/yo y para completar la
                     configuración de la cuenta.
- usuario_operativo: además, ya cambió la contraseña temporal y, si su rol lo
                     exige, ya activó el doble factor (RNF-02).
- requiere(...):     además, su rol tiene los permisos pedidos (RNF-03).

La UI puede esconder botones, pero el control de acceso vive aquí.
"""
import ipaddress

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import seguridad as seg
from app.core.errores import NoAutenticado, Prohibido
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.services.auth import version_credenciales
from app.services.usuarios import exige_mfa, permisos_de_rol

_bearer = HTTPBearer(auto_error=False)


def ip_cliente(request: Request) -> str | None:
    """La columna auditoria.ip es de tipo inet. Si lo que llega no es una IP
    (un socket, un proxy mal configurado, el cliente de pruebas), se guarda
    nulo: un dato de auditoría raro no puede tumbar el ingreso."""
    host = request.client.host if request.client else None
    try:
        # Sin el índice de zona de IPv6 ('fe80::1%eth0'): la columna inet no lo acepta
        return str(ipaddress.ip_address(host.split('%')[0])) if host else None
    except ValueError:
        return None


def usuario_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                   db: Session = Depends(get_db)) -> Usuarios:
    if cred is None:
        raise NoAutenticado('Falta el token de acceso.', codigo='sin_token')
    try:
        carga = seg.leer_token(cred.credentials, 'acceso')
    except seg.TokenInvalido:
        raise NoAutenticado('La sesión no es válida o ya venció.', codigo='token_invalido')
    u = db.get(Usuarios, int(carga['sub']))
    if u is None or not u.activo:
        raise NoAutenticado('La sesión no es válida o ya venció.', codigo='token_invalido')
    if carga.get('pv') != version_credenciales(u):
        raise NoAutenticado('La sesión se cerró porque la contraseña cambió.', codigo='sesion_cerrada')
    return u


def mfa_pendiente(db: Session, u: Usuarios) -> bool:
    return not u.mfa_habilitado and exige_mfa(db, u)


def usuario_operativo(u: Usuarios = Depends(usuario_actual),
                      db: Session = Depends(get_db)) -> Usuarios:
    if u.debe_cambiar_password:
        raise Prohibido('Debe cambiar la contraseña temporal antes de continuar.',
                        codigo='cambio_password_requerido')
    if mfa_pendiente(db, u):
        raise Prohibido('Su perfil exige doble factor. Actívelo antes de continuar.',
                        codigo='mfa_requerido')
    return u


def requiere(*permisos: str):
    """Uso: Depends(requiere('pagos.editar')). Exige todos los permisos listados."""
    def _dependencia(u: Usuarios = Depends(usuario_operativo),
                     db: Session = Depends(get_db)) -> Usuarios:
        faltan = set(permisos) - permisos_de_rol(db, u.rol_id)
        if faltan:
            raise Prohibido('No tiene permiso para esta acción.', codigo='sin_permiso')
        return u
    return _dependencia
