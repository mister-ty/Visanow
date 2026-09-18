"""Núcleo de VisaNow: 50 tablas, 2 vistas, 101 índices.

Ejecuta los tres archivos de db/schema/ en orden. Se escriben con op.execute()
y no con autogenerate a propósito: Alembic no reproduce la columna generada
monto_neto, los índices parciales ni las vistas, y si se confiara en el
autogenerate la siguiente migración intentaría borrarlos.

Revision ID: 0001_nucleo
Revises:
Create Date: 2026-09-18
"""
import pathlib
import re
from typing import Sequence, Union

from alembic import op

revision: str = '0001_nucleo'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ESQUEMA = pathlib.Path(__file__).resolve().parents[3] / 'db' / 'schema'
ARCHIVOS = ('001_nucleo.sql', '002_brechas.sql', '003_correcciones.sql')


def _sentencias(sql: str):
    """Parte el archivo en sentencias respetando los $$ de los cuerpos de función."""
    sql = re.sub(r'^\s*--.*$', '', sql, flags=re.M)
    partes, actual, en_dolar = [], [], False
    for linea in sql.splitlines():
        if linea.count('$$') % 2 == 1:
            en_dolar = not en_dolar
        actual.append(linea)
        if not en_dolar and linea.rstrip().endswith(';'):
            texto = '\n'.join(actual).strip()
            if texto and texto != ';':
                partes.append(texto)
            actual = []
    resto = '\n'.join(actual).strip()
    if resto:
        partes.append(resto)
    return partes


def upgrade() -> None:
    for nombre in ARCHIVOS:
        ruta = ESQUEMA / nombre
        if not ruta.exists():
            raise FileNotFoundError(f'No se encontró {ruta}')
        for sentencia in _sentencias(ruta.read_text(encoding='utf-8')):
            op.execute(sentencia)


def downgrade() -> None:
    # El núcleo no se revierte por partes: se vacía el esquema entero.
    # alembic_version se preserva, porque Alembic la actualiza justo después
    # de que esto termine; si se borra, el downgrade falla al no encontrarla.
    op.execute("""
        do $$
        declare r record;
        begin
          for r in select table_name from information_schema.views
                   where table_schema = 'public' loop
            execute format('drop view if exists public.%I cascade', r.table_name);
          end loop;
          for r in select table_name from information_schema.tables
                   where table_schema = 'public' and table_type = 'BASE TABLE'
                     and table_name <> 'alembic_version' loop
            execute format('drop table if exists public.%I cascade', r.table_name);
          end loop;
        end $$;
    """)
