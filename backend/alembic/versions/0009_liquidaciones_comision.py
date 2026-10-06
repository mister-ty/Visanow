"""La liquidación de comisiones por periodo (RF-052).

Las comisiones ya se podían calcular y guardar una por una, pero faltaba el
corte: juntar las del mes de una vendedora, sumarlas, dejar constancia de qué
ventas entraron y bloquearlas para que no se paguen dos veces.

Lo de bloquear es el punto. Sin esto, una comisión liquidada en octubre puede
volver a aparecer en el corte de noviembre si alguien recalcula, y nadie lo
nota hasta que se paga doble. Por eso `liquidaciones_comision` no es un reporte:
es el registro de que esa plata ya se pagó, y la comisión apunta de vuelta a
él.

Revision ID: 0009_liquidaciones
Revises: 0008_origen_1n
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0009_liquidaciones'
down_revision: Union[str, None] = '0008_origen_1n'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        create table liquidaciones_comision (
            id            bigserial primary key,
            vendedor_id   bigint       not null references usuarios(id),
            periodo       date         not null,
            total         numeric(14,2) not null,
            cantidad      integer      not null,
            estado        varchar(12)  not null default 'abierta',
            observaciones text,
            liquidada_por bigint references usuarios(id),
            creada_en     timestamptz  not null default now(),
            pagada_en     timestamptz,
            constraint ck_liquidacion_estado
                check (estado in ('abierta', 'pagada', 'anulada')),
            constraint ck_liquidacion_total check (total >= 0 and cantidad >= 0)
        )
    """)
    # Un solo corte por vendedora y periodo: si se necesita otro, se anula el
    # anterior. Dos cortes abiertos del mismo mes es la receta del pago doble.
    op.execute("""
        create unique index ux_liquidacion_vendedor_periodo
            on liquidaciones_comision (vendedor_id, periodo)
         where estado <> 'anulada'
    """)
    op.execute("comment on table liquidaciones_comision is "
               "'Corte de comisiones de una vendedora en un periodo. Las comisiones que entran "
               "quedan en estado liquidada y apuntan aquí, para que no se paguen dos veces.'")

    op.execute("""
        alter table comisiones
          add column if not exists liquidacion_id bigint
              references liquidaciones_comision(id)
    """)
    op.execute("""
        create index if not exists ix_comisiones_liquidacion
            on comisiones (liquidacion_id) where liquidacion_id is not null
    """)
    op.execute("comment on column comisiones.liquidacion_id is "
               "'En qué corte se pagó. Mientras sea nulo, la comisión no se ha pagado.'")


def downgrade() -> None:
    op.execute('drop index if exists ix_comisiones_liquidacion')
    op.execute('alter table comisiones drop column if exists liquidacion_id')
    op.execute('drop table if exists liquidaciones_comision')
