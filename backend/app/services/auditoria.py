"""Registro de auditoría (RNF-05, RN-08).

La tabla es inalterable a nivel de base de datos (migración 0002): aquí solo se
inserta. Los secretos nunca entran a la auditoría, ni cifrados.
"""
from __future__ import annotations

import datetime as dt
import decimal
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.esquema import Auditoria

NUNCA_AUDITAR = {'password_hash', 'mfa_secreto'}


def _a_json(valor: Any) -> Any:
    if isinstance(valor, (dt.datetime, dt.date)):
        return valor.isoformat()
    if isinstance(valor, decimal.Decimal):
        return str(valor)
    return valor


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
    if antes and despues:
        # Solo lo que cambió: el registro se lee de un vistazo
        claves = {k for k in antes.keys() | despues.keys() if antes.get(k) != despues.get(k)}
        antes = {k: antes.get(k) for k in claves}
        despues = {k: despues.get(k) for k in claves}
    db.add(Auditoria(usuario_id=usuario_id, operacion=operacion[:15], entidad=entidad[:40],
                     entidad_id=entidad_id, antes=antes, despues=despues, ip=ip))
