"""Las reglas de comisión, con lo que confirmó la administradora el 07/10/2026.

Tres cosas cambian, y las tres mueven plata:

**El escalón del 10 % aplica sobre un solo servicio.** Decía «el servicio de usa
premium, solo ese es el que aplica para las 10 (no aplica renovación premium o
china premium)». Estaba sembrado contando también `renovacion_premium`, que ella
excluyó de forma explícita. El servicio que sí es son los `asesoria_adelanto`
—«Asesoría USA + adelanto (Premium)»—, el más vendido del catálogo con 156
ventas. La fila `usa_premium` del catálogo viejo no es: no tiene ni una venta ni
una tarifa, es un registro muerto.

**Yas comisiona el 4 %, no el 7 %.** Estaba sembrado al 7 % y marcado como «por
confirmar». Son 3 puntos sobre cada venta suya.

**Hay regla general, y es del 4 %.** «yas ponle el 4 % de la venta y a los
demás». Hasta ahora quien no tuviera regla propia no comisionaba nada, porque la
respuesta anterior («las comisiones solo son para angie y yas») se leyó como que
nadie más comisionaba. No era eso: el resto del equipo comisiona al 4 %, sin el
escalón, que «solo aplica para angie».

**Las comisiones ya calculadas no se tocan.** RN-07 congela la regla en cada
venta, así que una migración que reescribiera `comisiones` estaría falsificando
el cálculo que se le explicó a alguien. Si hay comisiones sin liquidar calculadas
con la configuración vieja, se corrigen con el recálculo desde la aplicación, que
deja su rastro en auditoría.

**Nota sobre el número.** El 0011 está tomado por la rama `nube/plantillas`, que
todavía no se mezcla. Al mezclarla hay que re-apuntar `0011_plantillas` para que
cuelgue de esta y no de la 0010, o quedan dos cabezas y el despliegue falla.

Revision ID: 0012_regla_confirmada
Revises: 0010_regla_vendedora
Create Date: 2026-10-07
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0012_regla_confirmada'
down_revision: Union[str, None] = '0010_regla_vendedora'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DICHO_07 = 'Administradora VisaNow, WhatsApp del 07/10/2026 (decisión D-03)'

GENERAL = {
    'se_causa_con': 'pago_total',
    'porcentaje_base': 4.0,
    'excluye_de_la_base': ['recaudo_terceros'],
    'es_la_general': True,
    'dicho_por': DICHO_07,
}


def upgrade() -> None:
    con = op.get_bind()

    # El escalón, sobre un solo servicio.
    con.execute(sa.text("""
        update comisiones_reglas
           set nombre = :nombre,
               definicion = definicion || jsonb_build_object(
                   'servicios_que_cuentan_para_la_meta', cast(:cuentan as jsonb),
                   'servicios_excluidos_de_la_meta', cast(:excluidos as jsonb),
                   'dicho_por', cast(:dicho as text))
         where nombre like 'Angie%'
    """), {
        'nombre': 'Angie — 7 % con escalón del 10 % en las primeras 10 USA premium',
        'cuentan': json.dumps(['asesoria_adelanto']),
        'excluidos': json.dumps(['renovacion', 'renovacion_premium',
                                 'visa_china_premium', 'visa_premium_ninos']),
        'dicho': 'Administradora VisaNow, WhatsApp del 03/10 y del 07/10/2026 (D-03)',
    })

    # Yas, al 4 %, y se le quita la marca de «por confirmar» porque ya respondió.
    con.execute(sa.text("""
        update comisiones_reglas
           set nombre = :nombre,
               porcentaje = 4.0,
               definicion = (definicion - 'por_confirmar')
                            || jsonb_build_object('porcentaje_base', 4.0, 'dicho_por', cast(:dicho as text))
         where nombre like 'Yas%'
    """), {'nombre': 'Yas — 4 % del valor de la venta', 'dicho': DICHO_07})

    # La general, si no está. Es la única sin dueña, y lo es a propósito.
    con.execute(sa.text("""
        insert into comisiones_reglas
               (nombre, vendedor_id, base, porcentaje, meta_cantidad,
                vigente_desde, definicion, activo)
        select cast(:nombre as varchar), cast(null as bigint), 'vendido', 4.0,
               cast(null as smallint), date '2026-01-01',
               cast(:definicion as jsonb), true
         where not exists (select 1 from comisiones_reglas
                            where definicion->>'es_la_general' = 'true')
    """), {'nombre': 'General — 4 % del valor de la venta para el resto del equipo',
           'definicion': json.dumps(GENERAL)})


def downgrade() -> None:
    con = op.get_bind()
    con.execute(sa.text("delete from comisiones_reglas "
                        "where definicion->>'es_la_general' = 'true'"))
    con.execute(sa.text("""
        update comisiones_reglas
           set nombre = :nombre, porcentaje = 7.0,
               definicion = definicion || jsonb_build_object('porcentaje_base', 7.0)
         where nombre like 'Yas%'
    """), {'nombre': 'Yas — 7 % (porcentaje por confirmar)'})
    con.execute(sa.text("""
        update comisiones_reglas
           set nombre = :nombre,
               definicion = definicion || jsonb_build_object(
                   'servicios_que_cuentan_para_la_meta', cast(:cuentan as jsonb),
                   'servicios_excluidos_de_la_meta', cast(:excluidos as jsonb))
         where nombre like 'Angie%'
    """), {
        'nombre': 'Angie — 7 % con escalón del 10 % en las primeras 10 premium',
        'cuentan': json.dumps(['asesoria_adelanto', 'renovacion_premium']),
        'excluidos': json.dumps(['renovacion']),
    })
