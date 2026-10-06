"""Actividades 4.1 a 4.4 — acuerdo, pagos, saldo y cartera (RF-040 a RF-046).

Los abonos viven hoy en columnas fijas y seis ventas ya llenaron las tres: no
hay dónde registrar un cuarto pago. Y el saldo está escrito en una celda, así
que dos hojas dicen números distintos — entre PAGOS y REV PAGOS hay 37 millones
de deuda fantasma. Aquí los pagos son filas y el saldo lo calcula la vista.
"""
import datetime as dt

import pytest
from sqlalchemy import select, text

from app.models.esquema import MediosPago, Paises, Servicios
from tests.conftest import entrar


@pytest.fixture
def comercial(cliente, usuario):
    p = usuario('comercial')
    return entrar(cliente, p), p


@pytest.fixture
def finanzas(cliente, usuario):
    return entrar(cliente, usuario('finanzas'))


@pytest.fixture
def venta(cliente, comercial, db):
    """Una venta real, hecha por el camino normal: lead → ganar."""
    cab, _ = comercial
    c = cliente.post('/api/v1/clientes', headers=cab,
                     json={'nombre': 'Mauricio Londoño Sierra'}).json()
    cliente.post('/api/v1/solicitantes', headers=cab,
                 json={'cliente_id': c['id'], 'nombre': 'Mauricio Londoño Sierra'})
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    servicio = db.scalar(select(Servicios.id).where(Servicios.codigo == 'adelantos'))
    lead = cliente.post('/api/v1/oportunidades', headers=cab, json={
        'cliente_id': c['id'], 'servicio_id': servicio, 'pais_id': pais,
        'proxima_accion': 'Enviar cotización'}).json()
    v = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json={}).json()
    assert v['valor_pactado'] == 700000
    return v


def estado(cliente, cab, negocio_id):
    r = cliente.get(f'/api/v1/ventas/{negocio_id}/estado-financiero', headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


# -------------------------------------------------- pagos como transacciones

def test_una_venta_admite_mas_de_tres_pagos(cliente, finanzas, venta):
    """Es el límite que los archivos ya reventaron: «Abono 1, 2 y 3» y seis
    ventas con las tres llenas. Aquí un pago es una fila (RN-02)."""
    for i in range(5):
        r = cliente.post('/api/v1/pagos', headers=finanzas, json={
            'negocio_id': venta['id'], 'monto_bruto': 100000,
            'fecha': f'2026-10-0{i + 1}', 'referencia': f'abono {i + 1}'})
        assert r.status_code == 201, r.text

    e = estado(cliente, finanzas, venta['id'])
    assert len(e['pagos']) == 5
    assert e['total_pagado'] == 500000
    assert e['saldo'] == 200000, 'lo calcula la vista: 700.000 − 500.000'
    assert e['estado_financiero'] == 'abono'


def test_el_saldo_lo_calcula_la_vista_y_no_una_columna(cliente, finanzas, venta, db):
    """RN-01. Si el saldo estuviera guardado, habría dos lugares que pueden
    decir cosas distintas, que es el problema que tienen hoy los archivos."""
    cliente.post('/api/v1/pagos', headers=finanzas,
                 json={'negocio_id': venta['id'], 'monto_bruto': 300000})
    e = estado(cliente, finanzas, venta['id'])
    de_la_vista = db.execute(text('select saldo from v_estado_financiero where negocio_id = :n'),
                             {'n': venta['id']}).scalar()
    assert e['saldo'] == float(de_la_vista) == 400000

    columnas = [c[0] for c in db.execute(text(
        "select column_name from information_schema.columns where table_name = 'negocios'"))]
    assert 'saldo' not in columnas, 'el saldo no puede ser una columna de la venta'


def test_pagar_todo_deja_la_venta_en_pagado(cliente, finanzas, venta):
    cliente.post('/api/v1/pagos', headers=finanzas,
                 json={'negocio_id': venta['id'], 'monto_bruto': 700000})
    e = estado(cliente, finanzas, venta['id'])
    assert e['saldo'] == 0 and e['estado_financiero'] == 'pagado'


def test_el_costo_del_medio_de_pago_se_descuenta_del_neto(cliente, finanzas, venta, db):
    """La pasarela cobra: entraron 100.000 pero a la cuenta llegaron 97.000. Lo
    que el cliente debe baja por el bruto; lo que entró de verdad es el neto."""
    medio = db.scalar(select(MediosPago.id).where(MediosPago.codigo == 'pasarela'))
    cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': 100000, 'costo_medio': 3000,
        'medio_pago_id': medio})
    e = estado(cliente, finanzas, venta['id'])
    assert e['total_pagado'] == 100000, 'al cliente se le abona el bruto'
    assert e['neto_recibido'] == 97000, 'a la caja entraron 97.000'
    assert e['saldo'] == 600000


def test_un_costo_mayor_que_el_pago_se_rechaza(cliente, finanzas, venta):
    r = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': 50000, 'costo_medio': 60000})
    assert r.status_code == 422 and r.json()['codigo'] == 'costo_mayor_que_pago'


def test_un_pago_reversado_deja_de_contar_pero_no_se_borra(cliente, finanzas, venta):
    """Un pago borrado es plata que desaparece del historial sin rastro."""
    pago = cliente.post('/api/v1/pagos', headers=finanzas,
                        json={'negocio_id': venta['id'], 'monto_bruto': 200000}).json()
    assert estado(cliente, finanzas, venta['id'])['saldo'] == 500000

    r = cliente.post(f'/api/v1/pagos/{pago["id"]}/estado', headers=finanzas, json={
        'estado': 'reversado', 'observacion': 'El banco devolvió la transferencia'})
    assert r.status_code == 200, r.text

    e = estado(cliente, finanzas, venta['id'])
    assert e['saldo'] == 700000, 'vuelve a deber todo'
    assert len(e['pagos']) == 1, 'el pago sigue ahí, marcado'
    assert e['pagos'][0]['estado'] == 'reversado'


# ------------------------------------------- la bandeja de no identificados

def test_un_pago_sin_dueno_entra_y_espera_en_la_bandeja(cliente, finanzas, venta):
    """Llega una consignación y no siempre se sabe de quién es: el que consigna
    puede ser el papá o la empresa. Es mejor que perderlo o inventarle dueño."""
    r = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'monto_bruto': 350000, 'pagador_nombre': 'Gloria Sierra',
        'observacion': 'Consignación sin referencia'})
    assert r.status_code == 201, r.text
    pago = r.json()
    assert pago['negocio_id'] is None and pago['estado'] == 'no_identificado'

    bandeja = cliente.get('/api/v1/pagos?sin_asignar=true', headers=finanzas).json()
    assert pago['id'] in [p['id'] for p in bandeja['items']]
    # Y no le baja el saldo a nadie
    assert estado(cliente, finanzas, venta['id'])['saldo'] == 700000

    r = cliente.post(f'/api/v1/pagos/{pago["id"]}/asignar', headers=finanzas,
                     json={'negocio_id': venta['id']})
    assert r.status_code == 200 and r.json()['estado'] == 'confirmado'
    assert estado(cliente, finanzas, venta['id'])['saldo'] == 350000
    assert cliente.get('/api/v1/pagos?sin_asignar=true', headers=finanzas).json()['total'] == 0


# ------------------------------------------------------------ plan de cuotas

def test_el_plan_de_cuotas_parte_la_venta_en_anticipo_y_saldo(cliente, finanzas, venta):
    """Sin cuotas la cartera vencida sale en cero: una venta que no vence nunca
    no la cobra nadie."""
    r = cliente.post(f'/api/v1/ventas/{venta["id"]}/cuotas', headers=finanzas, json={})
    assert r.status_code == 201, r.text
    cuotas = r.json()
    assert [c['concepto'] for c in cuotas] == ['anticipo', 'saldo']
    assert [c['monto'] for c in cuotas] == [140000, 560000], '20 % y 80 % de 700.000'
    assert sum(c['monto'] for c in cuotas) == 700000, 'las cuotas suman el valor pactado'
    assert cuotas[1]['fecha_pactada'] > cuotas[0]['fecha_pactada']


def test_las_cuotas_suman_exacto_aunque_el_reparto_no_sea_redondo(cliente, finanzas, venta):
    """La última cuota lleva el residuo: si no, sobra o falta un peso y la
    cartera nunca llega a cero."""
    r = cliente.post(f'/api/v1/ventas/{venta["id"]}/cuotas', headers=finanzas,
                     json={'reparto': [33, 33, 34]})
    assert r.status_code == 201, r.text
    cuotas = r.json()
    assert len(cuotas) == 3
    assert sum(c['monto'] for c in cuotas) == 700000


def test_un_reparto_que_no_suma_cien_se_rechaza(cliente, finanzas, venta):
    r = cliente.post(f'/api/v1/ventas/{venta["id"]}/cuotas', headers=finanzas,
                     json={'reparto': [30, 30]})
    assert r.status_code == 422 and 'suma 60' in r.json()['detalle']


def test_no_se_duplica_el_plan_de_cuotas(cliente, finanzas, venta):
    cliente.post(f'/api/v1/ventas/{venta["id"]}/cuotas', headers=finanzas, json={})
    r = cliente.post(f'/api/v1/ventas/{venta["id"]}/cuotas', headers=finanzas, json={})
    assert r.status_code == 409 and r.json()['codigo'] == 'ya_tiene_cuotas'


# ---------------------------------------------------------------- ajustes

def test_un_descuento_posterior_baja_la_deuda_sin_tocar_el_valor_pactado(cliente, finanzas, venta):
    """Queda constancia de que se rebajó y por qué, en vez de reescribir el
    precio y perder la historia."""
    r = cliente.post(f'/api/v1/ventas/{venta["id"]}/ajustes', headers=finanzas, json={
        'tipo': 'descuento', 'monto': 100000, 'motivo': 'Se demoró la cita por culpa nuestra'})
    assert r.status_code == 201, r.text
    assert r.json()['monto'] == -100000, 'el tipo decide el signo'

    e = estado(cliente, finanzas, venta['id'])
    assert e['valor_pactado'] == 700000, 'el precio pactado no se reescribe'
    assert e['ajustes'] == -100000
    assert e['saldo'] == 600000


def test_un_cargo_sube_la_deuda(cliente, finanzas, venta):
    cliente.post(f'/api/v1/ventas/{venta["id"]}/ajustes', headers=finanzas, json={
        'tipo': 'cargo', 'monto': 50000, 'motivo': 'Envío urgente de documentos'})
    assert estado(cliente, finanzas, venta['id'])['saldo'] == 750000


def test_un_ajuste_sin_motivo_se_rechaza(cliente, finanzas, venta):
    """Un ajuste sin motivo es plata que cambió de lugar sin que nadie pueda
    explicar por qué."""
    r = cliente.post(f'/api/v1/ventas/{venta["id"]}/ajustes', headers=finanzas,
                     json={'tipo': 'cargo', 'monto': 50000, 'motivo': ''})
    assert r.status_code == 422


def test_el_monto_del_ajuste_va_en_positivo_siempre(cliente, finanzas, venta):
    r = cliente.post(f'/api/v1/ventas/{venta["id"]}/ajustes', headers=finanzas, json={
        'tipo': 'descuento', 'monto': -50000, 'motivo': 'Prueba'})
    assert r.status_code == 422


# ----------------------------------------------------------------- cartera

def test_la_cartera_distingue_lo_vencido_de_lo_por_vencer(cliente, finanzas, venta, db):
    """RF-046: a quién se llama primero. Sin la antigüedad, la lista de deudores
    es un montón sin orden."""
    cliente.post(f'/api/v1/ventas/{venta["id"]}/cuotas', headers=finanzas, json={})
    # La venta se hizo hace dos meses: el anticipo ya venció
    db.execute(text("""update cuotas_negocio set fecha_pactada = current_date - 60
                        where negocio_id = :n and numero = 1"""), {'n': venta['id']})
    db.execute(text("""update cuotas_negocio set fecha_pactada = current_date + 30
                        where negocio_id = :n and numero = 2"""), {'n': venta['id']})
    db.commit()

    r = cliente.get('/api/v1/cartera', headers=finanzas).json()
    fila = next(f for f in r['items'] if f['negocio_id'] == venta['id'])
    assert fila['vencido'] == 140000, 'el anticipo que no pagó'
    assert fila['por_vencer'] == 560000
    assert fila['dias_vencido'] == 60
    assert fila['cliente'] == 'Mauricio Londoño Sierra'

    solo_vencida = cliente.get('/api/v1/cartera?solo_vencida=true', headers=finanzas).json()
    assert venta['id'] in [f['negocio_id'] for f in solo_vencida['items']]


def test_el_resumen_de_cartera_da_los_cuatro_numeros(cliente, finanzas, venta):
    cliente.post('/api/v1/pagos', headers=finanzas,
                 json={'negocio_id': venta['id'], 'monto_bruto': 200000})
    r = cliente.get('/api/v1/cartera/resumen', headers=finanzas).json()
    assert r['vendido'] >= 700000
    assert r['cobrado'] >= 200000
    assert r['cartera'] >= 500000
    assert r['ventas_con_saldo'] >= 1


def test_una_venta_pagada_sale_de_la_cartera(cliente, finanzas, venta):
    cliente.post('/api/v1/pagos', headers=finanzas,
                 json={'negocio_id': venta['id'], 'monto_bruto': 700000})
    r = cliente.get('/api/v1/cartera', headers=finanzas).json()
    assert venta['id'] not in [f['negocio_id'] for f in r['items']]


def test_operaciones_no_ve_los_montos_de_la_cartera(cliente, usuario, venta):
    """Respuesta de la administradora del 29/09: a operaciones se le oculta la
    contabilidad."""
    cab = entrar(cliente, usuario('operaciones'))
    assert cliente.get('/api/v1/cartera', headers=cab).status_code == 403
    assert cliente.get('/api/v1/pagos', headers=cab).status_code == 403
