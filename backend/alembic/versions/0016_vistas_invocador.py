"""Las vistas de plata dejan de saltarse el RLS, y dos arreglos menores.

La migración 0015 activó «row level security» en las 56 tablas, y con eso la
llave anónima de Supabase dejó de poder leerlas. Pero las vistas se habían
quedado por fuera, y en PostgreSQL una vista corre por omisión con los permisos
de **quien la creó**, no de quien la consulta. Como las creó `postgres`, que
tiene BYPASSRLS, el RLS de las tablas de abajo no se evaluaba.

Medido contra la base de Supabase ya cargada, haciéndose pasar por `anon`:

    clientes             0 filas      (el RLS de 0015 sí funciona)
    v_estado_financiero  477 ventas, $390.445.600
    v_cartera            $65.376.226 de cartera

Es decir: con la llave que va escrita en el código del navegador, cualquiera
podía leer la posición financiera completa de la agencia. Las tablas estaban
cerradas y la puerta de al lado abierta.

`security_invoker` hace que la vista corra con los permisos de quien pregunta.
Para la aplicación no cambia nada —se conecta como dueño o con BYPASSRLS—, pero
`anon` pasa a ver cero.

De paso, dos cosas que el analizador de Supabase marcó y que es barato cerrar:

- `alembic_version` también quedaba expuesta. No tiene datos de nadie, solo dice
  en qué migración va la base, pero eso ya le dice a un atacante qué versión del
  esquema está mirando.
- `auditoria_inalterable` y `sin_tildes` no tenían `search_path` fijo. Una
  función sin él puede resolver nombres contra un esquema que el llamante
  controle. En `auditoria_inalterable` importa más de lo que parece: es la que
  impide modificar la auditoría (RNF-05).

Revision ID: 0016_vistas_invocador
Revises: 0015_rls_cerrado
Create Date: 2026-10-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0016_vistas_invocador'
down_revision: Union[str, None] = '0015_rls_cerrado'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL 15 en adelante. La base de desarrollo es 16 y Supabase 17.
    op.execute('alter view v_estado_financiero set (security_invoker = true)')
    op.execute('alter view v_cartera set (security_invoker = true)')

    op.execute('alter table alembic_version enable row level security')

    op.execute("alter function auditoria_inalterable() set search_path = pg_catalog, public")
    op.execute("alter function sin_tildes(text) set search_path = pg_catalog, public")


def downgrade() -> None:
    op.execute('alter function sin_tildes(text) reset search_path')
    op.execute('alter function auditoria_inalterable() reset search_path')
    op.execute('alter table alembic_version disable row level security')
    op.execute('alter view v_cartera set (security_invoker = false)')
    op.execute('alter view v_estado_financiero set (security_invoker = false)')
