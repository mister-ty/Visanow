from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import ajustes

# `hide_parameters=True` no es cosmetico: sin el, el mensaje de cualquier error
# de base trae `[SQL: ...]` y `[parameters: {...}]` con los VALORES de la fila, y
# como la aplicacion solo maneja sus propios errores de dominio, cualquier otra
# excepcion sube a Starlette, que imprime el traceback completo en el log. En
# Render ese log lo lee cualquiera que entre al panel y queda ahi. O sea que un
# texto demasiado largo en un campo -que es facil de provocar: los esquemas de
# EDITAR no traen los `max_length` que si traen los de CREAR- escribia en el log
# el nombre, el telefono o el pasaporte que venia en la peticion.
motor = create_engine(ajustes().database_url, pool_pre_ping=True, hide_parameters=True)
SesionLocal = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SesionLocal()
    try:
        yield db
    finally:
        db.close()
