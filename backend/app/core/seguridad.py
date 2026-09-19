"""Primitivas de seguridad: contraseñas, tokens y cifrado de datos sensibles.

Nada de esto sabe de la base de datos ni de FastAPI: son funciones puras que
usan los servicios.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import ajustes

_hasher = PasswordHasher()

# Hash de una contraseña que nadie tiene. Se verifica contra él cuando el correo
# no existe, para que responder «usuario inexistente» tarde lo mismo que
# responder «contraseña errada» y no se pueda averiguar quién tiene cuenta.
_HASH_SEÑUELO = _hasher.hash(secrets.token_urlsafe(32))


# ------------------------------------------------------------------ contraseñas

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password_hash: str | None, password: str) -> bool:
    """password_hash=None significa que el usuario no existe: se hace el mismo
    trabajo que con uno real, pero el resultado es siempre False."""
    try:
        coincide = _hasher.verify(password_hash or _HASH_SEÑUELO, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        coincide = False
    return coincide and password_hash is not None


def necesita_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validar_politica(password: str, email: str = '') -> list[str]:
    """Devuelve los incumplimientos; lista vacía si la contraseña sirve."""
    errores = []
    if len(password) < 10:
        errores.append('Debe tener al menos 10 caracteres.')
    if not any(c.isalpha() for c in password):
        errores.append('Debe incluir al menos una letra.')
    if not any(c.isdigit() for c in password):
        errores.append('Debe incluir al menos un número.')
    if email and email.split('@')[0].lower() in password.lower():
        errores.append('No puede contener el usuario del correo.')
    return errores


def password_temporal() -> str:
    """Contraseña de un solo uso para usuarios nuevos o restablecidos."""
    alfabeto = string.ascii_letters + string.digits
    while True:
        p = ''.join(secrets.choice(alfabeto) for _ in range(14))
        if not validar_politica(p):
            return p


# ----------------------------------------------------------------------- tokens

class TokenInvalido(Exception):
    pass


def crear_token(usuario_id: int, tipo: str, minutos: int, **extra) -> str:
    ahora = datetime.now(timezone.utc)
    carga = {'sub': str(usuario_id), 'tipo': tipo, 'iat': int(ahora.timestamp()),
             'exp': ahora + timedelta(minutes=minutos), 'jti': secrets.token_urlsafe(9), **extra}
    return jwt.encode(carga, ajustes().app_secret, algorithm=ajustes().jwt_algoritmo)


def leer_token(token: str, tipo: str) -> dict:
    """Decodifica y valida firma, expiración y tipo. Lanza TokenInvalido."""
    try:
        carga = jwt.decode(token, ajustes().app_secret, algorithms=[ajustes().jwt_algoritmo],
                           options={'require': ['sub', 'exp', 'iat', 'tipo']})
    except jwt.PyJWTError as e:
        raise TokenInvalido(str(e)) from e
    if carga.get('tipo') != tipo:
        raise TokenInvalido(f'Se esperaba un token de {tipo}')
    return carga


def huella_password(password_hash: str) -> str:
    """Resumen corto del hash vigente. Va dentro del token de recuperación:
    en cuanto la contraseña cambia, la huella deja de coincidir y el enlace
    muere. Así cada enlace sirve una sola vez sin guardar nada en la base."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------- cifrado

def _fernet() -> Fernet:
    llave = hashlib.sha256(ajustes().cifrado_llave.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(llave))


def cifrar(texto: str) -> str:
    """Cifrado en reposo (RNF-04): secretos de doble factor, pasaportes, DS-160."""
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(cifrado: str) -> str:
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except InvalidToken as e:
        raise ValueError('No se pudo descifrar: la llave no corresponde o el dato está dañado') from e


def indice_ciego(valor: str) -> str:
    """HMAC determinístico de un dato cifrado, para poder buscarlo (RF-029)
    sin descifrar la columna: el pasaporte se guarda cifrado y además se guarda
    este índice, que permite la búsqueda exacta pero no revela el valor."""
    normal = ''.join(valor.upper().split())
    llave = hashlib.sha256(('indice:' + ajustes().cifrado_llave).encode()).digest()
    return hmac.new(llave, normal.encode(), hashlib.sha256).hexdigest()
