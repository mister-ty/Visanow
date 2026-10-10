"""Saldo, estado financiero y cartera (RF-042, RF-046).

Todo lo que hay aquí **lee**, no calcula. El saldo lo hace la vista
`v_estado_financiero` y el vencimiento la vista `v_cartera`, en la base de
datos. Si el saldo se calculara también en Python, habría dos fórmulas que
tarde o temprano dicen cosas distintas, que es justo el problema que tienen hoy
los archivos: la hoja PAGOS y la hoja REV PAGOS discrepan en 37 millones.

Por eso este módulo es corto a propósito. Lo largo ya está en el SQL.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

ESTADOS = ('sin_acuerdo', 'pendiente_anticipo', 'abono', 'pagado')


@dataclass
class EstadoFinanciero:
    negocio_id: int
    valor_pactado: float
    total_pagado: float
    neto_recibido: float
    ajustes: float
    saldo: float
    estado_financiero: str
    moneda: str


@dataclass
class FilaCartera:
    negocio_id: int
    cliente_id: int
    cliente: str
    servicio: str
    fecha_venta: dt.date
    vendedor: str | None
    valor_pactado: float
    total_pagado: float
    saldo: float
    exigible_hoy: float
    vencido: float
    por_vencer: float
    dias_vencido: int
    moneda: str


def estado_de(db: Session, negocio_id: int) -> EstadoFinanciero | None:
    fila = db.execute(text("""
        select negocio_id, valor_pactado, total_pagado, neto_recibido, ajustes,
               saldo, estado_financiero, moneda
          from v_estado_financiero where negocio_id = :n"""), {'n': negocio_id}).first()
    if fila is None:
        return None
    return EstadoFinanciero(
        negocio_id=fila[0], valor_pactado=float(fila[1] or 0), total_pagado=float(fila[2] or 0),
        neto_recibido=float(fila[3] or 0), ajustes=float(fila[4] or 0), saldo=float(fila[5] or 0),
        estado_financiero=fila[6], moneda=fila[7])


def cartera(db: Session, *, solo_vencida: bool = False, vendedor_id: int | None = None,
            cliente_id: int | None = None, desde_dias: int | None = None,
            pagina: int = 1, tamano: int = 50) -> tuple[int, float, list[FilaCartera]]:
    """Quién debe, cuánto y desde cuándo (RF-046).

    `dias_vencido` se cuenta desde la cuota más antigua que ya era exigible: es
    la antigüedad que pide el requerimiento y la que decide a quién se llama
    primero.
    """
    filtros = ['c.saldo > 0']
    parametros: dict = {}
    if solo_vencida:
        filtros.append('c.vencido > 0')
    if vendedor_id:
        filtros.append('n.vendedor_id = :vendedor')
        parametros['vendedor'] = vendedor_id
    if cliente_id:
        filtros.append('n.cliente_id = :cliente')
        parametros['cliente'] = cliente_id
    if desde_dias:
        filtros.append('c.dias_mora >= :dias')
        parametros['dias'] = desde_dias
    donde = ' and '.join(filtros)

    base = f"""
        from v_cartera c
        join negocios n on n.id = c.negocio_id
        join clientes cl on cl.id = n.cliente_id
        join servicios s on s.id = n.servicio_id
        left join usuarios u on u.id = n.vendedor_id
       where {donde}"""

    total, suma = db.execute(
        text(f'select count(*), coalesce(sum(c.saldo), 0) {base}'), parametros).first()

    # `dias_mora` lo calcula la propia vista: rehacer la cuenta aquí sería tener
    # dos fórmulas que tarde o temprano dicen cosas distintas.
    filas = db.execute(text(f"""
        select c.negocio_id, n.cliente_id, cl.nombre, s.nombre, n.fecha_venta, u.nombre,
               c.valor_pactado, c.total_pagado, c.saldo, c.exigible_hoy, c.vencido,
               c.por_vencer, c.dias_mora, c.moneda
        {base}
        order by c.dias_mora desc, c.vencido desc, c.negocio_id
        limit :tamano offset :salto"""),
        parametros | {'tamano': tamano, 'salto': (pagina - 1) * tamano}).all()

    return int(total), float(suma), [
        FilaCartera(
            negocio_id=f[0], cliente_id=f[1], cliente=f[2], servicio=f[3], fecha_venta=f[4],
            vendedor=f[5], valor_pactado=float(f[6] or 0), total_pagado=float(f[7] or 0),
            saldo=float(f[8] or 0), exigible_hoy=float(f[9] or 0), vencido=float(f[10] or 0),
            por_vencer=float(f[11] or 0), dias_vencido=int(f[12] or 0),
            moneda=f[13]) for f in filas]


def resumen(db: Session) -> dict:
    """Los cuatro números que se miran de un vistazo."""
    fila = db.execute(text("""
        select coalesce(sum(valor_pactado), 0), coalesce(sum(total_pagado), 0),
               coalesce(sum(saldo), 0), coalesce(sum(vencido), 0),
               count(*) filter (where saldo > 0)
          from v_cartera""")).first()
    return {'vendido': float(fila[0]), 'cobrado': float(fila[1]), 'cartera': float(fila[2]),
            'vencido': float(fila[3]), 'ventas_con_saldo': int(fila[4])}


def por_estado(db: Session) -> list[tuple[str, int, float]]:
    return [(e, int(n), float(s)) for e, n, s in db.execute(text("""
        select estado_financiero, count(*), coalesce(sum(saldo), 0)
          from v_estado_financiero group by 1 order by 2 desc"""))]
