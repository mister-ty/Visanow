"""Control de la migración desde los Excel: poder correrla dos veces sin duplicar.

La migración lee 17 hojas de tres libros y escribe en nueve tablas. Sin una
clave que diga «esta fila ya la cargué», correrla dos veces duplica todo en
silencio, que es peor que fallar: nadie se entera hasta que la cartera está al
doble.

Las columnas `origen_archivo`, `origen_hoja` y `origen_fila` ya existían en
clientes, solicitantes, casos, negocios y pagos, pero sin restricción: servían
para rastrear, no para impedir. Aquí se completan en las tablas que faltaban y
se convierten en una clave de verdad.

La idempotencia NO se puede montar sobre esas columnas en `clientes`: un cliente
sale de varias filas de varias hojas (971 menciones que colapsan en unos 800
clientes), así que su `origen_*` guarda la fila que lo creó, nada más. Por eso
el control vive en `migracion_filas`, una fila por cada fila de Excel leída, que
dice qué se hizo con ella y qué registros produjo.

No se reutiliza `importaciones_filas` porque esa tabla es de la importación del
SaaS (actividad 5.1): solo enlaza `caso_id` y cuelga de una importación con
`archivo_sha256`. La migración produce clientes, personas, trámites, citas,
ventas y pagos desde una misma fila.

Revision ID: 0007_migracion
Revises: 0006_indice_ds160
Create Date: 2026-09-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0007_migracion'
down_revision: Union[str, None] = '0006_indice_ds160'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tablas que ya tenían las columnas de origen y las que había que completar
CON_ORIGEN = ('clientes', 'solicitantes', 'casos', 'negocios', 'pagos')
SIN_ORIGEN = ('grupos', 'citas', 'actividades', 'cuotas_negocio')


def upgrade() -> None:
    for tabla in SIN_ORIGEN:
        op.execute(f"""
            alter table {tabla}
              add column if not exists origen_archivo varchar(80),
              add column if not exists origen_hoja    varchar(60),
              add column if not exists origen_fila    integer
        """)

    # Índice parcial: solo aplica a lo migrado. Lo que se crea desde la
    # aplicación tiene los tres campos nulos y no lo toca.
    for tabla in CON_ORIGEN + SIN_ORIGEN:
        op.execute(f"""
            create unique index if not exists ux_{tabla}_origen
                on {tabla} (origen_archivo, origen_hoja, origen_fila)
             where origen_archivo is not null
        """)

    op.execute("""
        create table migracion_corridas (
            id            bigserial primary key,
            modo          varchar(16)  not null,
            iniciada_en   timestamptz  not null default now(),
            terminada_en  timestamptz,
            ejecutada_por bigint references usuarios(id),
            resumen       jsonb        not null default '{}'::jsonb,
            constraint ck_migracion_modo
                check (modo in ('previsualizacion', 'aplicacion'))
        )
    """)
    op.execute("comment on table migracion_corridas is "
               "'Cada ejecución de la migración desde los Excel. La previsualización no escribe "
               "datos: deja la corrida y sus filas para poder revisarla antes de aplicar.'")

    op.execute("""
        create table migracion_filas (
            id             bigserial primary key,
            corrida_id     bigint      not null references migracion_corridas(id) on delete cascade,
            archivo        varchar(80) not null,
            hoja           varchar(60) not null,
            fila           integer     not null,
            huella         char(64)    not null,
            resultado      varchar(15) not null,
            motivo         text,
            cliente_id     bigint references clientes(id),
            solicitante_id bigint references solicitantes(id),
            caso_id        bigint references casos(id),
            negocio_id     bigint references negocios(id),
            constraint ck_migracion_filas_resultado
                check (resultado in ('creado', 'actualizado', 'sin_cambios', 'excepcion', 'omitido'))
        )
    """)
    # Una fila de Excel se carga una sola vez, sin importar cuántas corridas haya.
    # La previsualización usa corridas aparte y se borra al aplicar.
    op.execute("""
        create unique index ux_migracion_filas_origen
            on migracion_filas (archivo, hoja, fila, corrida_id)
    """)
    op.execute("create index ix_migracion_filas_corrida on migracion_filas (corrida_id, resultado)")
    op.execute("create index ix_migracion_filas_huella on migracion_filas (huella)")
    op.execute("comment on column migracion_filas.huella is "
               "'sha256 del contenido normalizado de la fila. Si cambia, el Excel se editó "
               "después de migrar y la fila se vuelve a mirar.'")


def downgrade() -> None:
    op.execute('drop table if exists migracion_filas')
    op.execute('drop table if exists migracion_corridas')
    for tabla in CON_ORIGEN + SIN_ORIGEN:
        op.execute(f'drop index if exists ux_{tabla}_origen')
    for tabla in SIN_ORIGEN:
        op.execute(f'alter table {tabla} drop column if exists origen_archivo, '
                   f'drop column if exists origen_hoja, drop column if exists origen_fila')
