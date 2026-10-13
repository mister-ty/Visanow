"""Buscar un pago por su referencia sin recorrer la tabla entera (RF-029).

RF-029 pide que la misma caja de busqueda encuentre tambien por «referencia de
pago»: el numero que el cliente manda en el pantallazo de la transferencia. Es
lo que la administradora tiene a mano cuando le escriben «ya pague, el
comprobante dice 00123456789».

Se busca por pedazo y sin distinguir mayusculas, porque nadie copia la
referencia completa: lo normal es acordarse de los ultimos digitos, o pegar un
trozo del mensaje del banco. Eso en SQL es un `ilike '%...%'`, y para esa
pregunta un indice corriente no sirve de nada: PostgreSQL no lo puede usar y
recorre la tabla fila por fila.

Por eso se indexa por trigramas, que es la misma tecnica con la que ya se
buscan los nombres de clientes y solicitantes (migracion 0004) y por la misma
razon.

Hoy son 583 pagos con referencia y el recorrido completo no se siente. El
problema es que esa cuenta solo crece, y esta consulta se dispara con cada
letra que alguien escribe en el buscador: es el tipo de lentitud que no se nota
el dia que se escribe y se vuelve insoportable sin que nadie cambie nada.

El extracto del banco trae su propia referencia y en la bandeja de conciliacion
se filtra igual, asi que lleva el mismo indice por la misma razon.

No hay tablas nuevas, asi que no hay RLS que activar: las dos tablas ya la
tienen desde la migracion 0015.

Revision ID: 0021_referencia_de_pago
Revises: 0020_cartera_por_edades
Create Date: 2026-10-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0021_referencia_de_pago'
down_revision: Union[str, None] = '0020_cartera_por_edades'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# El indice es parcial: la mayoria de los pagos viejos no trae referencia, y
# una fila sin referencia no se puede encontrar por referencia.
TABLAS = ('pagos', 'movimientos_banco')


def upgrade() -> None:
    # pg_trgm ya viene con el nucleo (db/schema/001_nucleo.sql); se repite el
    # «if not exists» para que la migracion se sostenga sola si algun dia se
    # aplica sobre una base armada de otra forma.
    op.execute('create extension if not exists pg_trgm')
    for tabla in TABLAS:
        op.execute(f'create index ix_{tabla}_referencia on {tabla} '
                   f'using gin (referencia gin_trgm_ops) where referencia is not null')


def downgrade() -> None:
    for tabla in TABLAS:
        op.execute(f'drop index if exists ix_{tabla}_referencia')
