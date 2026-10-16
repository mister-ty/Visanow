"""Una venta se puede anular, y la cartera deja de contarla (RF-040, RN-01).

La carga de los Excel trajo la misma venta dos veces cuando aparecía en dos
hojas del mismo libro. Contado sobre producción: **16 ventas repetidas, con
$18.006.000 de más**, y 13 de ellas son el mismo negocio anotado en `PAGOS` y en
`PAGOS2026`. La idempotencia de la carga es por `(archivo, hoja, fila)`, así que
el mismo hecho en dos hojas son dos filas: no es un descuido de quien cargó, es
que la llave no podía verlo.

El problema no era solo que estuviera repetido. Era que **no había forma de
corregirlo**: sobre una venta solo existían cotizar, ganar y consultar. Ninguna
operación la quitaba de la cartera. O sea que el saldo de 16 clientes estaba mal
y el sistema no tenía con qué arreglarlo —y la cartera es el número con el que
se decide a quién se le cobra—.

**Se anula, no se borra.** La fila queda, con quién la anuló, cuándo y por qué.
Una venta que desaparece de la base sin rastro es peor que una repetida: nadie
puede responder después por qué los totales de octubre cambiaron.

Lo que sí hay que hacer ANTES de anular es resolver sus pagos, y por eso el
servicio se niega si tiene alguno confirmado. No es burocracia: en estas 16, los
pagos están repartidos entre las dos copias —$17,6 millones en una y $5,4 en la
otra— así que anular a secas haría desaparecer plata que sí entró. Cada pago hay
que marcarlo duplicado (si es el mismo anotado dos veces, que es el caso del
libro de ventas contra la caja) o moverlo a la venta que queda. Las dos
operaciones ya existían.

La vista se recrea para no contar las anuladas. Es el único sitio donde hay que
hacerlo: el saldo sale de ahí y nunca de una columna (RN-01), así que la cartera,
los tableros y la ficha quedan bien de una sola vez.

Revision ID: 0030_anular_una_venta_repetida
Revises: 0029_grupo_familiar_o_de_viaje
Create Date: 2026-10-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0030_anular_una_venta_repetida'
down_revision: Union[str, None] = '0029_grupo_familiar_o_de_viaje'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# La vista, igual que en db/schema/003_correcciones.sql pero sin las anuladas.
# Se escribe entera porque `create or replace view` no admite cambiar columnas:
# hay que darle la definición completa.
VISTA = """
create or replace view v_estado_financiero as
select
  n.id                                                           as negocio_id,
  n.valor_pactado,
  coalesce(p.pagado, 0)                                          as total_pagado,
  coalesce(p.neto, 0)                                            as neto_recibido,
  coalesce(a.ajustes, 0)                                         as ajustes,
  n.valor_pactado + coalesce(a.ajustes,0) - coalesce(p.pagado,0) as saldo,
  case
    when n.valor_pactado is null or n.valor_pactado = 0                then 'sin_acuerdo'
    when n.valor_pactado + coalesce(a.ajustes,0)
         - coalesce(p.pagado,0) <= 0                                   then 'pagado'
    when coalesce(p.pagado,0) = 0                                      then 'pendiente_anticipo'
    else                                                                    'abono'
  end                                                            as estado_financiero,
  n.moneda
from negocios n
left join lateral (
  select sum(monto_bruto) as pagado, sum(monto_neto) as neto
  from pagos
  where negocio_id = n.id and estado = 'confirmado' and moneda = n.moneda
) p on true
left join lateral (
  select sum(monto) as ajustes from ajustes_negocio where negocio_id = n.id
) a on true
where {filtro};
"""


def upgrade() -> None:
    op.execute("""
        alter table negocios
          add column anulada_en timestamptz,
          add column anulada_por bigint references usuarios(id),
          add column motivo_anulacion text
    """)
    # Índice parcial: las anuladas son unas pocas y se buscan aparte, mientras
    # que todas las demás consultas filtran por «no anulada».
    op.execute('create index ix_negocios_anuladas on negocios (anulada_en) '
               'where anulada_en is not null')
    op.execute(VISTA.format(filtro='n.anulada_en is null'))
    # La vista se recreó, así que vuelve a necesitar `security_invoker` (0016):
    # sin esto se salta el RLS de sus tablas y `anon` volvería a leer las 501
    # ventas. Hay prueba que lo vigila.
    op.execute('alter view v_estado_financiero set (security_invoker = true)')


def downgrade() -> None:
    op.execute(VISTA.format(filtro='true'))
    op.execute('alter view v_estado_financiero set (security_invoker = true)')
    op.execute('drop index if exists ix_negocios_anuladas')
    op.execute("""
        alter table negocios
          drop column if exists anulada_en,
          drop column if exists anulada_por,
          drop column if exists motivo_anulacion
    """)
