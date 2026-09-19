"""Errores de negocio. Los servicios los lanzan; main.py los traduce a HTTP.

Así un servicio no importa nada de FastAPI y se puede usar igual desde la API,
la importación del SaaS o la migración.
"""


class ErrorDominio(Exception):
    http = 400

    def __init__(self, mensaje: str, codigo: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo or self.__class__.__name__.lower()


class NoAutenticado(ErrorDominio):
    http = 401


class Prohibido(ErrorDominio):
    http = 403


class NoEncontrado(ErrorDominio):
    http = 404


class Conflicto(ErrorDominio):
    http = 409


class Invalido(ErrorDominio):
    http = 422


class Bloqueado(ErrorDominio):
    http = 423
