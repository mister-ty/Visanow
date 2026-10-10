"""Registro de auditoría (RNF-05, RN-08).

La tabla es inalterable a nivel de base de datos (migración 0002): aquí solo se
inserta. Los secretos nunca entran a la auditoría, ni cifrados, y los datos que
identifican a una persona entran como «cambió este campo», sin el valor: la
auditoría no puede ser la copia de la base que sobrevive a una anonimización.
"""
from __future__ import annotations

import datetime as dt
import decimal
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.esquema import Auditoria

NUNCA_AUDITAR = {'password_hash', 'mfa_secreto'}

# Estos campos SI se registran -saber que cambio el telefono de un cliente es
# justamente para lo que sirve una auditoria- pero sin repetir el valor.
#
# El motivo es RNF-09. Anonimizar a una persona le quita el nombre, el documento
# y el pasaporte de sus tablas; si la auditoria guarda el registro completo de
# cuando se creo, el nombre sigue ahi y la anonimizacion no anonimizo nada. Y la
# auditoria es inalterable a proposito (RNF-05), asi que no se puede limpiar
# despues: o no entra, o se queda para siempre.
#
# Va por ENTIDAD y no por nombre de campo: `nombre` en `clientes` es una persona,
# pero en `servicios`, `roles` o `alertas_tipos` es una etiqueta del catalogo, y
# ocultarla dejaria sin poder leer quien renombro que. El indice ciego del
# pasaporte tambien entra: no guarda el dato, pero deja confirmar que una persona
# estuvo, y eso tambien identifica.
#
# Lo que se pierde es el valor anterior de un campo personal. Lo que se conserva
# -quien, cuando, sobre que registro y que campo- es lo que se mira el dia que
# hay que responder por un cambio. El valor actual esta en la tabla, que es
# donde tiene que estar.
DATOS_PERSONALES: dict[str, set[str]] = {
    'clientes': {'nombre', 'nombre_busqueda', 'numero_documento', 'telefono',
                 'telefono_normalizado', 'email', 'observaciones'},
    'solicitantes': {'nombre', 'nombre_busqueda', 'numero_documento', 'pasaporte',
                     'pasaporte_indice', 'fecha_nacimiento', 'telefono',
                     'telefono_normalizado', 'email', 'observaciones'},
    'casos': {'ds160_numero_cifrado', 'ds160_hash', 'resultado_nota'},
    'usuarios': {'nombre', 'email'},
    # El nombre de un grupo es el apellido de una familia.
    'grupos': {'nombre', 'observaciones'},
}
OCULTO = '«dato personal»'


def sin_datos_personales(entidad: str, d: dict | None) -> dict | None:
    """Deja constancia de que el campo cambio, sin volver a escribir el dato."""
    campos = DATOS_PERSONALES.get(entidad)
    if not d or not campos:
        return d
    return {k: (OCULTO if k in campos and v is not None else v) for k, v in d.items()}


def _a_json(valor: Any) -> Any:
    """Deja el valor como algo que la columna jsonb pueda guardar."""
    if isinstance(valor, (dt.datetime, dt.date, dt.time)):
        return valor.isoformat()
    if isinstance(valor, decimal.Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {k: _a_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_a_json(v) for v in valor]
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def instantanea(objeto) -> dict:
    """Estado de un modelo como dict serializable, sin campos secretos."""
    return {c.key: _a_json(getattr(objeto, c.key))
            for c in inspect(objeto).mapper.column_attrs if c.key not in NUNCA_AUDITAR}


def auditar(db: Session, *, operacion: str, entidad: str, usuario_id: int | None = None,
            entidad_id: int | None = None, antes: dict | None = None,
            despues: dict | None = None, ip: str | None = None) -> None:
    """Agrega el registro a la sesión. Lo confirma el commit del servicio que
    llama, para que la auditoría y el cambio auditado queden en la misma
    transacción: o quedan los dos o ninguno."""
    # Se limpia aquí y no en cada servicio: un servicio que pase un datetime
    # crudo rompía la petición entera con un 500, porque la columna es jsonb.
    # Registrar la auditoría no puede ser lo que tumbe la operación que audita.
    antes = _a_json(antes) if antes else antes
    despues = _a_json(despues) if despues else despues
    if antes and despues:
        # Solo lo que cambió: el registro se lee de un vistazo
        claves = {k for k in antes.keys() | despues.keys() if antes.get(k) != despues.get(k)}
        antes = {k: antes.get(k) for k in claves}
        despues = {k: despues.get(k) for k in claves}
    db.add(Auditoria(usuario_id=usuario_id, operacion=operacion[:15], entidad=entidad[:40],
                     entidad_id=entidad_id,
                     antes=sin_datos_personales(entidad, antes),
                     despues=sin_datos_personales(entidad, despues), ip=ip))
