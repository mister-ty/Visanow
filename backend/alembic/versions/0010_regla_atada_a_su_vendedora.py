"""Cada regla de comisión queda atada a su vendedora por id.

Las dos reglas se sembraron con `vendedor_id` nulo: el seed desempaquetaba a
quién era cada una y nunca lo escribía. Para saber de quién era una regla,
`regla_para` terminaba adivinando por el primer nombre de la usuaria —que el
nombre de la regla empezara igual—, y cuando no adivinaba devolvía la primera
regla sin vendedora.

Eso repartía el escalón del 10 % de Angie entre todo el mundo. «Isa», que es la
Yas real de la base, no empareja con la regla llamada «Yas — 7 %…» porque 'yas…'
no empieza por 'isa'; caía en la de Angie y cobraba su escalón. Igual cualquier
comercial que se creara mañana, y cada una estrenando su propio cupo de diez
ventas al 10 %: 36.000 COP de más por venta premium, hasta 360.000 al mes por
persona. La administradora fue explícita en que las comisiones son solo de Angie
y de Yas, y que Miriam no vende.

Las reglas se amarran por correo, que es único y lo dio ella misma el 03/10. La
que no se pueda amarrar queda **inactiva**: una regla sin dueña tiene que pagarle
a nadie, no a todas.

Revision ID: 0010_regla_vendedora
Revises: 0009_liquidaciones
Create Date: 2026-10-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0010_regla_vendedora'
down_revision: Union[str, None] = '0009_liquidaciones'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Correos dados por la administradora el 03/10/2026.
DUENAS = (
    ('Angie%', 'angielorena221003@gmail.com'),
    ('Yas%', 'yasvic1212@gmail.com'),
)


def upgrade() -> None:
    for patron, correo in DUENAS:
        op.execute(f"""
            update comisiones_reglas r
               set vendedor_id = u.id
              from usuarios u
             where r.nombre like '{patron}'
               and r.vendedor_id is null
               and lower(u.email) = '{correo}'
        """)

    # Lo que no se pudo amarrar se apaga, con el motivo escrito en la regla: sin
    # esto una regla huérfana se vuelve la regla general de todo el mundo.
    op.execute("""
        update comisiones_reglas
           set activo = false,
               definicion = coalesce(definicion, '{}'::jsonb) || jsonb_build_object(
                   'inactiva_porque',
                   'No se pudo determinar de quién es esta regla: no hay usuaria con el '
                   'correo que la identifica. Asígnele la vendedora y actívela.')
         where vendedor_id is null
           and (nombre like 'Angie%' or nombre like 'Yas%')
    """)


def downgrade() -> None:
    op.execute("""
        update comisiones_reglas
           set vendedor_id = null,
               activo = true,
               definicion = definicion - 'inactiva_porque'
         where nombre like 'Angie%' or nombre like 'Yas%'
    """)
