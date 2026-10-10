"""Colaboradores de un tramite (RF-026).

Un tramite tiene un responsable -el que responde por el- y a veces alguien mas
que trabaja en el: quien acompana una cita, quien cubre una incapacidad, quien
atiende al cliente mientras el responsable esta fuera.

Hasta hoy solo existia `casos.responsable_id`. Quien tenia alcance limitado solo
veia los tramites de los que era responsable, asi que ayudar en un tramite ajeno
era imposible sin que se lo reasignaran: y reasignar cambia quien responde, que
no es lo mismo que ayudar.

El responsable sigue siendo uno solo a proposito. RN-04 pide que todo tramite
activo tenga responsable, y un tramite con tres duenos no tiene ninguno.

Revision ID: 0018_colaboradores_caso
Revises: 0017_nombre_alerta_saas
"""
from alembic import op

revision = '0018_colaboradores_caso'
down_revision = '0017_nombre_alerta_saas'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        create table casos_colaboradores (
          caso_id      bigint      not null references casos (id) on delete cascade,
          usuario_id   bigint      not null references usuarios (id),
          agregado_por bigint               references usuarios (id),
          agregado_en  timestamptz not null default now(),
          primary key (caso_id, usuario_id)
        )
    """)
    # El indice al derecho lo da la llave primaria; este es para la otra
    # pregunta, que es la que hace la pantalla: «en que tramites colaboro yo».
    op.execute('create index ix_casos_colaboradores_usuario '
               'on casos_colaboradores (usuario_id, caso_id)')

    # RLS como todas las demas (migracion 0015): la tabla queda cerrada a
    # internet y solo entra la aplicacion.
    op.execute('alter table casos_colaboradores enable row level security')
    op.execute('alter table casos_colaboradores force row level security')


def downgrade() -> None:
    op.execute('drop table if exists casos_colaboradores')
