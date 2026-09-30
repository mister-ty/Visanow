"""Las comprobaciones que la migración tiene que pasar para darse por buena.

Se corren contra la base que sea: la de desarrollo mientras se depura con
VisaNow, y la de producción el día de la carga. Por eso viven aquí y no en la
suite de pruebas, que corre contra una base desechable y deshace cada
transacción al terminar.

Cada comprobación contesta una pregunta que, si se responde mal, nadie nota
hasta que el sistema está en uso: ¿la cartera cuadra?, ¿las citas quedaron a la
hora que dice el Excel?, ¿los abonos se volvieron filas?, ¿alguien corrió la
migración dos veces?
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class Comprobacion:
    que: str
    paso: bool
    detalle: str


def _uno(db: Session, sql: str):
    return db.execute(text(sql)).scalar()


def correr(db: Session) -> list[Comprobacion]:
    r: list[Comprobacion] = []

    def anotar(que: str, paso: bool, detalle: str) -> None:
        r.append(Comprobacion(que, paso, detalle))

    # --- RN-01: el saldo sale de la vista, nunca de una columna
    fila = db.execute(text('select coalesce(sum(valor_pactado),0), coalesce(sum(total_pagado),0), '
                           'coalesce(sum(saldo),0) from v_estado_financiero')).first()
    pactado, pagado, saldo = (float(x) for x in fila)
    anotar('El saldo lo calcula la vista y cuadra con ventas menos pagos',
           abs(saldo - (pactado - pagado)) < 1,
           f'pactado {pactado:,.0f} - pagado {pagado:,.0f} = {pactado - pagado:,.0f}; '
           f'la vista dice {saldo:,.0f}')

    anotar('Queda cartera por cobrar', saldo > 0, f'cartera: {saldo:,.0f}')

    negativos = _uno(db, 'select count(*) from v_estado_financiero where saldo < 0')
    monto_neg = float(_uno(db, 'select coalesce(sum(saldo),0) from v_estado_financiero '
                               'where saldo < 0') or 0)
    anotar('Ninguna venta quedó con saldo a favor del cliente', negativos == 0,
           f'{negativos} ventas con saldo negativo por {monto_neg:,.0f}. No es un error de la '
           f'carga: el Excel registra más pagos que el valor cobrado. Salen listadas en la '
           f'pestaña «PLANTILLA precio pactado» del reporte.')

    # --- RN-02: los abonos son filas, no columnas
    con_varios = _uno(db, 'select count(*) from (select negocio_id from pagos '
                          'group by negocio_id having count(*) >= 2) x')
    anotar('Las columnas Abono 1/2/3 se volvieron filas de pagos', con_varios > 0,
           f'{con_varios} ventas tienen dos o más pagos registrados')

    # --- RN-10: la zona horaria no se perdió
    #
    # No se puede comprobar contando citas de madrugada: el Excel trae siete que
    # de verdad dicen la 1:45 y las 5:15, y esas son un dato malo del archivo, no
    # una zona horaria perdida. Lo que sí delata el error es la forma del
    # conjunto: si las fechas hubieran entrado sin zona, TODAS se habrían corrido
    # cinco horas y el grueso de las citas caería de madrugada en vez de en
    # horario de consulado.
    con_hora = _uno(db, """select count(*) from citas
                            where origen_archivo is not null
                              and (extract(hour from inicia_en at time zone 'America/Bogota') <> 0
                                   or extract(minute from inicia_en at time zone 'America/Bogota') <> 0)""")
    en_horario = _uno(db, """select count(*) from citas
                              where origen_archivo is not null
                                and extract(hour from inicia_en at time zone 'America/Bogota')
                                    between 6 and 18""")
    proporcion = en_horario / con_hora if con_hora else 0
    anotar('Las citas quedaron en horario de consulado, no corridas cinco horas',
           proporcion >= 0.9,
           f'{en_horario} de {con_hora} citas con hora caen entre las 6 y las 18 '
           f'({proporcion:.0%}). Si la zona se hubiera perdido, el grueso estaría de madrugada.')

    # --- integridad de lo migrado
    huerfanos = _uno(db, """select count(*) from casos c
                             left join solicitantes s on s.id = c.solicitante_id
                            where c.origen_archivo is not null and s.id is null""")
    anotar('Todo trámite migrado cuelga de una persona', huerfanos == 0,
           f'{huerfanos} trámites sin persona')

    sin_cliente = _uno(db, """select count(*) from solicitantes
                               where origen_archivo is not null
                                 and cliente_id is null and grupo_id is null""")
    anotar('Toda persona migrada cuelga de un cliente o de un grupo', sin_cliente == 0,
           f'{sin_cliente} personas sueltas')

    pagos_sueltos = _uno(db, """select count(*) from pagos
                                 where origen_archivo is not null and negocio_id is null""")
    anotar('Todo pago migrado está asignado a una venta', pagos_sueltos == 0,
           f'{pagos_sueltos} pagos sin venta')

    # --- la carga no se duplicó
    dobles = _uno(db, """select count(*) from (
                             select origen_archivo, origen_hoja, origen_fila
                               from casos where origen_archivo is not null
                              group by 1, 2, 3 having count(*) > 1) x""")
    anotar('Ninguna fila de Excel produjo dos trámites', dobles == 0,
           f'{dobles} filas duplicadas. Si sale distinto de cero, la migración se corrió dos '
           'veces sin el control de idempotencia.')

    clientes_dobles = _uno(db, """select count(*) from (
                                      select lower(nombre_busqueda) n from clientes
                                       where origen_archivo is not null
                                       group by 1 having count(*) > 1) x""")
    anotar('Ningún cliente quedó cargado dos veces', clientes_dobles == 0,
           f'{clientes_dobles} nombres repetidos entre los clientes migrados')

    # --- lo que quedó pendiente de asignar: es información, no un error
    sin_resp = _uno(db, "select count(*) from casos where origen_archivo is not null "
                        "and responsable_id is null")
    anotar('Los trámites sin responsable quedan identificados', True,
           f'{sin_resp} trámites entran a la bandeja «sin asignar». RN-04 pide responsable: la '
           'migración no lo inventa, lo reparte VisaNow el día de la carga.')

    sin_hora = _uno(db, "select count(*) from citas where origen_archivo is not null "
                        "and estado = 'pendiente'")
    anotar('Las citas sin hora quedan marcadas como pendientes', True,
           f'{sin_hora} citas sin hora en el archivo, marcadas para completar en vez de '
           'inventarles una hora.')

    return r
