"""Distinguir un grupo familiar de uno de viaje (RF-003).

RF-003 pide «grupos familiares o de viaje» y la tabla no tenia con que
distinguirlos: solo nombre y observaciones. El tipo quedaba en lo que alcanzara
a escribir quien creara el grupo, asi que hoy la unica forma de saber si
«Promocion 2026» es una familia o un curso que viaja junto es leer el nombre y
adivinar.

Por que importa, y no es un dato decorativo: las dos cosas se atienden distinto
y se cobran distinto. La familia viaja con menores -que llevan su propio
papeleo-, renueva junta y vuelve cada diez anos; el grupo de viaje es una vez,
son adultos y el contacto suele ser quien organiza, no un pariente. Sin la
columna no se puede responder cuanto de la operacion es cada cosa, que es la
cuenta con la que se decide donde poner la publicidad.

Por que arranca en 'familiar': las 895 personas que ya estan cargadas son
familias -es el negocio de VisaNow hasta hoy- y dejar la columna nula obligaria
a toda consulta a tratar el nulo como un tercer tipo que no existe en el
requisito. Quien cree un grupo de viaje lo dice al crearlo, o lo corrige
despues, que para eso el grupo ya se puede editar.

Por que un check y no texto libre: si el tipo se escribiera a mano, manana
habria «Familiar», «fam» y «familia» y el conteo por tipo no se podria hacer.
Es la misma razon por la que los estados y las modalidades viven en catalogo.
Son dos valores que salen del requisito y no los define la agencia, asi que un
check basta y no hace falta una tabla nueva.

No hay tablas nuevas, asi que no hay RLS que activar: `grupos` ya la tiene
desde la migracion 0015.

Por que es la 0029 y no la 0022, con la que nacio: se escribio en paralelo con
la 0027 y la 0028, y las tres declaraban la 0021 como anterior. Al mezclar,
alembic se quedo con dos cabezas y `upgrade head` deja de funcionar: el
despliegue se cae en el paso de migrar, antes de tocar un dato, y la suite
entera no arranca porque el conftest tambien hace `upgrade head`.

Encadenarla DESPUES de la 0028 y no antes no es cosmetico. Produccion ya aplico
la 0027 y la 0028; si esta se colara en medio de la fila, alembic la daria por
aplicada sin haberla corrido nunca -el registro guarda la cabeza, no la lista- y
la columna `grupos.tipo` no existiria mientras el sistema cree que si. Un numero
mas alto es lo unico que garantiza que corra.

Revision ID: 0029_grupo_familiar_o_de_viaje
Revises: 0028_cerrar_los_roles_publicos
Create Date: 2026-10-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0029_grupo_familiar_o_de_viaje'
down_revision: Union[str, None] = '0028_cerrar_los_roles_publicos'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        alter table grupos
          add column tipo varchar(10) not null default 'familiar'
          constraint ck_grupos_tipo check (tipo in ('familiar','viaje'))
    """)


def downgrade() -> None:
    op.execute('alter table grupos drop column if exists tipo')
