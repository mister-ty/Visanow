from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

CodigoTotp = Field(pattern=r'^\d{6}$', description='Código de 6 dígitos de la aplicación autenticadora')


class LoginEntrada(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenSalida(BaseModel):
    access_token: str
    token_type: Literal['bearer'] = 'bearer'
    expira_en_segundos: int


class DesafioMfa(BaseModel):
    requiere_mfa: Literal[True] = True
    token_mfa: str


class SegundoFactorEntrada(BaseModel):
    token_mfa: str
    codigo: str = CodigoTotp


class CodigoEntrada(BaseModel):
    codigo: str = CodigoTotp


class MfaInicioSalida(BaseModel):
    secreto: str = Field(description='Para escribirlo a mano si no se puede escanear el QR')
    uri: str = Field(description='otpauth:// para generar el código QR')


class CambioPasswordEntrada(BaseModel):
    actual: str = Field(min_length=1, max_length=200)
    nueva: str = Field(min_length=1, max_length=200)


class RecuperarEntrada(BaseModel):
    email: EmailStr


class RestablecerEntrada(BaseModel):
    token: str
    nueva: str = Field(min_length=1, max_length=200)


class YoSalida(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str
    alcance: str
    permisos: list[str]
    mfa_habilitado: bool
    debe_cambiar_password: bool
    mfa_requerido: bool = Field(description='Su rol exige doble factor y aún no lo activa')
    ultimo_acceso: datetime | None
