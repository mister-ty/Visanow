"""Exportación de las listas grandes con registro de quién se llevó qué (RF-075, RNF-07).

Una lista exportada sale del sistema y ya no se puede controlar: por eso cada
descarga queda en `auditoria` con quién fue, qué lista, con qué filtros y
cuántas filas. Eso es lo que permite contestar, si un listado de clientes
aparece donde no debe, de quién fue la descarga.

El permiso es `<módulo>.exportar`, distinto de `.ver`: poder mirar una pantalla
no autoriza a llevarse toda la lista. Los datos salen de los mismos servicios que
alimentan las pantallas, así que el alcance y los filtros son los de siempre y
no hay una segunda consulta que se pueda desalinear de la primera.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.errores import Invalido, Prohibido
from app.models.esquema import Usuarios
from app.services import cartera as serv_cartera
from app.services import casos as serv_casos
from app.services import comisiones as serv_comisiones
from app.services import personas
from app.services.auditoria import auditar
from app.services.tableros import Indicador, Tabla, Tablero, a_csv, a_xlsx
from app.services.usuarios import permisos_de_rol

BOGOTA = ZoneInfo('America/Bogota')
# Tope de seguridad: una exportación sin límite es una forma de vaciar la base.
MAX_FILAS = 50_000
# Lo que admite de una vez el servicio más estricto (clientes recorta a 100)
LOTE = 100


@dataclass
class Lista:
    titulo: str
    permiso: str
    # Quién solo ve lo suyo no se puede llevar la lista de toda la agencia. Los
    # trámites ya se limitan por alcance dentro del servicio; las demás no.
    exige_alcance_total: bool
    construir: Callable[[Session, Usuarios, dict], tuple[list[str], list[list]]]


def _texto(v):
    """Neutraliza las fórmulas: un nombre que empiece por «=» no debe ejecutarse al abrirse en Excel."""
    if isinstance(v, str) and v[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + v
    return v


def _hora(v: dt.datetime | None) -> str | None:
    """Los instantes se guardan con zona; el negocio los lee en hora de Bogotá."""
    return v.astimezone(BOGOTA).strftime('%Y-%m-%d %H:%M') if v else None


def _lotes(pedir: Callable[[int], list]) -> list:
    """Recorre las páginas del servicio hasta agotarlas o llegar al tope."""
    todo: list = []
    pagina = 1
    while True:
        lote = pedir(pagina)
        todo.extend(lote)
        if len(todo) > MAX_FILAS:
            raise Invalido(f'La lista supera {MAX_FILAS} filas: acote el filtro e intente de nuevo.',
                           codigo='exportacion_muy_grande')
        if len(lote) < LOTE:
            return todo
        pagina += 1


def _clientes(db: Session, actor: Usuarios, f: dict):
    filas = _lotes(lambda p: personas.listar(
        db, texto_busqueda=f.get('texto'), incluir_archivados=bool(f.get('archivados')),
        pagina=p, tamano=LOTE)[1])
    cols = ['Nombre', 'Tipo de documento', 'Número de documento', 'Teléfono', 'Correo', 'Ciudad',
            'Archivado', 'Creado']
    return cols, [[c.nombre, c.tipo_documento, c.numero_documento, c.telefono, c.email, c.ciudad,
                   'Sí' if c.archivado else 'No', _hora(c.creado_en)] for c in filas]


def _casos(db: Session, actor: Usuarios, f: dict):
    # `actor` va al servicio: es lo que aplica el alcance (RNF-03).
    filas = _lotes(lambda p: serv_casos.listar(
        db, actor=actor, estado=f.get('estado'), responsable_id=f.get('responsable_id'),
        pais_id=f.get('pais_id'), texto=f.get('texto'), sin_asignar=bool(f.get('sin_asignar')),
        incluir_finalizados=bool(f.get('incluir_finalizados')), pagina=p, tamano=LOTE)[1])
    cols = ['Trámite', 'Solicitante', 'País', 'Estado', 'Responsable', 'Fuente', 'N° solicitud SaaS',
            'Última actividad', 'Creado']
    return cols, [[c.id, c.solicitante.nombre if c.solicitante else None,
                   c.pais.nombre if c.pais else None, c.estado.nombre if c.estado else None,
                   c.responsable.nombre if c.responsable else None, c.fuente, c.id_externo,
                   _hora(c.ultima_actividad_en), _hora(c.creado_en)] for c in filas]


def _cartera(db: Session, actor: Usuarios, f: dict):
    filas = _lotes(lambda p: serv_cartera.cartera(
        db, solo_vencida=bool(f.get('solo_vencida')), vendedor_id=f.get('vendedor_id'),
        desde_dias=f.get('desde_dias'), pagina=p, tamano=LOTE)[2])
    cols = ['Venta', 'Cliente', 'Servicio', 'Fecha de venta', 'Vendedor', 'Pactado', 'Pagado', 'Saldo',
            'Vencido', 'Por vencer', 'Días de mora', 'Moneda']
    return cols, [[x.negocio_id, x.cliente, x.servicio, x.fecha_venta.isoformat() if x.fecha_venta else None,
                   x.vendedor, x.valor_pactado, x.total_pagado, x.saldo, x.vencido, x.por_vencer,
                   x.dias_vencido, x.moneda] for x in filas]


def _comisiones(db: Session, actor: Usuarios, f: dict):
    filas = serv_comisiones.comisiones_de(
        db, vendedor_id=f.get('vendedor_id'), periodo=f.get('periodo'), estado=f.get('estado'))
    if len(filas) > MAX_FILAS:
        raise Invalido(f'La lista supera {MAX_FILAS} filas: acote el filtro e intente de nuevo.',
                       codigo='exportacion_muy_grande')
    cols = ['Comisión', 'Venta', 'Vendedor', 'Periodo', 'Base de cálculo', 'Porcentaje', 'Escalón', 'Monto',
            'Estado', 'Explicación']
    out = []
    for c in filas:
        regla = c.regla_aplicada or {}   # la regla congelada al calcular (RN-07)
        out.append([c.id, c.negocio_id, c.vendedor.nombre if c.vendedor else None,
                    c.periodo.isoformat() if c.periodo else None, float(c.base_calculo),
                    regla.get('porcentaje_aplicado'), regla.get('escalon'), float(c.monto), c.estado,
                    regla.get('explicacion')])
    return cols, out


LISTAS: dict[str, Lista] = {
    'clientes': Lista('Clientes', 'clientes.exportar', True, _clientes),
    'casos': Lista('Trámites', 'casos.exportar', False, _casos),
    'cartera': Lista('Cartera', 'pagos.exportar', True, _cartera),
    'comisiones': Lista('Comisiones', 'comisiones.exportar', True, _comisiones),
}


def exportar(db: Session, actor: Usuarios, nombre: str, formato: str, filtros: dict,
             ip: str | None = None) -> tuple[bytes, int]:
    """Genera el archivo y deja el registro en la misma transacción.

    El registro se escribe después de construir los datos y se confirma aquí: si
    algo falla antes, no queda constancia de una descarga que no ocurrió; si el
    registro no se puede escribir, la descarga tampoco sale.
    """
    lista = LISTAS.get(nombre)
    if lista is None:
        raise Invalido('Esa lista no se puede exportar.', codigo='lista_desconocida')
    if lista.permiso not in permisos_de_rol(db, actor.rol_id):
        raise Prohibido('No tiene permiso para exportar esta lista.', codigo='sin_permiso')
    if lista.exige_alcance_total and actor.alcance != 'todos':
        raise Prohibido('Esta lista abarca toda la agencia y su alcance no la incluye.',
                        codigo='sin_alcance')

    columnas, filas = lista.construir(db, actor, filtros)
    filas = [[_texto(v) for v in fila] for fila in filas]
    tabla = Tablero(tablero=nombre, titulo=lista.titulo,
                    indicadores=[Indicador('filas', 'Filas exportadas', len(filas))],
                    tablas=[Tabla(nombre, lista.titulo, columnas, filas)])
    cuerpo = a_csv(tabla) if formato == 'csv' else a_xlsx(tabla)

    registrar(db, actor, nombre, formato, filtros, len(filas), ip)
    db.commit()
    return cuerpo, len(filas)


def registrar(db: Session, actor: Usuarios, lista: str, formato: str, filtros: dict,
              filas: int, ip: str | None = None) -> None:
    """Una línea de auditoría por descarga: quién, qué, con qué filtros y cuántas filas.

    Se guardan los filtros y el conteo, nunca el contenido: la auditoría no puede
    convertirse en una segunda copia de los datos que protege.
    """
    auditar(db, operacion='exportar', entidad=f'exportacion:{lista}'[:40], usuario_id=actor.id,
            despues={'lista': lista, 'formato': formato, 'filas': filas,
                     'filtros': {k: v for k, v in filtros.items() if v not in (None, '', False)}},
            ip=ip)
