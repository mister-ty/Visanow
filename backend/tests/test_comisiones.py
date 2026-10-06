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

from app.models.esquema import CategoriasGasto, Negocios, Paises, Servicios
from tests.conftest import entrar


@pytest.fixture
def finanzas(cliente, usuario):
    return entrar(cliente, usuario('finanzas'))


@pytest.fixture
def vendedora(cliente, db, usuario):
    """Una comercial con la regla de Angie: el seed la empareja por nombre."""
    p = usuario('comercial')
    p.u.nombre = 'Angie Lorena'
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
