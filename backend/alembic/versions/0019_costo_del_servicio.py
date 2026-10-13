"""Lo que a la agencia le cuesta prestar cada servicio (RF-054).

La rentabilidad es el ingreso menos lo que se fue. Tres de esas restas ya se
podian hacer: la comision de la vendedora, los gastos cargados a la venta y lo
que se lleva la pasarela cuando el cliente paga con tarjeta. Faltaba la mas
grande: lo que cuesta ATENDER el servicio. Si asesorar una visa premium le
cuesta a la agencia $180.000 entre el tramitador y el traductor, una venta de
$1.100.000 con $77.000 de comision no deja $1.023.000; deja $843.000. Sin esta
tabla el margen sale inflado en exactamente esa plata y las decisiones de precio
se toman sobre un numero que no existe.

**Por que el costo tiene vigencia y no es una columna del servicio.** El costo
sube: el tramitador cobraba $120.000 el ano pasado y cobra $180.000 hoy. Con una
sola columna, subirle el costo hoy reescribiria el margen de todas las ventas
del ano pasado, y el historico dejaria de cuadrar con lo que la agencia reporto
en su momento. Con vigencia, cada venta se mide con el costo que regia el dia
que se vendio: es la misma razon por la que `tarifas` tiene vigencia y por la
que la comision guarda su regla congelada (RN-07).

**Por que varias filas por servicio.** El costo no es un numero redondo, es una
lista: tramitador, traduccion, mensajeria fija. En una sola cifra nadie puede
responder «y por que nos cuesta tanto». En filas con concepto, si.

**Por que `por_persona`.** La venta es grupal (PREMIUM x 3). El traductor cobra
por cada solicitante; el tramitador, una vez por la familia. Las dos cosas son
costos del mismo servicio y tienen que poder convivir, igual que en `tarifas`.

Esto NO es el saldo ni el margen: aqui solo se guarda lo que cuesta, que es un
dato que alguien escribe. La resta se hace al preguntar (RN-01).

Revision ID: 0019_costo_del_servicio
Revises: 0018_colaboradores_caso
"""
from alembic import op

revision = '0019_costo_del_servicio'
down_revision = '0018_colaboradores_caso'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        create table costos_servicio (
          id            smallserial primary key,
          servicio_id   int          not null references servicios (id),
          concepto      varchar(120) not null,
          monto         numeric(14,2) not null check (monto >= 0),
          moneda        char(3)      not null default 'COP',
          modalidad     varchar(12)  not null default 'total'
                        check (modalidad in ('total','por_persona')),
          vigente_desde date         not null,
          vigente_hasta date,
          activo        boolean      not null default true,
          observacion   text,
          creado_en     timestamptz  not null default now(),
          constraint ck_costos_servicio_vigencia
            check (vigente_hasta is null or vigente_hasta >= vigente_desde)
        )
    """)
    # Un mismo concepto no puede empezar a regir dos veces el mismo dia para el
    # mismo servicio: si pasara, el margen dependeria de cual de las dos filas
    # leyera la consulta.
    op.execute("""create unique index ux_costos_servicio
                  on costos_servicio (servicio_id, concepto, vigente_desde)""")
    # La pregunta de la rentabilidad siempre es «los costos de ESTE servicio
    # vigentes ESE dia».
    op.execute("""create index ix_costos_servicio_vigencia
                  on costos_servicio (servicio_id, vigente_desde, vigente_hasta)""")

    # RLS como todas las demas (migracion 0015): la tabla queda cerrada a
    # internet y solo entra la aplicacion.
    op.execute('alter table costos_servicio enable row level security')
    op.execute('alter table costos_servicio force row level security')


def downgrade() -> None:
    op.execute('drop table if exists costos_servicio')
