"""La cartera se puede leer por edades, y se sabe qué vence la semana entrante.

Hasta ahora `v_cartera` decía cuántos días llevaba vencida cada venta y nada
más. Con un número suelto por fila no se puede contestar la pregunta que de
verdad se hace al cobrar —«de lo que me deben, cuánto lleva entre 31 y 60
días»—, que es la que decide a quién se llama hoy y qué parte de la cartera ya
hay que dar por difícil de recuperar.

Se agregan dos cosas a la vista:

- `tramo_mora`: el corte por edades en los cuatro tramos de la contabilidad
  colombiana (1-30, 31-60, 61-90 y más de 90 días), los mismos con los que se
  arma cualquier informe de cartera por edades.
- `proximo_vencimiento`: la fecha de la próxima cuota que todavía no es
  exigible. Sin ella no hay forma de preguntar «qué me vence esta semana», que
  es lo que permite llamar ANTES de que la plata se vuelva mora. Hoy «por
  vencer» se ve, pero no se puede filtrar, así que no sirve para organizar el
  trabajo del día.

Van en la VISTA y no en el código de la aplicación a propósito. La lista de
deudores, el informe por edades y el archivo que se exporta tienen que partir
la cartera por los mismos cortes; si cada uno hiciera su propia cuenta, tarde o
temprano el total del informe no cuadraría con la suma de la tabla. Es
exactamente el problema que hay hoy entre las hojas PAGOS y REV PAGOS, donde la
misma deuda aparece con 37 millones de diferencia.

Una venta con cuota exigible hoy y sin pagar entra en el primer tramo y no en
«al día»: es plata que ya se tenía que haber recibido, aunque todavía no haya
cumplido un día de atraso.

Revision ID: 0019_cartera_por_edades
Revises: 0018_colaboradores_caso
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0019_cartera_por_edades'
down_revision: Union[str, None] = '0018_colaboradores_caso'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Las nueve columnas de antes van en el mismo orden y con el mismo nombre: así
# `create or replace` conserva la vista en lugar de pedir que se borre, y nada
# de lo que ya la consulta se rompe.
NUEVA = """
create or replace view v_cartera as
with exigible as (
  select negocio_id, sum(monto) as exigible_hoy, min(fecha_pactada) as mas_antigua
  from cuotas_negocio where fecha_pactada <= current_date group by negocio_id
), siguiente as (
  select negocio_id, min(fecha_pactada) as proxima
  from cuotas_negocio where fecha_pactada > current_date group by negocio_id
)
select f.negocio_id, f.moneda, f.valor_pactado, f.total_pagado, f.saldo,
       coalesce(e.exigible_hoy,0) as exigible_hoy,
       greatest(coalesce(e.exigible_hoy,0) - f.total_pagado, 0) as vencido,
       greatest(f.saldo - greatest(coalesce(e.exigible_hoy,0) - f.total_pagado, 0), 0) as por_vencer,
       case when coalesce(e.exigible_hoy,0) - f.total_pagado > 0
            then current_date - e.mas_antigua else 0 end as dias_mora,
       case
         when coalesce(e.exigible_hoy,0) - f.total_pagado <= 0 then 'al_dia'
         when current_date - e.mas_antigua <= 30                then '1_30'
         when current_date - e.mas_antigua <= 60                then '31_60'
         when current_date - e.mas_antigua <= 90                then '61_90'
         else                                                        'mas_90'
       end as tramo_mora,
       s.proxima as proximo_vencimiento
from v_estado_financiero f
left join exigible e on e.negocio_id = f.negocio_id
left join siguiente s on s.negocio_id = f.negocio_id
"""

ANTERIOR = """
create view v_cartera as
with exigible as (
  select negocio_id, sum(monto) as exigible_hoy, min(fecha_pactada) as mas_antigua
  from cuotas_negocio where fecha_pactada <= current_date group by negocio_id
)
select f.negocio_id, f.moneda, f.valor_pactado, f.total_pagado, f.saldo,
       coalesce(e.exigible_hoy,0) as exigible_hoy,
       greatest(coalesce(e.exigible_hoy,0) - f.total_pagado, 0) as vencido,
       greatest(f.saldo - greatest(coalesce(e.exigible_hoy,0) - f.total_pagado, 0), 0) as por_vencer,
       case when coalesce(e.exigible_hoy,0) - f.total_pagado > 0
            then current_date - e.mas_antigua else 0 end as dias_mora
from v_estado_financiero f
left join exigible e on e.negocio_id = f.negocio_id
"""


def upgrade() -> None:
    op.execute(NUEVA)
    # Se vuelve a dejar explícito: sin `security_invoker` la vista corre con los
    # permisos de quien la creó y se salta el RLS de las tablas de abajo, que es
    # el hueco que cerró la migración 0016 y por el que la posición financiera
    # completa quedaba legible con la llave pública del navegador.
    op.execute('alter view v_cartera set (security_invoker = true)')


def downgrade() -> None:
    # `create or replace` no puede quitar columnas, así que para volver atrás
    # hay que recrear la vista.
    op.execute('drop view v_cartera')
    op.execute(ANTERIOR)
    op.execute('alter view v_cartera set (security_invoker = true)')
