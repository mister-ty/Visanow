"""Corrige el índice de origen donde una fila de Excel produce varios registros.

La migración 0007 puso un índice único sobre (origen_archivo, origen_hoja,
origen_fila) en nueve tablas, dando por hecho que cada fila de Excel produce un
registro. Es cierto en dos de ellas y falso en el resto:

- una fila de `PAGOS` trae hasta tres abonos, y cada abono es una fila de `pagos`
  (que es justamente lo que resuelve RN-02);
- una fila de la hoja `2026` trae la cita del CAS y la de la entrevista, y cada
  una es una fila de `citas`;
- una celda de cliente puede traer dos personas («Ana Gómez y Luis Gómez»), así
  que una misma fila origina dos clientes y dos solicitantes.

Con el índice puesto, la carga fallaba en el segundo abono de la primera venta.
Se deja solo donde la relación sí es uno a uno: `casos` y `negocios`.

La idempotencia no se pierde: no vivía en estos índices sino en
`migracion_filas`, que registra cada fila de Excel con su huella y permite
reconocer lo ya cargado. Estos índices eran un refuerzo, y un refuerzo que
impide cargar los datos correctos no refuerza nada.

Revision ID: 0008_origen_1n
Revises: 0007_migracion
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0008_origen_1n'
down_revision: Union[str, None] = '0007_migracion'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Una fila de Excel produce varios registros en estas tablas
UNO_A_VARIOS = ('clientes', 'solicitantes', 'pagos', 'citas', 'actividades', 'cuotas_negocio',
                'grupos')
# ...y uno solo en estas
UNO_A_UNO = ('casos', 'negocios')


def upgrade() -> None:
    for tabla in UNO_A_VARIOS:
        op.execute(f'drop index if exists ux_{tabla}_origen')
        # Se conserva como índice normal: sirve para rastrear de dónde salió
        # cada registro, que era el propósito original de estas columnas.
        op.execute(f"""
            create index if not exists ix_{tabla}_origen
                on {tabla} (origen_archivo, origen_hoja, origen_fila)
             where origen_archivo is not null
        """)


def downgrade() -> None:
    for tabla in UNO_A_VARIOS:
        op.execute(f'drop index if exists ix_{tabla}_origen')
        op.execute(f"""
            create unique index if not exists ux_{tabla}_origen
                on {tabla} (origen_archivo, origen_hoja, origen_fila)
             where origen_archivo is not null
        """)
