"""El índice ciego del DS-160 queda del mismo tipo que el del pasaporte.

El sistema tiene dos datos cifrados que además hay que poder buscar: el número
de pasaporte y el número de DS-160. Los dos se buscan igual, por un índice ciego
—un HMAC del valor, que permite la búsqueda exacta sin descifrar la columna—,
pero quedaron de tipos distintos: `solicitantes.pasaporte_indice` es char(64)
con el HMAC en hexadecimal y `casos.ds160_hash` era bytea.

Con dos tipos, la misma función `indice_ciego()` no sirve para las dos columnas
y la búsqueda global falla con «bytes or buffer expected». Se unifica en char(64)
ahora, que nada escribe todavía esa columna (la llena la importación del SaaS,
actividad 5.1): hacerlo después costaría convertir datos reales.

Revision ID: 0006_indice_ds160
Revises: 0005_casos
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0006_indice_ds160'
down_revision: Union[str, None] = '0005_casos'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `encode(..., 'hex')` deja en hexadecimal lo que hubiera: la conversión es
    # defensiva, hoy la columna está vacía.
    op.execute("""
        alter table casos
          alter column ds160_hash type char(64)
          using encode(ds160_hash, 'hex')
    """)
    op.execute("comment on column casos.ds160_hash is "
               "'Índice ciego (HMAC-SHA256 en hexadecimal) del número de DS-160, "
               "para buscarlo sin descifrar ds160_numero_cifrado'")


def downgrade() -> None:
    op.execute("""
        alter table casos
          alter column ds160_hash type bytea
          using decode(ds160_hash, 'hex')
    """)
