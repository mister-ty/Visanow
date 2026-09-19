"""Autenticación: ingreso, doble factor, contraseñas y recuperación (RF-025 PDF, RNF-02)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import seguridad as seg
from app.core.config import ajustes
from app.core.errores import Bloqueado, Invalido, NoAutenticado
from app.models.esquema import Usuarios
from app.services import notificaciones
from app.services.auditoria import auditar


MINUTOS_TOKEN_MFA = 5
MINUTOS_TOKEN_RECUPERACION = 30
EMISOR_TOTP = 'VisaNow'


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _credenciales_invalidas() -> NoAutenticado:
    """Una sola respuesta para correo inexistente, contraseña errada, cuenta
    inactiva y cuenta bloqueada: ninguna revela si el correo tiene cuenta."""
    a = ajustes()
    return NoAutenticado(f'Correo o contraseña incorrectos. Por seguridad, tras {a.login_max_intentos} '
                         f'intentos fallidos la cuenta se bloquea {a.login_bloqueo_minutos} minutos.',
                         codigo='credenciales_invalidas')


def version_credenciales(u: Usuarios) -> str:
    """Viaja dentro del token. Cambia cuando cambia la contraseña o cuando se
    activa o reinicia el doble factor: en cualquiera de esos casos todas las
    sesiones anteriores quedan cerradas. Así un token obtenido solo con
    contraseña no gana acceso pleno cuando después se activa el doble factor."""
    return seg.huella_password(u.password_hash + ('|mfa' if u.mfa_habilitado else ''))[:8]


# ----------------------------------------------------------------- ingreso

def _registrar_fallo(db: Session, u: Usuarios, ip: str | None, motivo: str) -> None:
    u.intentos_fallidos += 1
    bloqueo = u.intentos_fallidos >= ajustes().login_max_intentos
    if bloqueo:
        u.bloqueado_hasta = _ahora() + timedelta(minutes=ajustes().login_bloqueo_minutos)
        u.intentos_fallidos = 0
    auditar(db, operacion='bloqueo' if bloqueo else 'login_fallido', entidad='usuarios',
            usuario_id=u.id, entidad_id=u.id, despues={'motivo': motivo}, ip=ip)
    db.commit()


def _verificar_no_bloqueado(u: Usuarios) -> None:
    if u.bloqueado_hasta and u.bloqueado_hasta > _ahora():
        minutos = int((u.bloqueado_hasta - _ahora()).total_seconds() // 60) + 1
        raise Bloqueado(f'Cuenta bloqueada por intentos fallidos. Intente de nuevo en {minutos} min.',
                        codigo='cuenta_bloqueada')


def autenticar(db: Session, email: str, password: str, ip: str | None) -> Usuarios:
    """Valida correo y contraseña. No distingue «no existe» de «contraseña
    errada»: ni en el mensaje ni en el tiempo de respuesta."""
    # FOR UPDATE: los intentos simultáneos sobre la misma cuenta se atienden de a
    # uno. Sin esto, varias solicitudes leían el mismo contador y lo escribían
    # con el mismo valor, y el límite de intentos se podía pasar muchas veces.
    u = db.scalar(select(Usuarios).where(Usuarios.email == email).with_for_update())
    if u is None:
        seg.verificar_password(None, password)
        auditar(db, operacion='login_fallido', entidad='usuarios',
                despues={'motivo': 'correo_inexistente', 'email': email}, ip=ip)
        db.commit()
        raise _credenciales_invalidas()

    if u.bloqueado_hasta and u.bloqueado_hasta > _ahora():
        auditar(db, operacion='login_bloqueado', entidad='usuarios', usuario_id=u.id,
                entidad_id=u.id, ip=ip)
        db.commit()
        raise _credenciales_invalidas()
    if not seg.verificar_password(u.password_hash, password):
        _registrar_fallo(db, u, ip, 'password')
        raise _credenciales_invalidas()
    if not u.activo:
        auditar(db, operacion='login_fallido', entidad='usuarios', usuario_id=u.id,
                entidad_id=u.id, despues={'motivo': 'inactivo'}, ip=ip)
        db.commit()
        raise _credenciales_invalidas()

    if seg.necesita_rehash(u.password_hash):
        u.password_hash = seg.hash_password(password)
    if u.mfa_habilitado:
        db.commit()           # el ingreso se completa en verificar_segundo_factor
    else:
        _ingreso_exitoso(db, u, ip)
    return u


def _ingreso_exitoso(db: Session, u: Usuarios, ip: str | None) -> None:
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None
    u.ultimo_acceso = _ahora()
    auditar(db, operacion='login', entidad='usuarios', usuario_id=u.id, entidad_id=u.id, ip=ip)
    db.commit()


def emitir_acceso(u: Usuarios) -> dict:
    minutos = ajustes().jwt_expira_minutos
    token = seg.crear_token(u.id, 'acceso', minutos, pv=version_credenciales(u))
    return {'access_token': token, 'token_type': 'bearer', 'expira_en_segundos': minutos * 60}


def emitir_desafio_mfa(u: Usuarios) -> dict:
    return {'requiere_mfa': True,
            'token_mfa': seg.crear_token(u.id, 'mfa', MINUTOS_TOKEN_MFA, pv=version_credenciales(u))}


# ---------------------------------------------------------- doble factor

def _totp(u: Usuarios) -> pyotp.TOTP:
    return pyotp.TOTP(seg.descifrar(u.mfa_secreto))


def iniciar_mfa(db: Session, u: Usuarios) -> dict:
    """Genera un secreto nuevo y lo guarda cifrado. No queda activo hasta que
    el usuario demuestre que lo configuró en su aplicación (confirmar_mfa)."""
    if u.mfa_habilitado:
        raise Invalido('El doble factor ya está activo. Pida a la administradora que lo reinicie.',
                       codigo='mfa_ya_activo')
    secreto = pyotp.random_base32()
    u.mfa_secreto = seg.cifrar(secreto)
    db.commit()
    return {'secreto': secreto,
            'uri': pyotp.TOTP(secreto).provisioning_uri(name=u.email, issuer_name=EMISOR_TOTP)}


def confirmar_mfa(db: Session, u: Usuarios, codigo: str, ip: str | None) -> None:
    if not u.mfa_secreto:
        raise Invalido('Primero hay que iniciar la activación del doble factor.', codigo='mfa_sin_iniciar')
    if not _totp(u).verify(codigo, valid_window=1):
        raise Invalido('El código no coincide. Revise la hora del teléfono e intente de nuevo.',
                       codigo='codigo_invalido')
    u.mfa_habilitado = True
    auditar(db, operacion='mfa_activado', entidad='usuarios', usuario_id=u.id, entidad_id=u.id, ip=ip)
    db.commit()


def verificar_segundo_factor(db: Session, token_mfa: str, codigo: str, ip: str | None) -> Usuarios:
    try:
        carga = seg.leer_token(token_mfa, 'mfa')
    except seg.TokenInvalido:
        raise NoAutenticado('El paso de verificación venció. Ingrese de nuevo.', codigo='token_mfa_invalido')
    u = db.get(Usuarios, int(carga['sub']), with_for_update=True)
    if u is None or not u.activo or not u.mfa_habilitado or carga.get('pv') != version_credenciales(u):
        raise NoAutenticado('El paso de verificación venció. Ingrese de nuevo.', codigo='token_mfa_invalido')
    _verificar_no_bloqueado(u)
    if not _totp(u).verify(codigo, valid_window=1):
        _registrar_fallo(db, u, ip, 'codigo_mfa')
        raise NoAutenticado('Código de verificación incorrecto.', codigo='codigo_invalido')
    _ingreso_exitoso(db, u, ip)
    return u


# ------------------------------------------------------------- contraseñas

def _fijar_password(u: Usuarios, nueva: str) -> None:
    errores = seg.validar_politica(nueva, u.email)
    if errores:
        raise Invalido(' '.join(errores), codigo='password_debil')
    if seg.verificar_password(u.password_hash, nueva):
        raise Invalido('La contraseña nueva debe ser distinta de la actual.', codigo='password_repetida')
    u.password_hash = seg.hash_password(nueva)
    u.password_cambiado_en = _ahora()
    u.intentos_fallidos = 0
    u.bloqueado_hasta = None


def cambiar_password(db: Session, u: Usuarios, actual: str, nueva: str, ip: str | None) -> None:
    """Cierra todas las sesiones, incluida la que hace el cambio: hay que volver
    a ingresar (con doble factor si aplica). Si devolviera un token nuevo, quien
    robara un token podría renovarlo indefinidamente sin pasar el doble factor.

    La contraseña actual cuenta para el mismo límite de intentos del ingreso:
    si no, un token robado permitiría adivinarla sin límite."""
    db.refresh(u, with_for_update=True)
    _verificar_no_bloqueado(u)
    if not seg.verificar_password(u.password_hash, actual):
        _registrar_fallo(db, u, ip, 'password_actual')
        raise Invalido('La contraseña actual no es correcta.', codigo='password_actual_errada')
    _fijar_password(u, nueva)
    u.debe_cambiar_password = False
    auditar(db, operacion='password_cambio', entidad='usuarios', usuario_id=u.id, entidad_id=u.id, ip=ip)
    db.commit()


def solicitar_recuperacion(db: Session, email: str, ip: str | None) -> None:
    """Responde igual exista o no el correo: no revela quién tiene cuenta."""
    u = db.scalar(select(Usuarios).where(Usuarios.email == email))
    if u is None or not u.activo:
        # El mismo INSERT y COMMIT que el caso real, para no delatarse por el tiempo
        auditar(db, operacion='recuperacion', entidad='usuarios',
                despues={'email': email, 'resultado': 'sin_cuenta_activa'}, ip=ip)
        db.commit()
        return
    token = seg.crear_token(u.id, 'recuperacion', MINUTOS_TOKEN_RECUPERACION,
                            pwf=seg.huella_password(u.password_hash))
    auditar(db, operacion='recuperacion', entidad='usuarios', usuario_id=u.id, entidad_id=u.id, ip=ip)
    db.commit()
    notificaciones.enviar_recuperacion(u.email, token)


def restablecer_password(db: Session, token: str, nueva: str, ip: str | None) -> None:
    try:
        carga = seg.leer_token(token, 'recuperacion')
    except seg.TokenInvalido:
        raise Invalido('El enlace de recuperación no es válido o ya venció.', codigo='enlace_invalido')
    u = db.get(Usuarios, int(carga['sub']))
    # La huella deja de coincidir en cuanto la contraseña cambia: el enlace sirve una sola vez
    if u is None or not u.activo or carga.get('pwf') != seg.huella_password(u.password_hash):
        raise Invalido('El enlace de recuperación no es válido o ya venció.', codigo='enlace_invalido')
    _fijar_password(u, nueva)
    u.debe_cambiar_password = False
    auditar(db, operacion='password_reset', entidad='usuarios', usuario_id=u.id, entidad_id=u.id, ip=ip)
    db.commit()
