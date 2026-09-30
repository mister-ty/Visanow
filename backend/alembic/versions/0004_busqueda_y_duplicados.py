"""Búsqueda de personas y detección de duplicados (RF-002, RF-029).

En los archivos actuales el mismo cliente aparece escrito de varias formas
(«MARIA JOSE» y «María José») y el teléfono unas veces con +57 y otras sin él:
971 menciones de cliente para 570 personas reales. Comparar los textos tal como
están no encuentra esos duplicados.

Se agregan dos columnas calculadas por la base, que siempre están al día porque
no las escribe la aplicación:

- nombre_busqueda: el nombre en minúsculas y sin tildes, con índice de trigramas
  para comparar por parecido.
- telefono_normalizado: los últimos 10 dígitos, sin +57, espacios ni guiones.

unaccent() es «estable» y no se puede usar en una columna calculada; por eso se
envuelve en sin_tildes(), declarada inmutable. Es la práctica habitual: el
diccionario de unaccent no cambia en la vida de la base.

Revision ID: 0004_duplicados
Revises: 0003_respuestas
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0004_duplicados'
down_revision: Union[str, None] = '0003_respuestas'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('create extension if not exists unaccent')
    op.execute("""
        create or replace function sin_tildes(texto text) returns text
        language sql immutable parallel safe strict as
        $$ select public.unaccent('public.unaccent', texto) $$
    """)

    for tabla in ('clientes', 'solicitantes'):
        op.execute(f"""
            alter table {tabla}
              add column nombre_busqueda text
                  generated always as (lower(sin_tildes(nombre))) stored,
              add column telefono_normalizado varchar(10)
                  generated always as (
                      nullif(right(regexp_replace(coalesce(telefono,''), '[^0-9]', '', 'g'), 10), '')
                  ) stored
        """)
        op.execute(f"""create index ix_{tabla}_nombre_busqueda on {tabla}
                       using gin (nombre_busqueda gin_trgm_ops)""")
        op.execute(f"""create index ix_{tabla}_telefono_norm on {tabla} (telefono_normalizado)
                       where telefono_normalizado is not null""")

    # El documento de un solicitante no es único (una persona puede estar además
    # registrada como cliente), pero sí se busca por él para detectar duplicados.
    op.execute("""create index ix_solicitantes_documento on solicitantes
                  (coalesce(tipo_documento,'?'), numero_documento)
                  where numero_documento is not null""")
    op.execute('create index ix_solicitantes_email on solicitantes (email) where email is not null')
    op.execute("""create index ix_solicitantes_grupo on solicitantes (grupo_id)
                  where grupo_id is not null""")
    op.execute("""create index ix_solicitantes_cliente on solicitantes (cliente_id)
                  where cliente_id is not null""")
    op.execute('create index ix_grupos_contacto on grupos (cliente_contacto_id)')

    # Quien fue absorbido en una fusión no vuelve a aparecer en las búsquedas
    op.execute("""create index ix_clientes_activos on clientes (id)
                  where fusionado_en_id is null and not archivado""")


def downgrade() -> None:
    op.execute('drop index if exists ix_clientes_activos')
    op.execute('drop index if exists ix_grupos_contacto')
    op.execute('drop index if exists ix_solicitantes_cliente')
    op.execute('drop index if exists ix_solicitantes_grupo')
    op.execute('drop index if exists ix_solicitantes_email')
    op.execute('drop index if exists ix_solicitantes_documento')
    for tabla in ('clientes', 'solicitantes'):
        op.execute(f'drop index if exists ix_{tabla}_telefono_norm')
        op.execute(f'drop index if exists ix_{tabla}_nombre_busqueda')
        op.execute(f'alter table {tabla} drop column if exists telefono_normalizado, '
                   f'drop column if exists nombre_busqueda')
    op.execute('drop function if exists sin_tildes(text)')
