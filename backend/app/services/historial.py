"""Traduce el historial de un trámite al idioma de quien lo lee.

La tabla `casos_historial` guarda lo que pasó en los términos de la base de
datos: `estado: esperando_info → info_en_revision`, `sede_id: — → 2`. Eso sirve
para auditar, pero en pantalla no dice nada: nadie en VisaNow sabe qué es la
sede 2.

Aquí se resuelven los códigos y los identificadores contra los catálogos, en una
consulta por tabla y no una por fila. La traducción se hace en el servidor, que
es donde están los catálogos, para que la ficha del cliente y la del trámite
cuenten exactamente lo mismo.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.esquema import (CasosHistorial, ChecklistItems, EstadosOperativos, Modalidades,
                                Paises, Sedes, TiposVisa, Usuarios)

# Campo de la tabla -> (cómo se llama en español, de qué catálogo sale el id)
CAMPOS: dict[str, tuple[str, type | None]] = {
    'pais_id': ('País', Paises),
    'sede_id': ('Sede', Sedes),
    'tipo_visa_id': ('Tipo de visa', TiposVisa),
    'modalidad_id': ('Modalidad', Modalidades),
    'responsable_id': ('Responsable', Usuarios),
    'negocio_id': ('Venta asociada', None),
    'proxima_accion': ('Próxima acción', None),
    'proxima_accion_fecha': ('Fecha de la próxima acción', None),
}

TIPOS_CITA = {
    'cas': 'CAS (huellas y foto)', 'biometria': 'biometría', 'entrevista': 'entrevista',
    'radicacion': 'radicación', 'preparacion': 'preparación', 'entrega': 'entrega', 'otra': 'cita',
}

RESULTADOS = {
    'aprobada': 'Aprobada', 'negada': 'Negada', 'proceso_administrativo': 'En proceso administrativo',
    'cancelado': 'Cancelado', 'no_continuo': 'No continuó',
}


def _nombres(db: Session, filas: Iterable[CasosHistorial]) -> dict:
    """Una consulta por catálogo, con solo los ids que el historial menciona."""
    ids: dict[type, set[int]] = defaultdict(set)
    codigos_estado: set[str] = set()
    codigos_item: set[str] = set()

    for h in filas:
        if h.campo in ('estado', 'excepcion', 'creado'):
            codigos_estado.update(v for v in (h.valor_anterior, h.valor_nuevo) if v)
        elif h.campo.startswith('checklist:'):
            codigos_item.add(h.campo.split(':', 1)[1])
        else:
            modelo = CAMPOS.get(h.campo, (None, None))[1] or _modelo_de_cita(h.campo)
            if modelo is not None:
                ids[modelo].update(int(v) for v in (h.valor_anterior, h.valor_nuevo)
                                   if v and v.isdigit())

    catalogos = {modelo: {i: n for i, n in db.execute(
        select(modelo.id, modelo.nombre).where(modelo.id.in_(valores)))}
        for modelo, valores in ids.items() if valores}

    estados = {c: n for c, n in db.execute(
        select(EstadosOperativos.codigo, EstadosOperativos.nombre)
        .where(EstadosOperativos.codigo.in_(codigos_estado)))} if codigos_estado else {}

    items = {c: n for c, n in db.execute(
        select(ChecklistItems.codigo, ChecklistItems.nombre)
        .where(ChecklistItems.codigo.in_(codigos_item)))} if codigos_item else {}

    return {'catalogos': catalogos, 'estados': estados, 'items': items}


def _modelo_de_cita(campo: str) -> type | None:
    """`cita_entrevista_sede_id` también apunta a un catálogo."""
    if campo.startswith('cita_') and campo.endswith('_sede_id'):
        return Sedes
    return None


def _valor(nombres: dict, modelo: type | None, bruto: str | None) -> str:
    if bruto is None or bruto == '':
        return '—'
    if modelo is not None and bruto.isdigit():
        return nombres['catalogos'].get(modelo, {}).get(int(bruto), f'#{bruto}')
    return bruto


def describir(db: Session, filas: list[CasosHistorial]) -> list[str]:
    """Un título legible por cada fila, en el mismo orden que llegaron."""
    nombres = _nombres(db, filas)
    return [_titulo(h, nombres) for h in filas]


def _titulo(h: CasosHistorial, nombres: dict) -> str:
    estados, items = nombres['estados'], nombres['items']
    campo, antes, despues = h.campo, h.valor_anterior, h.valor_nuevo

    if campo == 'creado':
        return 'Trámite creado'

    if campo in ('estado', 'excepcion'):
        origen = estados.get(antes or '', antes or '—')
        destino = estados.get(despues or '', despues or '—')
        etiqueta = 'Excepción autorizada' if campo == 'excepcion' else 'Estado'
        return f'{etiqueta}: {origen} → {destino}'

    if campo == 'resultado':
        return f'Resultado: {RESULTADOS.get(despues or "", despues or "—")}'

    if campo.startswith('checklist:'):
        codigo = campo.split(':', 1)[1]
        estado = 'entregado' if despues == 'cumplido' else 'pendiente'
        return f'Documento «{items.get(codigo, codigo)}»: {estado}'

    if campo.startswith('cita_'):
        return _titulo_cita(campo, despues, nombres)

    etiqueta, modelo = CAMPOS.get(campo, (campo.replace('_', ' ').capitalize(), None))
    return f'{etiqueta}: {_valor(nombres, modelo, antes)} → {_valor(nombres, modelo, despues)}'


def _titulo_cita(campo: str, despues: str | None, nombres: dict) -> str:
    resto = campo.removeprefix('cita_')
    for tipo, legible in TIPOS_CITA.items():
        if resto == tipo:
            return f'Cita de {legible} agendada'
        if resto.startswith(f'{tipo}_'):
            detalle = resto.removeprefix(f'{tipo}_')
            if detalle == 'inicia_en':
                return f'Cita de {legible} reprogramada'
            if detalle == 'observaciones':
                return f'Cita de {legible}: nota'
            if detalle == 'estado':
                return f'Cita de {legible}: {despues or "—"}'
            if detalle == 'sede_id':
                return f'Cita de {legible}: sede {_valor(nombres, Sedes, despues)}'
            return f'Cita de {legible}: {detalle.replace("_", " ")}'
    return f'Cita: {resto.replace("_", " ")}'
