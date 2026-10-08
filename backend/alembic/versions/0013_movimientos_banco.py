"""El extracto bancario, para conciliar los pagos contra el banco (RF-044).

La administradora explicó el 07/10 cómo lo resuelve hoy: «el cliente manda el
soporte por whatsapp y también me llega la notificación del correo, entonces a
veces el nombre es el de ellos otras veces es de otra persona, pero a la final el
cliente nos avisa y nos comparte el pantallazo».

De ahí salen las dos decisiones de diseño de esta tabla:

**El nombre de quien consigna no sirve para cruzar.** Muchas veces no es el del
cliente —paga el esposo, la mamá, un amigo—, así que cruzar por nombre produciría
asignaciones falsas, que es peor que no asignar. El cruce automático va por
**valor y fecha**, y lo que no cruce solo se queda a la vista para que alguien lo
asigne a mano. La descripción del banco se guarda, pero como información, no como
llave: en el extracto real 182 de 192 movimientos dicen apenas «TRANSFERENCIA CTA
SUC VIRTUAL».

**No todo movimiento es un pago de cliente.** En el extracto real hay intereses
de ahorro de 5 pesos, reversos de compras y plata personal. Por eso existe
`descartado` con su motivo: un movimiento que no es de un cliente tiene que poder
salir de la bandeja sin inventarle un pago, y dejando dicho por qué.

Las columnas `nota_cliente` y `nota_abono` guardan lo que ella venía anotando a
mano en las columnas CLIENTE y ABONO de la hoja EXTRACTO. No se usan para cruzar
—son texto libre, «GEORGINA GARCIA, ESPOSO E HIJO»— pero son la pista con la que
ella reconoce el movimiento, así que se conservan y se muestran.

La `huella` hace que importar dos veces el mismo extracto no duplique nada, que
es la misma garantía que ya tiene la migración de los Excel.

Revision ID: 0013_movimientos_banco
Revises: 0012_regla_confirmada
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0013_movimientos_banco'
down_revision: Union[str, None] = '0012_regla_confirmada'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        create table movimientos_banco (
            id              bigserial primary key,
            banco           varchar(60)  not null,
            banco_cuenta_id smallint     references bancos_cuentas(id),
            fecha           date         not null,
            descripcion     varchar(300),
            valor           numeric(14,2) not null,
            moneda          char(3)      not null default 'COP',
            referencia      varchar(120),

            estado          varchar(20)  not null default 'sin_conciliar',
            pago_id         bigint       references pagos(id),
            motivo_descarte varchar(300),
            -- El banco a veces reporta dos veces la misma transferencia. Se
            -- marca la repetida y se apunta a la buena, para que la suma del
            -- extracto siga cuadrando sin contar la plata dos veces.
            duplicado_de_id bigint       references movimientos_banco(id),

            -- Lo que la administradora anotaba a mano en el Excel: no se cruza
            -- con esto, pero es la pista con la que ella reconoce el movimiento.
            nota_cliente    varchar(200),
            nota_abono      varchar(60),
            observacion     text,

            huella          char(64)     not null,
            origen_archivo  varchar(120),
            origen_hoja     varchar(60),
            origen_fila     integer,

            conciliado_por  bigint       references usuarios(id),
            conciliado_en   timestamptz,
            creado_en       timestamptz  not null default now(),

            constraint movimientos_banco_estado_check
                check (estado in ('sin_conciliar', 'conciliado', 'parcial',
                                  'duplicado', 'reversado', 'descartado')),
            -- Cuadrado sin pago sería decir que cuadra contra nada. «parcial»
            -- también apunta a un pago: es el que cubre una parte.
            constraint movimientos_banco_conciliado_check
                check (estado not in ('conciliado', 'parcial') or pago_id is not null),
            -- Sacar plata del extracto sin explicación es perderle el rastro.
            constraint movimientos_banco_motivo_check
                check (estado not in ('descartado', 'reversado')
                       or (motivo_descarte is not null and btrim(motivo_descarte) <> '')),
            -- Una repetida tiene que decir de cuál es repetida.
            constraint movimientos_banco_duplicado_check
                check (estado <> 'duplicado' or duplicado_de_id is not null),
            constraint movimientos_banco_no_se_duplica_a_si_mismo
                check (duplicado_de_id is null or duplicado_de_id <> id)
        )
    """)
    # Importar dos veces el mismo extracto no puede duplicar movimientos.
    op.execute('create unique index ux_movimientos_banco_huella '
               'on movimientos_banco (huella)')
    # La bandeja se ordena por fecha, y el cruce busca por valor y fecha.
    op.execute('create index ix_movimientos_banco_bandeja '
               'on movimientos_banco (estado, fecha desc)')
    op.execute('create index ix_movimientos_banco_cruce '
               'on movimientos_banco (valor, fecha) where estado = \'sin_conciliar\'')
    # Un pago no puede quedar conciliado contra dos movimientos del banco.
    op.execute('create unique index ux_movimientos_banco_pago '
               "on movimientos_banco (pago_id) where pago_id is not null "
               "and estado = 'conciliado'")


def downgrade() -> None:
    op.execute('drop table movimientos_banco')
