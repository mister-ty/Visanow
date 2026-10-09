"""Plantillas de mensajes por evento (RF-063).

Hoy los mensajes a clientes (confirmación de cita, recordatorio de saldo) se
escriben a mano o se copian de un chat viejo, y cada asesora los dice distinto.
Esta tabla los guarda una vez, con variables entre llaves dobles, para que el
sistema los llene con los datos del cliente, la cita, el saldo y el responsable.

Se escribio como 0011 colgando de la 0010, pero mientras tanto master gano la
0012 (reglas de comision) y la 0013 (extracto bancario). Se renumero a 0014 y se
re-apunto a la 0013: dos migraciones colgando de la misma dejarian dos cabezas y
`alembic upgrade head` fallaria en el despliegue. Nunca se habia aplicado, asi
que renumerarla no rompe ninguna base.

El evento NO lleva un `check` en la base: el catálogo de eventos vive en el
servicio y crece con el negocio; atarlo a una restricción obligaría a una
migración por cada evento nuevo.

Revision ID: 0014_plantillas
Revises: 0013_movimientos_banco
Create Date: 2026-10-06 (renumerada el 08/10)
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0014_plantillas'
down_revision: Union[str, None] = '0013_movimientos_banco'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        create table plantillas_mensaje (
            id             bigserial primary key,
            evento         varchar(40)  not null,
            nombre         varchar(80)  not null,
            canal          varchar(10)  not null default 'whatsapp',
            asunto         varchar(160),
            cuerpo         text         not null,
            activa         boolean      not null default true,
            creada_por     bigint references usuarios(id),
            creada_en      timestamptz  not null default now(),
            actualizada_en timestamptz  not null default now(),
            constraint ck_plantilla_canal check (canal in ('whatsapp', 'correo', 'sms')),
            constraint ck_plantilla_cuerpo check (length(btrim(cuerpo)) > 0)
        )
    """)
    # Dos plantillas con el mismo nombre para el mismo evento y canal no se
    # distinguen en la lista: la asesora no sabría cuál elegir.
    op.execute("create unique index ux_plantilla_nombre on plantillas_mensaje (evento, canal, nombre)")
    op.execute("create index ix_plantilla_evento on plantillas_mensaje (evento) where activa")
    op.execute("""
        insert into plantillas_mensaje (evento, nombre, canal, cuerpo) values
        ('cita_confirmada', 'Confirmación de cita', 'whatsapp',
         'Hola {{cliente_nombre}}, le confirmamos la cita de {{solicitante_nombre}} ({{cita_tipo}}) el {{cita_fecha}} a las {{cita_hora}} en {{cita_sede}}. Cualquier duda, escríbame. {{responsable_nombre}}, VisaNow.'),
        ('cita_recordatorio', 'Recordatorio de cita', 'whatsapp',
         'Hola {{cliente_nombre}}, le recordamos la cita de {{solicitante_nombre}} ({{cita_tipo}}): {{cita_fecha}}, {{cita_hora}}, {{cita_sede}}. {{responsable_nombre}}, VisaNow.'),
        ('saldo_pendiente', 'Recordatorio de saldo', 'whatsapp',
         'Hola {{cliente_nombre}}, le escribimos de VisaNow: tiene un saldo pendiente de {{saldo}}. Si ya pagó, envíenos el comprobante para registrarlo. {{responsable_nombre}}.'),
        ('pago_recibido', 'Pago recibido', 'whatsapp',
         'Hola {{cliente_nombre}}, recibimos su pago. El saldo pendiente es {{saldo}}. Gracias. {{responsable_nombre}}, VisaNow.')
    """)


def downgrade() -> None:
    op.execute("drop table if exists plantillas_mensaje")
