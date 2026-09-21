"""Los modelos se generan desde la base (esquema.py, no se edita a mano).

Aquí solo se les da una representación legible: sin esto, los desplegables de la
administración muestran «<Paises object at 0x...>» en vez de «Colombia».
"""
from app.models.esquema import Base


def _texto(self) -> str:
    for campo in ('nombre', 'codigo', 'clave', 'banco'):
        valor = getattr(self, campo, None)
        if valor:
            return str(valor)
    return f'#{getattr(self, "id", "?")}'


Base.__str__ = _texto
