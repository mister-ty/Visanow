"""Cierra la lectura directa de las tablas por la API de Supabase.

Supabase publica el esquema `public` en internet a través de PostgREST. Cualquiera
con la llave anónima —que es pública por diseño, va en el código del navegador—
puede consultar las tablas que no tengan «row level security» activa. En este
sistema eso serían los pasaportes, los números de DS-160 y los datos de 866
personas, legibles con una llave que no es secreta.

**Activar RLS sin escribir ni una política deja la puerta cerrada**, y es lo
correcto acá: VisaNow no usa la API de Supabase. La aplicación habla con
PostgreSQL por conexión directa como `postgres`, que tiene `BYPASSRLS`, así que
no se entera de nada. Quien sí se entera es `anon`, que deja de ver filas.

Es seguro fuera de Supabase. En la base de desarrollo y en la del VPS la
aplicación se conecta con el rol **dueño** de las tablas, y en PostgreSQL el
dueño salta RLS mientras no se le ponga `FORCE ROW LEVEL SECURITY`. Así que acá
no cambia nada; allá cierra un hueco.

La prueba `test_seguridad.py` verifica que toda tabla nueva también la tenga: una
migración solo cubre las tablas que existían el día que se escribió, y un
descuido futuro volvería a abrir la puerta sin que nada falle.

Revision ID: 0015_rls_cerrado
Revises: 0014_plantillas
Create Date: 2026-10-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0015_rls_cerrado'
down_revision: Union[str, None] = '0014_plantillas'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Se recorren las tablas que existan, en vez de nombrarlas: son más de
    # cincuenta y una lista escrita a mano se desactualiza en el primer cambio.
    op.execute("""
        do $$
        declare t record;
        begin
          for t in select tablename from pg_tables
                    where schemaname = 'public' and tablename <> 'alembic_version'
          loop
            execute format('alter table public.%I enable row level security', t.tablename);
          end loop;
        end $$;
    """)


def downgrade() -> None:
    op.execute("""
        do $$
        declare t record;
        begin
          for t in select tablename from pg_tables
                    where schemaname = 'public' and tablename <> 'alembic_version'
          loop
            execute format('alter table public.%I disable row level security', t.tablename);
          end loop;
        end $$;
    """)
