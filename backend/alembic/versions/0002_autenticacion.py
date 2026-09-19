"""Autenticación: bloqueo por intentos, sesiones invalidables y auditoría inalterable.

- intentos_fallidos / bloqueado_hasta: cinco contraseñas erradas bloquean la
  cuenta quince minutos (RNF-02).
- password_cambiado_en: todo token emitido antes de un cambio de contraseña
  deja de servir.
- debe_cambiar_password: el usuario creado por la administradora entra con una
  contraseña temporal y no puede operar hasta cambiarla.
- La auditoría se vuelve inalterable en la base de datos (RNF-05). COMO_INICIAR.md
  pedía que el usuario de la API solo tuviera INSERT y SELECT sobre la tabla,
  pero la API usa una sola conexión: la regla no se cumplía. Un trigger la
  impone sin importar con qué usuario se conecte quien intente modificarla.

Revision ID: 0002_autenticacion
Revises: 0001_nucleo
Create Date: 2026-09-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0002_autenticacion'
down_revision: Union[str, None] = '0001_nucleo'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        alter table usuarios
          add column intentos_fallidos     smallint    not null default 0,
          add column bloqueado_hasta       timestamptz,
          add column password_cambiado_en  timestamptz,
          add column debe_cambiar_password boolean     not null default true
    """)
    op.execute("create index if not exists ix_auditoria_usuario "
               "on auditoria (usuario_id, ocurrido_en desc)")
    op.execute("create index if not exists ix_auditoria_entidad "
               "on auditoria (entidad, entidad_id, ocurrido_en desc)")
    op.execute("""
        create or replace function auditoria_inalterable() returns trigger
        language plpgsql as $$
        begin
          raise exception 'La auditoría es inalterable (RNF-05): % no está permitido', tg_op
            using errcode = 'insufficient_privilege';
        end $$
    """)
    op.execute("""
        create trigger tg_auditoria_sin_cambios
          before update or delete on auditoria
          for each row execute function auditoria_inalterable()
    """)
    op.execute("""
        create trigger tg_auditoria_sin_truncate
          before truncate on auditoria
          for each statement execute function auditoria_inalterable()
    """)


def downgrade() -> None:
    op.execute('drop trigger if exists tg_auditoria_sin_truncate on auditoria')
    op.execute('drop trigger if exists tg_auditoria_sin_cambios on auditoria')
    op.execute('drop function if exists auditoria_inalterable()')
    op.execute('drop index if exists ix_auditoria_entidad')
    op.execute('drop index if exists ix_auditoria_usuario')
    op.execute("""
        alter table usuarios
          drop column if exists debe_cambiar_password,
          drop column if exists password_cambiado_en,
          drop column if exists bloqueado_hasta,
          drop column if exists intentos_fallidos
    """)
