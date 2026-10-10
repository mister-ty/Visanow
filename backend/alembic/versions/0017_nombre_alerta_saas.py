"""El tipo de alerta del SaaS no se llama «fallida»: dispara tambien cuando no fallo.

La regla avisa por dos motivos distintos -la ultima importacion dio error, o
funciono pero lleva mas de un dia sin correr-. El nombre «Sincronizacion SaaS
fallida» solo describe el primero, y en la bandeja quedaba un titulo que decia
«fallida» sobre un cuerpo que decia «5 tramites actualizados, 0 con conflicto».

No va por el seed porque ALERTAS siembra con `on conflict (codigo) do nothing`,
y eso esta bien: la matriz la configura la administradora y volver a sembrar no
puede pisarle lo que cambio. El nombre no es configurable desde la pantalla, asi
que renombrarlo aca es seguro.

Revision ID: 0017_nombre_alerta_saas
Revises: 0016_vistas_invocador
"""
from alembic import op

revision = '0017_nombre_alerta_saas'
down_revision = '0016_vistas_invocador'
branch_labels = None
depends_on = None

VIEJO = 'Sincronización SaaS fallida'
NUEVO = 'Importación del SaaS'


def upgrade() -> None:
    op.execute(f"""update alertas_tipos set nombre = '{NUEVO}'
                    where codigo = 'sync_saas_fallida' and nombre = '{VIEJO}'""")


def downgrade() -> None:
    op.execute(f"""update alertas_tipos set nombre = '{VIEJO}'
                    where codigo = 'sync_saas_fallida' and nombre = '{NUEVO}'""")
