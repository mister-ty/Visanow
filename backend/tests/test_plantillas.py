"""Plantillas de mensajes por evento (RF-063).

Estas pruebas NO se corrieron al escribirlas (el entorno no tenía PostgreSQL):
revisar el resultado antes de fusionar. Falta una prueba de generación completa
con una venta y una cita reales.
"""
import pytest

from tests.conftest import entrar


@pytest.fixture
def admin(cliente, usuario):
    return entrar(cliente, usuario('administradora'))


def test_la_migracion_deja_plantillas_iniciales(cliente, admin):
    r = cliente.get('/api/v1/plantillas', headers=admin)
    assert r.status_code == 200, r.text
    assert {p['evento'] for p in r.json()} >= {'cita_confirmada', 'saldo_pendiente'}


def test_una_variable_mal_escrita_se_rechaza(cliente, admin):
    """Saldría tal cual en el mensaje al cliente."""
    r = cliente.post('/api/v1/plantillas', headers=admin, json={
        'evento': 'pago_recibido', 'nombre': 'Con error', 'cuerpo': 'Hola {{cliente_nmbre}}'})
    assert r.status_code == 422
    assert 'cliente_nmbre' in r.json()['detalle']


def test_no_se_repite_nombre_en_el_mismo_evento_y_canal(cliente, admin):
    datos = {'evento': 'pago_recibido', 'nombre': 'Gracias por su pago',
             'cuerpo': 'Gracias {{cliente_nombre}}'}
    assert cliente.post('/api/v1/plantillas', headers=admin, json=datos).status_code == 201
    assert cliente.post('/api/v1/plantillas', headers=admin, json=datos).status_code == 409


def test_editar_una_plantilla_y_desactivarla(cliente, admin):
    p = cliente.get('/api/v1/plantillas', headers=admin).json()[0]
    r = cliente.patch(f'/api/v1/plantillas/{p["id"]}', headers=admin, json={'activa': False})
    assert r.status_code == 200 and r.json()['activa'] is False
    ids = [x['id'] for x in cliente.get('/api/v1/plantillas', headers=admin).json()]
    assert p['id'] not in ids


def test_operaciones_usa_plantillas_pero_no_las_edita(cliente, usuario):
    cab = entrar(cliente, usuario('operaciones'))
    assert cliente.get('/api/v1/plantillas', headers=cab).status_code == 200
    r = cliente.post('/api/v1/plantillas', headers=cab, json={
        'evento': 'pago_recibido', 'nombre': 'No debería', 'cuerpo': 'Hola'})
    assert r.status_code == 403


def test_operaciones_no_imprime_montos(cliente, usuario, admin):
    """Respuesta del 29/09: operaciones no ve la contabilidad, tampoco en un mensaje."""
    cab = entrar(cliente, usuario('operaciones'))
    con_saldo = next(p for p in cliente.get('/api/v1/plantillas', headers=admin).json()
                     if 'saldo' in p['variables'])
    r = cliente.post(f'/api/v1/plantillas/{con_saldo["id"]}/generar', headers=cab,
                     json={'caso_id': 1})
    assert r.status_code == 403
