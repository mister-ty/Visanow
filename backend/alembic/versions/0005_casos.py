"""Casos de visa: venta opcional, próxima acción y tablero (RF-020 a RF-028, RN-04).

1. El caso deja de exigir una venta. En los archivos actuales la operación vive
   en VISANOW CLIENTES.xlsx (287 trámites de 2026) y el dinero en
   CUENTAS VISANOW.xlsx: son libros distintos y no siempre se cruzan. Al migrar
   habrá trámites sin venta registrada, y la importación del SaaS también crea
   casos antes de que la venta exista. Exigirla obligaría a inventar ventas, que
   es peor que ver el hueco: «trámite sin venta» pasa a ser un control.

2. RN-04 pide que todo caso activo tenga responsable, estado, última actividad y
   próxima acción. Las tres primeras ya estaban; la próxima acción no existía.

Revision ID: 0005_casos
Revises: 0004_duplicados
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0005_casos'
down_revision: Union[str, None] = '0004_duplicados'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('alter table casos alter column negocio_id drop not null')
    op.execute("""
        alter table casos
          add column proxima_accion varchar(200),
          add column proxima_accion_fecha date
    """)

    # El tablero operativo (RF-022) filtra por estado, responsable y antigüedad
    op.execute('create index ix_casos_tablero on casos (estado_id, responsable_id, ultima_actividad_en desc)')
    op.execute("""create index ix_casos_sin_asignar on casos (creado_en)
                  where responsable_id is null""")
    op.execute("""create index ix_casos_sin_venta on casos (creado_en)
                  where negocio_id is null""")
    op.execute('create index ix_casos_solicitante on casos (solicitante_id)')
    op.execute('create index ix_citas_caso on citas (caso_id, inicia_en)')
    op.execute("""create index ix_citas_proximas on citas (inicia_en)
                  where estado in ('pendiente','programada','confirmada')""")
    op.execute('create index ix_historial_caso on casos_historial (caso_id, ocurrido_en desc)')


def downgrade() -> None:
    op.execute('drop index if exists ix_historial_caso')
    op.execute('drop index if exists ix_citas_proximas')
    op.execute('drop index if exists ix_citas_caso')
    op.execute('drop index if exists ix_casos_solicitante')
    op.execute('drop index if exists ix_casos_sin_venta')
    op.execute('drop index if exists ix_casos_sin_asignar')
    op.execute('drop index if exists ix_casos_tablero')
    op.execute("""alter table casos drop column if exists proxima_accion_fecha,
                  drop column if exists proxima_accion""")
    op.execute('alter table casos alter column negocio_id set not null')
