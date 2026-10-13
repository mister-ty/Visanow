"""Saldo, estado financiero y cartera (RF-042, RF-046).

Todo lo que hay aquí **lee**, no calcula. El saldo lo hace la vista
`v_estado_financiero` y el vencimiento la vista `v_cartera`, en la base de
datos. Si el saldo se calculara también en Python, habría dos fórmulas que
tarde o temprano dicen cosas distintas, que es justo el problema que tienen hoy
los archivos: la hoja PAGOS y la hoja REV PAGOS discrepan en 37 millones.

Por eso este módulo es corto a propósito. Lo largo ya está en el SQL. Lo mismo
vale para el corte por edades: en qué tramo cae cada deuda lo dice la vista, y
acá solo se agrupa y se le pone nombre.

La cartera se contesta de tres maneras —los totales, el corte por edades y la
lista de deudores— y las tres aceptan los mismos filtros. Esa es la razón de
`_filtros`: si cada respuesta filtrara a su manera, la pantalla mostraría un
total que no cuadra con la tabla que tiene debajo.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

ESTADOS = ('sin_acuerdo', 'pendiente_anticipo', 'abono', 'pagado')

#: Los cortes de antigüedad de la contabilidad colombiana, en orden de edad.
#: Quién cae en cuál lo decide la vista `v_cartera`, no este archivo: así el
#: informe por edades, la lista de deudores y el archivo que se exporta parten
#: la cartera por los mismos cortes y sus totales cuadran entre sí.
TRAMOS = ('al_dia', '1_30', '31_60', '61_90', 'mas_90')

ETIQUETA_TRAMO = {
    'al_dia': 'Al día',
    '1_30': '1 a 30 días',
    '31_60': '31 a 60 días',
    '61_90': '61 a 90 días',
    'mas_90': 'Más de 90 días',
}


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
    servicio_id: int
    fecha_venta: dt.date
    vendedor: str | None
    valor_pactado: float
    total_pagado: float
    saldo: float
    exigible_hoy: float
    vencido: float
    por_vencer: float
    dias_vencido: int
    #: El atraso puesto en el corte contable: con «65 días» hay que hacer la
    #: cuenta mental; con «61 a 90» ya se sabe en qué parte del informe va.
    tramo: str
    #: La fecha de la próxima cuota que todavía no es exigible. Es lo que
    #: permite llamar antes de que la plata se vuelva mora.
    proximo_vencimiento: dt.date | None
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


def _filtros(*, solo_vencida: bool = False, tramo: str | None = None,
             desde_dias: int | None = None, vence_en_dias: int | None = None,
             vendedor_id: int | None = None, cliente_id: int | None = None,
             servicio_id: int | None = None, desde: dt.date | None = None,
             hasta: dt.date | None = None) -> tuple[list[str], dict]:
    """Los filtros de la cartera, escritos una sola vez (RF-046).

    Están aquí y no dentro de cada consulta porque las tres respuestas de la
    pantalla —los totales de arriba, el corte por edades y la lista de
    deudores— tienen que hablar de las mismas ventas. Si los totales no
    obedecieran el filtro, la tarjeta diría un número, la suma de la tabla otro,
    y nadie sabría a cuál creerle: es el mismo problema que hoy tienen las hojas
    PAGOS y REV PAGOS.

    Solo se tocan columnas de la vista y de la venta, no del cliente ni del
    servicio, para que la consulta de totales pueda usar los mismos filtros sin
    arrastrar uniones que le cambien lo que suma.
    """
    condiciones: list[str] = []
    parametros: dict = {}
    if solo_vencida:
        condiciones.append('c.vencido > 0')
    if tramo:
        condiciones.append('c.tramo_mora = :tramo')
        parametros['tramo'] = tramo
    if desde_dias is not None:
        condiciones.append('c.dias_mora >= :dias')
        parametros['dias'] = desde_dias
    if vence_en_dias is not None:
        # «Qué me vence esta semana». Pide plata que todavía no es exigible: una
        # venta sin nada por vencer no sirve para llamar antes de la fecha.
        condiciones.append('c.por_vencer > 0 and c.proximo_vencimiento is not null '
                           'and c.proximo_vencimiento <= current_date + :vence')
        parametros['vence'] = vence_en_dias
    if vendedor_id:
        condiciones.append('n.vendedor_id = :vendedor')
        parametros['vendedor'] = vendedor_id
    if cliente_id:
        condiciones.append('n.cliente_id = :cliente')
        parametros['cliente'] = cliente_id
    if servicio_id:
        condiciones.append('n.servicio_id = :servicio')
        parametros['servicio'] = servicio_id
    if desde:
        condiciones.append('n.fecha_venta >= :desde')
        parametros['desde'] = desde
    if hasta:
        condiciones.append('n.fecha_venta <= :hasta')
        parametros['hasta'] = hasta
    return condiciones, parametros


def cartera(db: Session, *, pagina: int = 1, tamano: int = 50, **filtros
            ) -> tuple[int, float, list[FilaCartera]]:
    """Quién debe, cuánto, desde cuándo y qué se le vence (RF-046).

    `dias_vencido` se cuenta desde la cuota más antigua que ya era exigible, y
    `tramo` es ese mismo atraso puesto en el corte de la contabilidad: es la
    antigüedad que pide el requerimiento y la que decide a quién se llama
    primero.
    """
    condiciones, parametros = _filtros(**filtros)
    donde = ' and '.join(['c.saldo > 0', *condiciones])

    base = f"""
        from v_cartera c
        join negocios n on n.id = c.negocio_id
        join clientes cl on cl.id = n.cliente_id
        join servicios s on s.id = n.servicio_id
        left join usuarios u on u.id = n.vendedor_id
       where {donde}"""

    total, suma = db.execute(
        text(f'select count(*), coalesce(sum(c.saldo), 0) {base}'), parametros).first()

    # `dias_mora` y `tramo_mora` los calcula la propia vista: rehacer la cuenta
    # aquí sería tener dos fórmulas que tarde o temprano dicen cosas distintas.
    filas = db.execute(text(f"""
        select c.negocio_id, n.cliente_id, cl.nombre, s.nombre, n.fecha_venta, u.nombre,
               c.valor_pactado, c.total_pagado, c.saldo, c.exigible_hoy, c.vencido,
               c.por_vencer, c.dias_mora, c.moneda, c.tramo_mora, c.proximo_vencimiento,
               n.servicio_id
        {base}
        order by c.dias_mora desc, c.vencido desc
        limit :tamano offset :salto"""),
        parametros | {'tamano': tamano, 'salto': (pagina - 1) * tamano}).all()

    return int(total), float(suma), [
        FilaCartera(
            negocio_id=f[0], cliente_id=f[1], cliente=f[2], servicio=f[3], fecha_venta=f[4],
            vendedor=f[5], valor_pactado=float(f[6] or 0), total_pagado=float(f[7] or 0),
            saldo=float(f[8] or 0), exigible_hoy=float(f[9] or 0), vencido=float(f[10] or 0),
            por_vencer=float(f[11] or 0), dias_vencido=int(f[12] or 0),
            moneda=f[13], tramo=f[14], proximo_vencimiento=f[15],
            servicio_id=f[16]) for f in filas]


def resumen(db: Session, **filtros) -> dict:
    """Los números que se miran de un vistazo, con los filtros puestos.

    «Por vencer» va al lado de «vencido» porque sin él de la cartera solo se ve
    la mitad: lo que ya se pasó de fecha, y no lo que se va a pasar la semana
    entrante, que es lo único que todavía se puede evitar.
    """
    condiciones, parametros = _filtros(**filtros)
    donde = f"where {' and '.join(condiciones)}" if condiciones else ''
    fila = db.execute(text(f"""
        select coalesce(sum(c.valor_pactado), 0), coalesce(sum(c.total_pagado), 0),
               coalesce(sum(c.saldo), 0), coalesce(sum(c.vencido), 0),
               coalesce(sum(c.por_vencer), 0),
               count(*) filter (where c.saldo > 0)
          from v_cartera c
          join negocios n on n.id = c.negocio_id
          {donde}"""), parametros).first()
    return {'vendido': float(fila[0]), 'cobrado': float(fila[1]), 'cartera': float(fila[2]),
            'vencido': float(fila[3]), 'por_vencer': float(fila[4]),
            'ventas_con_saldo': int(fila[5])}


def antiguedad(db: Session, **filtros) -> list[dict]:
    """La cartera repartida por edades: el informe con el que se cobra (RF-046).

    Los cuatro tramos son los de la contabilidad colombiana. Un número de días
    por fila no contesta la pregunta que de verdad se hace —«de lo que me
    deben, cuánto lleva entre 31 y 60 días»—, y mientras no se contesta nadie
    sabe cuánta plata ya está en el tramo que toca dar por difícil de cobrar.

    Los tramos vacíos también salen, y en orden de edad: un informe al que le
    falta la fila de «más de 90 días» se lee como que no hay nada ahí, y no es
    lo mismo que no haberlo mirado.
    """
    condiciones, parametros = _filtros(**filtros)
    donde = ' and '.join(['c.saldo > 0', *condiciones])
    medido = {t: (int(n), float(s), float(v), float(p))
              for t, n, s, v, p in db.execute(text(f"""
                  select c.tramo_mora, count(*), coalesce(sum(c.saldo), 0),
                         coalesce(sum(c.vencido), 0), coalesce(sum(c.por_vencer), 0)
                    from v_cartera c
                    join negocios n on n.id = c.negocio_id
                   where {donde}
                   group by 1"""), parametros)}
    return [{'tramo': t, 'etiqueta': ETIQUETA_TRAMO[t],
             'cuantas': medido.get(t, (0, 0.0, 0.0, 0.0))[0],
             'saldo': medido.get(t, (0, 0.0, 0.0, 0.0))[1],
             'vencido': medido.get(t, (0, 0.0, 0.0, 0.0))[2],
             'por_vencer': medido.get(t, (0, 0.0, 0.0, 0.0))[3]} for t in TRAMOS]


def por_estado(db: Session) -> list[tuple[str, int, float]]:
    return [(e, int(n), float(s)) for e, n, s in db.execute(text("""
        select estado_financiero, count(*), coalesce(sum(saldo), 0)
          from v_estado_financiero group by 1 order by 2 desc"""))]
