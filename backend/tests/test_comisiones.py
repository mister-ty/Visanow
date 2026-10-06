"""Actividad 4.5 — gastos y comisiones (RF-050 a RF-054).

La regla la dio la administradora el 03/10/2026: Angie comisiona el 7 % del
valor de la venta; sobre sus primeras diez ventas premium del periodo se le
paga el 10 %; la renovación no cuenta para esas diez; se gana cuando el cliente
termina de pagar; y la base es solo el valor del servicio, porque la tasa
consular la paga el cliente directamente al consulado.

Es la lógica donde un error no falla: solo paga de menos o de más, y nadie se
entera hasta que alguien reclama.
"""
import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models.esquema import (Auditoria, CategoriasGasto, Comisiones,
                                ComisionesReglas, Negocios, Paises, Servicios)
from tests.conftest import entrar


@pytest.fixture
def finanzas(cliente, usuario):
    return entrar(cliente, usuario('finanzas'))


@pytest.fixture
def vendedora(cliente, db, usuario):
    """Una comercial con la regla de Angie, atada a ella por id.

    La regla sembrada se le asigna a esta usuaria de prueba. Antes la fixture se
    llamaba «Angie Lorena» para que el emparejamiento por nombre la encontrara;
    eso probaba la suerte del seed, no el motor.
    """
    p = usuario('comercial')
    p.u.nombre = 'Angie Lorena'
    regla = db.scalars(select(ComisionesReglas)
                       .where(ComisionesReglas.nombre.like('Angie%'))).first()
    regla.vendedor_id = p.u.id
    regla.activo = True
    db.commit()
    return entrar(cliente, p), p


def servicio_id(db, codigo: str) -> int:
    return db.scalar(select(Servicios.id).where(Servicios.codigo == codigo))


def vender(cliente, cab, db, *, servicio: str, nombre: str, fecha: str | None = None,
           valor: float | None = None):
    """Una venta completa por el camino normal: cliente, persona, lead, ganar."""
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': nombre}).json()
    cliente.post('/api/v1/solicitantes', headers=cab,
                 json={'cliente_id': c['id'], 'nombre': nombre})
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    lead = cliente.post('/api/v1/oportunidades', headers=cab, json={
        'cliente_id': c['id'], 'servicio_id': servicio_id(db, servicio), 'pais_id': pais,
        'proxima_accion': 'Cotizar'}).json()
    cuerpo = {}
    if fecha:
        cuerpo['fecha_venta'] = fecha
    if valor is not None:
        cuerpo['valor_pactado'] = valor
    r = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


def comision_de(cliente, cab, negocio_id):
    todas = cliente.get('/api/v1/comisiones', headers=cab).json()
    return next((c for c in todas if c['negocio_id'] == negocio_id), None)


# ------------------------------------------------------------ el porcentaje

def test_la_comision_base_es_el_siete_por_ciento_del_valor_de_la_venta(cliente, vendedora,
                                                                        finanzas, db):
    cab, _ = vendedora
    venta = vender(cliente, cab, db, servicio='asesoria_usa', nombre='Nora Pineda Gil')
    c = comision_de(cliente, finanzas, venta['id'])

    assert c is not None, 'la venta tiene que nacer con su comisión provisional'
    assert c['porcentaje_aplicado'] == 7.0
    assert c['base_calculo'] == venta['valor_pactado']
    assert c['monto'] == pytest.approx(venta['valor_pactado'] * 0.07, abs=1)
    assert c['estado'] == 'provisional'


def test_las_primeras_diez_premium_del_mes_van_al_diez_por_ciento(cliente, vendedora,
                                                                   finanzas, db):
    """Es el escalón que dio la administradora, y donde está la plata: entre el
    7 % y el 10 % sobre diez ventas hay una diferencia que se nota."""
    cab, _ = vendedora
    montos = []
    for i in range(12):
        venta = vender(cliente, cab, db, servicio='asesoria_adelanto',
                       nombre=f'Cliente Premium{i:02d} Apellido{i:02d}',
                       fecha=f'2026-11-{i + 1:02d}')
        c = comision_de(cliente, finanzas, venta['id'])
        montos.append((i + 1, c['porcentaje_aplicado'], c['escalon'], c['explicacion']))

    primeras = [p for n, p, _, _ in montos if n <= 10]
    despues = [p for n, p, _, _ in montos if n > 10]
    assert primeras == [10.0] * 10, f'las primeras diez van al 10 %: {primeras}'
    assert despues == [7.0, 7.0], f'de la once en adelante vuelve al 7 %: {despues}'
    assert montos[0][2] == 'meta' and montos[10][2] == 'base'
    assert 'n.º 11' in montos[10][3], 'la explicación dice qué posición ocupó'


def test_la_renovacion_no_cuenta_para_las_diez_premium(cliente, vendedora, finanzas, db):
    """Lo dijo explícito: «no aplica renovación». Si contara, una renovación
    barata consumiría un cupo del 10 % que le corresponde a una venta grande."""
    cab, _ = vendedora
    for i in range(3):
        vender(cliente, cab, db, servicio='renovacion',
               nombre=f'Renovador Numero{i} Apellido{i}', fecha=f'2026-12-0{i + 1}')
    premium = vender(cliente, cab, db, servicio='asesoria_adelanto',
                     nombre='Primera Premium Delmes', fecha='2026-12-10')

    c = comision_de(cliente, finanzas, premium['id'])
    assert c['porcentaje_aplicado'] == 10.0
    assert 'n.º 1' in c['explicacion'], 'las renovaciones no gastaron cupo'


def test_el_contador_de_las_diez_arranca_de_cero_cada_mes(cliente, vendedora, finanzas, db):
    cab, _ = vendedora
    ultima_de_enero = None
    for i in range(11):
        ultima_de_enero = vender(cliente, cab, db, servicio='asesoria_adelanto',
                                 nombre=f'Enero Cliente{i:02d} Apellido{i:02d}',
                                 fecha=f'2027-01-{i + 1:02d}')
    primera_de_febrero = vender(cliente, cab, db, servicio='asesoria_adelanto',
                                nombre='Febrero Primer Cliente', fecha='2027-02-02')

    assert comision_de(cliente, finanzas, ultima_de_enero['id'])['porcentaje_aplicado'] == 7.0
    assert comision_de(cliente, finanzas, primera_de_febrero['id'])['porcentaje_aplicado'] == 10.0


def test_la_tasa_consular_no_comisiona(cliente, vendedora, finanzas, db):
    """Son 39 ventas por 40 millones en los archivos. Si entraran en la base, la
    comisión saldría inflada el 11,7 %."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, servicio='pago_visa', nombre='Tasa Consular Cliente')
    assert comision_de(cliente, finanzas, venta['id']) is None, \
        'el recaudo de terceros no genera comisión'


# ------------------------------------------------- de quien es cada regla
#
# La administradora fue explicita: «las comisiones solo son para angie y yas,
# miriam no hace ventas». Antes las reglas se sembraban sin dueña y `regla_para`
# adivinaba por el primer nombre; cuando no adivinaba —«Isa» contra la regla
# «Yas — 7 %…»— repartia el escalon del 10 % de Angie a quien fuera.

def _comercial_con_regla(cliente, db, usuario, patron):
    """Una comercial a la que se le asigna la regla sembrada que se pida."""
    p = usuario('comercial')
    regla = db.scalars(select(ComisionesReglas)
                       .where(ComisionesReglas.nombre.like(patron))).first()
    regla.vendedor_id = p.u.id
    regla.activo = True
    db.commit()
    return entrar(cliente, p), p


def test_la_regla_de_yas_no_trae_el_escalon_del_diez_de_angie(cliente, db, usuario, finanzas):
    """Yas comisiona el 7 % plano: su regla no tiene meta.

    El porcentaje de Yas sigue por confirmar, pero lo que no puede pasar es que
    herede el escalon de Angie por un emparejamiento de nombres.
    """
    cab, _ = _comercial_con_regla(cliente, db, usuario, 'Yas%')
    venta = vender(cliente, cab, db, servicio='asesoria_adelanto',
                   nombre='Regla Deyas Cliente', fecha='2026-11-05')
    c = comision_de(cliente, finanzas, venta['id'])

    assert c['porcentaje_aplicado'] == 7.0, c
    assert c['escalon'] == 'base', 'el escalon del 10 % es de Angie, no de Yas'
    assert 'Yas' in c['explicacion'] or 'n.º' not in c['explicacion'], c['explicacion']


def test_dos_comerciales_de_nombre_parecido_no_comparten_la_regla(cliente, db, usuario,
                                                                 finanzas):
    """La regla es de quien dice el id, no de quien se llama parecido.

    El emparejamiento viejo exigia que el nombre de la regla empezara por el
    primer nombre de la usuaria, asi que «Angie Lorena» y «Angelica Ruiz» podian
    cobrar las dos el escalon del 10 %.
    """
    cab_angie, _ = _comercial_con_regla(cliente, db, usuario, 'Angie%')
    otra = usuario('comercial')
    otra.u.nombre = 'Angelica Ruiz'
    db.commit()
    cab_otra = entrar(cliente, otra)

    mia = vender(cliente, cab_angie, db, servicio='asesoria_adelanto',
                 nombre='Parecido Angie Cliente', fecha='2026-11-05')
    suya = vender(cliente, cab_otra, db, servicio='asesoria_adelanto',
                  nombre='Parecido Angelica Cliente', fecha='2026-11-05')

    assert comision_de(cliente, finanzas, mia['id'])['porcentaje_aplicado'] == 10.0
    assert comision_de(cliente, finanzas, suya['id']) is None, (
        'Angelica no es Angie: no hereda su regla por parecerse de nombre')


def test_una_comercial_sin_regla_no_comisiona(cliente, db, usuario, finanzas):
    """Miriam no vende: una comercial sin regla propia no cobra la de nadie."""
    p = usuario('comercial')
    p.u.nombre = 'Miriam Sin Regla'
    db.commit()
    cab = entrar(cliente, p)

    venta = vender(cliente, cab, db, servicio='asesoria_adelanto',
                   nombre='Sin Regla Cliente', fecha='2026-11-05')
    assert comision_de(cliente, finanzas, venta['id']) is None, (
        'una comercial sin regla no puede heredar el escalon del 10 % de Angie')


def test_la_regla_congelada_dice_el_nombre_de_la_regla_que_se_aplico(cliente, db, usuario,
                                                                     finanzas):
    """RN-07: la comision guarda cual regla se le aplico, y tiene que ser la suya."""
    cab, p = _comercial_con_regla(cliente, db, usuario, 'Yas%')
    venta = vender(cliente, cab, db, servicio='asesoria_usa', nombre='Congelada Yas Cliente')

    c = db.scalars(select(Comisiones).where(Comisiones.negocio_id == venta['id'])).first()
    assert c.regla_aplicada['regla_nombre'].startswith('Yas'), c.regla_aplicada['regla_nombre']
    assert 'porcentaje_meta' not in c.regla_aplicada, 'la regla de Yas no tiene meta'


# ------------------------------------------------- el cupo y las ventas atrasadas
#
# Lo encontro una auditoria del motor el 05/10/2026: el cupo del 10 % se reparte
# por fecha de venta, asi que una venta registrada hoy con fecha de la semana
# pasada no solo toma su puesto, les corre un puesto a todas las de atras. Antes
# de arreglarlo, la que salia del cupo se quedaba con el 10 % y el mes terminaba
# con once comisiones al 10 % contra una meta de diez.

def _diez_premium_de_septiembre(cliente, cab, db, etiqueta):
    """Diez ventas premium del 19 al 28 de septiembre, en orden."""
    return [vender(cliente, cab, db, servicio='asesoria_adelanto',
                   nombre=f'{etiqueta} Cliente{i:02d} Apellido{i:02d}',
                   fecha=f'2026-09-{i + 19:02d}')
            for i in range(10)]


def test_una_venta_atrasada_no_deja_once_comisiones_al_diez_por_ciento(cliente, vendedora,
                                                                       finanzas, db):
    """La meta es de diez. Once al 10 % es plata pagada de mas."""
    cab, p = vendedora
    _diez_premium_de_septiembre(cliente, cab, db, 'Atrasada')

    delmes = cliente.get(f'/api/v1/comisiones?vendedor_id={p.u.id}&periodo=2026-09-01',
                         headers=finanzas).json()
    assert [c['porcentaje_aplicado'] for c in delmes] == [10.0] * 10, 'los diez cupos usados'

    # Llega la venta atrasada: fue el 22 de septiembre, se registra hoy.
    vender(cliente, cab, db, servicio='asesoria_adelanto',
           nombre='Atrasada Retro Cliente', fecha='2026-09-22')

    despues = cliente.get(f'/api/v1/comisiones?vendedor_id={p.u.id}&periodo=2026-09-01',
                          headers=finanzas).json()
    al_diez = [c for c in despues if c['porcentaje_aplicado'] == 10.0]
    al_siete = [c for c in despues if c['porcentaje_aplicado'] == 7.0]
    assert len(despues) == 11
    assert len(al_diez) == 10, f'once premium, diez cupos: {len(al_diez)} al 10 %'
    assert len(al_siete) == 1, 'la que sale del cupo vuelve al 7 %'


def test_la_venta_atrasada_toma_el_puesto_que_le_da_la_fecha(cliente, vendedora, finanzas, db):
    """El puesto sale de la fecha de venta, no del dia en que se digito."""
    cab, p = vendedora
    diez = _diez_premium_de_septiembre(cliente, cab, db, 'Puesto')
    ultima = diez[-1]              # la del 28, hasta ahora la n.º 10

    nueva = vender(cliente, cab, db, servicio='asesoria_adelanto',
                   nombre='Puesto Retro Cliente', fecha='2026-09-22')

    # El 22 ya tenia una venta (la n.º 4), asi que la atrasada entra de quinta.
    c_nueva = comision_de(cliente, finanzas, nueva['id'])
    assert c_nueva['porcentaje_aplicado'] == 10.0
    assert 'n.º 5' in c_nueva['explicacion'], c_nueva['explicacion']

    # Y la del 28 pasa a ser la n.º 11: fuera del cupo.
    c_ultima = comision_de(cliente, finanzas, ultima['id'])
    assert c_ultima['porcentaje_aplicado'] == 7.0, c_ultima
    assert c_ultima['escalon'] == 'base'
    assert 'n.º 11' in c_ultima['explicacion'], c_ultima['explicacion']


def test_ningun_puesto_del_cupo_queda_repetido(cliente, vendedora, finanzas, db):
    """Dos comisiones diciendo ser la misma venta n.º 5 no se puede explicar."""
    cab, p = vendedora
    _diez_premium_de_septiembre(cliente, cab, db, 'Unico')
    vender(cliente, cab, db, servicio='asesoria_adelanto',
           nombre='Unico Retro Cliente', fecha='2026-09-22')

    puestos = [c.regla_aplicada.get('posicion_en_la_meta') for c in db.scalars(
        select(Comisiones).where(Comisiones.vendedor_id == p.u.id,
                                 Comisiones.periodo == dt.date(2026, 9, 1)))]
    assert sorted(puestos) == list(range(1, 12)), f'los puestos del mes: {sorted(puestos)}'


def test_el_corte_del_mes_paga_diez_cupos_y_no_once(cliente, vendedora, finanzas, db):
    """La prueba de la plata: lo anterior son campos, esto es lo que se gira."""
    cab, p = vendedora
    ventas = _diez_premium_de_septiembre(cliente, cab, db, 'Corte')
    ventas.append(vender(cliente, cab, db, servicio='asesoria_adelanto',
                         nombre='Corte Retro Cliente', fecha='2026-09-22'))
    for v in ventas:
        cliente.post('/api/v1/pagos', headers=finanzas,
                     json={'negocio_id': v['id'], 'monto_bruto': v['valor_pactado'],
                           'fecha': '2026-09-30'})

    r = cliente.post('/api/v1/liquidaciones', headers=finanzas,
                     json={'vendedor_id': p.u.id, 'periodo': '2026-09-01'})
    assert r.status_code == 201, r.text
    liq = r.json()
    assert liq['cantidad'] == 11

    valores = sorted(v['valor_pactado'] for v in ventas)
    debido = sum(valores[:-1]) * 0.10 + valores[-1] * 0.07
    assert liq['total'] == pytest.approx(debido, abs=2), (
        f'el corte gira {liq["total"]:,.0f} y la regla dice {debido:,.0f}')


def test_una_atrasada_que_desplaza_una_comision_ya_pagada_queda_anotada(cliente, vendedora,
                                                                        finanzas, db):
    """Si el cupo ya se liquido, esa plata ya salio y no se puede recalcular.

    Lo unico honesto es que quede escrito: sin esto el sobrepago desaparece sin
    que nadie se entere.
    """
    cab, p = vendedora
    diez = _diez_premium_de_septiembre(cliente, cab, db, 'Anotada')
    for v in diez:
        cliente.post('/api/v1/pagos', headers=finanzas,
                     json={'negocio_id': v['id'], 'monto_bruto': v['valor_pactado'],
                           'fecha': '2026-09-30'})
    r = cliente.post('/api/v1/liquidaciones', headers=finanzas,
                     json={'vendedor_id': p.u.id, 'periodo': '2026-09-01'})
    assert r.status_code == 201 and r.json()['cantidad'] == 10

    vender(cliente, cab, db, servicio='asesoria_adelanto',
           nombre='Anotada Retro Cliente', fecha='2026-09-22')

    alerta = db.scalars(select(Auditoria)
                        .where(Auditoria.operacion == 'alerta',
                               Auditoria.entidad == 'comisiones')
                        .order_by(Auditoria.id.desc())).first()
    assert alerta is not None, 'el sobrepago tiene que quedar anotado'
    assert alerta.despues['vendedor_id'] == p.u.id
    assert len(alerta.despues['comisiones']) == 1, alerta.despues
    assert 'ya salió' in alerta.despues['motivo']

    # La liquidada no se tocó: esa plata ya se pagó (RN-07).
    c = comision_de(cliente, finanzas, diez[-1]['id'])
    assert c['estado'] == 'liquidada' and c['porcentaje_aplicado'] == 10.0


# -------------------------------------------------------------- la causación

def test_la_comision_se_gana_cuando_el_cliente_termina_de_pagar(cliente, vendedora,
                                                                 finanzas, db):
    """«La comisión se gana cuando el cliente termina de pagar toda la venta»."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, servicio='asesoria_usa', nombre='Pago Completo Cliente')
    total = venta['valor_pactado']

    cliente.post('/api/v1/pagos', headers=finanzas,
                 json={'negocio_id': venta['id'], 'monto_bruto': total / 2})
    assert comision_de(cliente, finanzas, venta['id'])['estado'] == 'provisional'

    cliente.post('/api/v1/pagos', headers=finanzas,
                 json={'negocio_id': venta['id'], 'monto_bruto': total / 2})
    assert comision_de(cliente, finanzas, venta['id'])['estado'] == 'causada'


def test_reversar_un_pago_devuelve_la_comision_a_provisional(cliente, vendedora, finanzas, db):
    """No se paga comisión de plata que no entró."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, servicio='asesoria_usa', nombre='Pago Reversado Cliente')
    pago = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': venta['valor_pactado']}).json()
    assert comision_de(cliente, finanzas, venta['id'])['estado'] == 'causada'

    cliente.post(f'/api/v1/pagos/{pago["id"]}/estado', headers=finanzas,
                 json={'estado': 'reversado', 'observacion': 'El banco la devolvió'})
    assert comision_de(cliente, finanzas, venta['id'])['estado'] == 'provisional'


def test_un_cargo_posterior_vuelve_a_abrir_la_comision(cliente, vendedora, finanzas, db):
    cab, _ = vendedora
    venta = vender(cliente, cab, db, servicio='asesoria_usa', nombre='Cargo Posterior Cliente')
    cliente.post('/api/v1/pagos', headers=finanzas,
                 json={'negocio_id': venta['id'], 'monto_bruto': venta['valor_pactado']})
    assert comision_de(cliente, finanzas, venta['id'])['estado'] == 'causada'

    cliente.post(f'/api/v1/ventas/{venta["id"]}/ajustes', headers=finanzas, json={
        'tipo': 'cargo', 'monto': 50000, 'motivo': 'Envío urgente'})
    assert comision_de(cliente, finanzas, venta['id'])['estado'] == 'provisional'


# --------------------------------------------------------- la regla congelada

def test_la_regla_queda_congelada_en_la_comision(cliente, vendedora, finanzas, db):
    """RN-07: si en enero cambia el porcentaje, las comisiones de octubre no se
    mueven. Por eso la comisión guarda su propia copia de la regla."""
    from app.models.esquema import Comisiones

    cab, _ = vendedora
    venta = vender(cliente, cab, db, servicio='asesoria_usa', nombre='Regla Congelada Cliente')
    comision = db.scalar(select(Comisiones).where(Comisiones.negocio_id == venta['id']))

    congelada = comision.regla_aplicada
    assert congelada['porcentaje_aplicado'] == 7.0
    assert congelada['se_causa_con'] == 'pago_total'
    assert 'congelada_en' in congelada
    assert congelada['explicacion'], 'tiene que poder explicarse meses después'

    # Cambia la regla del catálogo: la comisión ya hecha no se mueve
    db.execute(text('update comisiones_reglas set porcentaje = 15'))
    db.commit()
    assert comision_de(cliente, finanzas, venta['id'])['porcentaje_aplicado'] == 7.0


# --------------------------------------------------------------- liquidación

def test_la_liquidacion_junta_lo_causado_y_lo_bloquea(cliente, vendedora, finanzas, db):
    """RF-052. Las comisiones que entran no pueden volver a entrar en otro
    corte: ahí está la diferencia entre un reporte y el registro de un pago."""
    cab, p = vendedora
    ventas = []
    for i in range(3):
        v = vender(cliente, cab, db, servicio='asesoria_usa',
                   nombre=f'Liquidar Cliente{i} Apellido{i}', fecha='2027-03-10')
        cliente.post('/api/v1/pagos', headers=finanzas,
                     json={'negocio_id': v['id'], 'monto_bruto': v['valor_pactado'],
                           'fecha': '2027-03-15'})
        ventas.append(v)

    pendientes = cliente.get(f'/api/v1/comisiones/pendientes?vendedor_id={p.u.id}'
                             '&periodo=2027-03-01', headers=finanzas).json()
    assert len(pendientes) == 3

    r = cliente.post('/api/v1/liquidaciones', headers=finanzas, json={
        'vendedor_id': p.u.id, 'periodo': '2027-03-20', 'observaciones': 'Corte de marzo'})
    assert r.status_code == 201, r.text
    liq = r.json()
    assert liq['cantidad'] == 3
    assert liq['periodo'] == '2027-03-01', 'el periodo es el primer día del mes'
    assert liq['total'] == pytest.approx(sum(c['monto'] for c in pendientes), abs=1)
    assert all(c['estado'] == 'liquidada' for c in liq['comisiones'])

    # Ya no quedan pendientes y no se puede liquidar dos veces el mismo mes
    assert cliente.get(f'/api/v1/comisiones/pendientes?vendedor_id={p.u.id}'
                       '&periodo=2027-03-01', headers=finanzas).json() == []
    r = cliente.post('/api/v1/liquidaciones', headers=finanzas,
                     json={'vendedor_id': p.u.id, 'periodo': '2027-03-01'})
    assert r.status_code == 409 and r.json()['codigo'] == 'periodo_ya_liquidado'


def test_una_comision_provisional_no_entra_en_el_corte(cliente, vendedora, finanzas, db):
    """Solo se liquida lo que el cliente ya pagó."""
    cab, p = vendedora
    vender(cliente, cab, db, servicio='asesoria_usa', nombre='Sin Pagar Cliente',
           fecha='2027-04-05')
    r = cliente.post('/api/v1/liquidaciones', headers=finanzas,
                     json={'vendedor_id': p.u.id, 'periodo': '2027-04-01'})
    assert r.status_code == 422 and r.json()['codigo'] == 'sin_comisiones'


def test_anular_la_liquidacion_devuelve_las_comisiones(cliente, vendedora, finanzas, db):
    cab, p = vendedora
    v = vender(cliente, cab, db, servicio='asesoria_usa', nombre='Anular Corte Cliente',
               fecha='2027-05-10')
    cliente.post('/api/v1/pagos', headers=finanzas,
                 json={'negocio_id': v['id'], 'monto_bruto': v['valor_pactado'],
                       'fecha': '2027-05-12'})
    liq = cliente.post('/api/v1/liquidaciones', headers=finanzas,
                       json={'vendedor_id': p.u.id, 'periodo': '2027-05-01'}).json()

    r = cliente.post(f'/api/v1/liquidaciones/{liq["id"]}/anular', headers=finanzas,
                     json={'motivo': 'Se liquidó el mes equivocado'})
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'anulada'
    assert 'Se liquidó el mes equivocado' in r.json()['observaciones']
    assert comision_de(cliente, finanzas, v['id'])['estado'] == 'causada'

    # Y ahora sí se puede volver a liquidar ese mes
    assert cliente.post('/api/v1/liquidaciones', headers=finanzas,
                        json={'vendedor_id': p.u.id,
                              'periodo': '2027-05-01'}).status_code == 201


def test_una_comision_liquidada_no_se_recalcula(cliente, vendedora, finanzas, db):
    """Esa plata ya se pagó: cambiarla después es reescribir la historia."""
    cab, p = vendedora
    v = vender(cliente, cab, db, servicio='asesoria_usa', nombre='Ya Liquidada Cliente',
               fecha='2027-06-10')
    cliente.post('/api/v1/pagos', headers=finanzas,
                 json={'negocio_id': v['id'], 'monto_bruto': v['valor_pactado'],
                       'fecha': '2027-06-11'})
    cliente.post('/api/v1/liquidaciones', headers=finanzas,
                 json={'vendedor_id': p.u.id, 'periodo': '2027-06-01'})

    r = cliente.post(f'/api/v1/ventas/{v["id"]}/comision/recalcular', headers=finanzas)
    assert r.status_code == 409 and r.json()['codigo'] == 'comision_liquidada'


# -------------------------------------------------------------------- gastos

def test_un_gasto_directo_se_le_carga_a_la_venta(cliente, vendedora, finanzas, db):
    """La mensajería de un trámite se le resta a esa venta; la publicidad del
    mes no. Es la diferencia que decide si una venta fue buen negocio."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, servicio='asesoria_usa', nombre='Con Gastos Cliente')
    mensajeria = db.scalar(select(CategoriasGasto.id)
                           .where(CategoriasGasto.codigo == 'mensajeria'))
    publicidad = db.scalar(select(CategoriasGasto.id)
                           .where(CategoriasGasto.codigo == 'publicidad'))

    r = cliente.post('/api/v1/gastos', headers=finanzas, json={
        'categoria_id': mensajeria, 'concepto': 'Envío del pasaporte a Bogotá',
        'monto': 35000, 'negocio_id': venta['id']})
    assert r.status_code == 201 and r.json()['es_directo'] is True

    cliente.post('/api/v1/gastos', headers=finanzas, json={
        'categoria_id': publicidad, 'concepto': 'Pauta de octubre', 'monto': 500000})

    directos = cliente.get(f'/api/v1/gastos?negocio_id={venta["id"]}', headers=finanzas).json()
    assert directos['total'] == 1 and directos['suma'] == 35000

    from app.services.gastos import directos_de_la_venta
    assert directos_de_la_venta(db, venta['id']) == 35000


def test_un_gasto_se_anula_pero_no_se_borra(cliente, finanzas, db):
    categoria = db.scalar(select(CategoriasGasto.id).where(CategoriasGasto.codigo == 'otro'))
    g = cliente.post('/api/v1/gastos', headers=finanzas, json={
        'categoria_id': categoria, 'concepto': 'Gasto equivocado', 'monto': 90000}).json()

    r = cliente.post(f'/api/v1/gastos/{g["id"]}/anular', headers=finanzas,
                     json={'motivo': 'Se registró dos veces'})
    assert r.status_code == 200 and r.json()['estado'] == 'anulado'

    visibles = cliente.get('/api/v1/gastos', headers=finanzas).json()
    assert g['id'] not in [x['id'] for x in visibles['items']]
    con_anulados = cliente.get('/api/v1/gastos?incluir_anulados=true', headers=finanzas).json()
    assert g['id'] in [x['id'] for x in con_anulados['items']]


def test_operaciones_no_ve_gastos_ni_comisiones(cliente, usuario):
    """Respuesta de la administradora del 29/09: a operaciones se le oculta la
    contabilidad."""
    cab = entrar(cliente, usuario('operaciones'))
    assert cliente.get('/api/v1/gastos', headers=cab).status_code == 403
    assert cliente.get('/api/v1/comisiones', headers=cab).status_code == 403
