"""Ajustes del modelo por las respuestas de la administradora (19/09/2026).

1. El SaaS agrupa a una familia en UNA solicitud con varios solicitantes (la
   solicitud #0d9ccdd3 tiene dos). La llave de importación no puede ser solo el
   número de solicitud: se vuelve número de solicitud + solicitante. Con la
   llave anterior, el segundo miembro de la familia se rechazaba como duplicado.

2. El pasaporte se guarda cifrado (RNF-04) y se busca por un índice ciego
   (RF-029). El token cifrado no cabía en varchar(80).

3. La venta es grupal (PREMIUM x 3 = $3.200.000) y la tasa consular se cobra
   como una venta aparte ("PAGO VISA", cantidad 0). La tasa es plata del
   consulado que VisaNow recauda, no ingreso: servicios.tipo la separa para
   que no infle lo vendido ni la base de comisión.

4. Los precios dependen de cuántas personas viajan: tarifas por número de
   personas, con valor total o por persona, y un valor mínimo de negociación.

5. Anticipo del 20 % o del 80 %; el saldo se paga al agendar la cita y, si no
   se ha pagado al mes, está en mora. El plazo va en parametros, no en código.

6. Una sola persona transfiere por el grupo: pagos.pagador_nombre guarda quién
   aparece en el extracto, que es lo que se usa para identificar el pago.

Revision ID: 0003_respuestas
Revises: 0002_autenticacion
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0003_respuestas'
down_revision: Union[str, None] = '0002_autenticacion'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Llave de importación: solicitud del SaaS + solicitante
    op.execute('drop index if exists ux_casos_id_externo')
    op.execute("""create unique index ux_casos_solicitud_solicitante
                  on casos (id_externo, solicitante_id) where id_externo is not null""")
    op.execute('create index ix_casos_id_externo on casos (id_externo) where id_externo is not null')

    # 2. Pasaporte cifrado y buscable
    op.execute('alter table solicitantes alter column pasaporte type text')
    op.execute('alter table solicitantes add column pasaporte_indice char(64)')
    op.execute("""create unique index ux_solicitantes_pasaporte
                  on solicitantes (pasaporte_indice) where pasaporte_indice is not null""")

    # 3. Servicios: honorario o recaudo de terceros, país por defecto y tasa consular
    op.execute("""
        alter table servicios
          add column tipo varchar(20) not null default 'honorario'
              check (tipo in ('honorario','recaudo_terceros')),
          add column pais_id smallint references paises(id),
          add column crea_casos boolean not null default true,
          add column tasa_consular_valor  numeric(14,2),
          add column tasa_consular_moneda char(3),
          add column tasa_consular_nota   varchar(200)
    """)

    # 4. Tarifas por número de personas
    op.execute("""
        alter table tarifas
          add column personas     smallint not null default 1 check (personas between 1 and 20),
          add column modalidad    varchar(12) not null default 'total'
              check (modalidad in ('total','por_persona')),
          add column valor_minimo numeric(14,2) check (valor_minimo is null or valor_minimo >= 0),
          add constraint ck_tarifas_valor check (valor >= 0),
          add constraint ck_tarifas_vigencia check (vigente_hasta is null or vigente_hasta >= vigente_desde)
    """)
    op.execute("""create unique index ux_tarifas_servicio_personas_vigencia
                  on tarifas (servicio_id, personas, vigente_desde)""")

    # 5. Parámetros del negocio configurables desde la administración
    op.execute("""
        create table parametros (
          clave           varchar(60) primary key,
          valor           jsonb not null,
          descripcion     text not null,
          actualizado_por bigint references usuarios(id),
          actualizado_en  timestamptz not null default now()
        )
    """)

    # 6. Quién pagó, y a qué venta principal pertenece una venta adicional
    op.execute('alter table pagos add column pagador_nombre varchar(160)')
    op.execute("""alter table negocios add column negocio_principal_id bigint
                  references negocios(id)""")
    op.execute("""create index ix_negocios_principal on negocios (negocio_principal_id)
                  where negocio_principal_id is not null""")


def downgrade() -> None:
    op.execute('drop index if exists ix_negocios_principal')
    op.execute('alter table negocios drop column if exists negocio_principal_id')
    op.execute('alter table pagos drop column if exists pagador_nombre')
    op.execute('drop table if exists parametros')
    op.execute('drop index if exists ux_tarifas_servicio_personas_vigencia')
    op.execute("""alter table tarifas drop constraint if exists ck_tarifas_vigencia,
                  drop constraint if exists ck_tarifas_valor, drop column if exists valor_minimo,
                  drop column if exists modalidad, drop column if exists personas""")
    op.execute("""alter table servicios drop column if exists tasa_consular_nota,
                  drop column if exists tasa_consular_moneda, drop column if exists tasa_consular_valor,
                  drop column if exists crea_casos, drop column if exists pais_id,
                  drop column if exists tipo""")
    op.execute('drop index if exists ux_solicitantes_pasaporte')
    op.execute('alter table solicitantes drop column if exists pasaporte_indice')
    op.execute('alter table solicitantes alter column pasaporte type varchar(80)')
    op.execute('drop index if exists ix_casos_id_externo')
    op.execute('drop index if exists ux_casos_solicitud_solicitante')
    op.execute("""create unique index ux_casos_id_externo on casos (id_externo)
                  where id_externo is not null""")
