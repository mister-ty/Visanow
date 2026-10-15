"""La cartera dejaba de recorrer la tabla de pagos una vez por venta (RNF-08).

La pantalla de cartera —la que contesta «quien nos debe»— sale de la vista
`v_estado_financiero`, que por cada venta suma sus pagos y sus ajustes. Hasta
hoy la tabla `pagos` no tenia ningun indice por `negocio_id`, asi que para
sumarle los pagos a una venta PostgreSQL recorria los 634 pagos completos. Con
501 ventas, eso es recorrer la tabla 501 veces para armar una sola pantalla.

Medido sobre la base de desarrollo con los datos reales migrados, la consulta de
cartera ordenada por saldo:

    sin el indice   18,4 ms   ->  Seq Scan on pagos   (loops=501)
    con el indice    1,1 ms   ->  Index Scan using ix_pagos_negocio

Diecisiete veces, y el plan cambia de recorrido completo a busqueda por indice.
Pero el numero que importa no es el de hoy: 18 ms no molestan a nadie. Lo que
importa es la forma de la cuenta. El costo crece con pagos *por* ventas, no con
pagos mas ventas: al triple de volumen —1.500 ventas y 1.900 pagos, que es un
año y medio de trabajo a este ritmo— son nueve veces mas, y ahi si se siente.
Esta es la clase de lentitud que no existe el dia que se escribe y que despues
nadie sabe de donde salio, porque no la causo ningun cambio.

`ajustes_negocio` lleva el indice por la misma razon y en el mismo lugar del
plan: la vista la agrega igual, una vez por venta. Hoy la tabla esta vacia, asi
que no hay nada que medir todavia; se agrega ahora porque el dia que tenga filas
el problema ya estaria ahi, y porque la vista que las suma es la misma.

Se queda por fuera, a proposito, un indice por fecha en `pagos`: tambien se
probo y no cambio nada (la consulta ya tardaba 0,1 ms con recorrido completo).
Un indice que no se usa no es gratis —se mantiene en cada insercion de un pago—,
asi que no entra sin una medicion que lo pida.

No hay tablas nuevas, asi que no hay RLS que activar.

Revision ID: 0027_indice_pagos_por_negocio
Revises: 0021_referencia_de_pago
Create Date: 2026-10-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0027_indice_pagos_por_negocio'
down_revision: Union[str, None] = '0021_referencia_de_pago'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabla, columna). Las dos las agrega `v_estado_financiero` una vez por venta.
FALTANTES = (
    ('pagos', 'negocio_id'),
    ('ajustes_negocio', 'negocio_id'),
)


def upgrade() -> None:
    for tabla, columna in FALTANTES:
        op.execute(f'create index ix_{tabla}_negocio on {tabla} ({columna})')


def downgrade() -> None:
    for tabla, _ in FALTANTES:
        op.execute(f'drop index if exists ix_{tabla}_negocio')
