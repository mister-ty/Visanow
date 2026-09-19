from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Alcance = Literal['todos', 'asignados', 'propios']


class UsuarioSalida(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str
    alcance: str
    activo: bool
    mfa_habilitado: bool
    debe_cambiar_password: bool
    bloqueado: bool
    ultimo_acceso: datetime | None
    creado_en: datetime


class UsuarioCrear(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    email: EmailStr
    rol: str
    alcance: Alcance = 'todos'


class UsuarioEditar(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    rol: str | None = None
    activo: bool | None = None
    alcance: Alcance | None = None


class PasswordTemporalSalida(BaseModel):
    usuario: UsuarioSalida
    password_temporal: str = Field(description='Se muestra una sola vez. Entregarla por un canal seguro.')


class RolSalida(BaseModel):
    codigo: str
    nombre: str
    permisos: list[str]
