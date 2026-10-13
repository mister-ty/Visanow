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


class UsuarioAsignable(BaseModel):
    id: int
    nombre: str
    rol: str


class RolSalida(BaseModel):
    id: int
    codigo: str
    nombre: str
    permisos: list[str]


class PermisoSalida(BaseModel):
    """Una casilla de la pantalla de permisos. `modulo` es lo que la agrupa."""
    codigo: str
    nombre: str
    modulo: str


class PermisosDeRol(BaseModel):
    """Lo que el rol queda pudiendo hacer: la lista COMPLETA, no lo que se agrega.

    Lo que no venga se le quita. Se guarda así, y no cambio por cambio, porque
    la pantalla es una matriz de casillas y lo que manda es lo que quedó
    marcado: dos personas ajustando a la vez no terminan con una matriz mitad y
    mitad que nadie decidió.
    """
    permisos: list[str] = Field(max_length=300, description='Códigos de permiso, como «casos.ver»')
