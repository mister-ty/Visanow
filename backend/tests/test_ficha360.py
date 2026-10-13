"""La vista 360 completa (RF-005).

El requisito enumera nueve cosas -oportunidades, ventas, trámites, pagos, saldo,
tareas, alertas, documentos y cronología- y la ficha traía dos. Lo demás estaba
repartido entre siete pantallas.

Lo que vigilan estas pruebas no es que los bloques existan, que es lo fácil,
sino que cada uno respete a quién le toca. La ficha responde todo junto: si los
permisos se mezclan, operaciones recibe en una sola llamada los montos que la
administradora dijo el 29/09 que no debe ver.
"""
import pytest
from sqlalchemy import select, text

from app.models.esquema import Paises, Servicios
from tests.conftest import entrar

RUTA = '/api/v1/clientes/{}/ficha'


@pytest.fixture
def admin(cliente, usuario):
    return entrar(cliente, usuario('administradora'))


def ficha(cliente, cab, cliente_id):
    r = cliente.get(RUTA.format(cliente_id), headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def cliente_completo(cliente, admin, db, usuario):
    """Un cliente con de todo: lead, venta, pago, trámite, tarea y documento.

    Se arma por la API y no a mano en la base, para que sea lo que de verdad
    produce el sistema cuando alguien trabaja.
    """
    c = cliente.post('/api/v1/clientes', headers=admin, json={
        'nombre': 'Completa Trescientos Cliente', 'telefono': '3001112233'}).json()
    s = cliente.post('/api/v1/solicitantes', headers=admin, json={
        'cliente_id': c['id'], 'nombre': 'Completa Trescientos Cliente',
        'pasaporte': 'CT3600001'}).json()

    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    servicio = db.scalar(select(Servicios.id).where(Servicios.codigo == 'asesoria_usa'))

    lead = cliente.post('/api/v1/oportunidades', headers=admin, json={
        'cliente_id': c['id'], 'servicio_id': servicio, 'pais_id': pais,
        'proxima_accion': 'Cotizar el premium'}).json()
    venta = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar',
                         headers=admin, json={}).json()
    cliente.post('/api/v1/pagos', headers=admin, json={
        'negocio_id': venta['id'], 'fecha': '2026-10-01', 'monto_bruto': 240000})
    cliente.post('/api/v1/tareas', headers=admin, json={
        'titulo': 'Llamar para la cita', 'cliente_id': c['id'], 'prioridad': 'alta'})
    cliente.post('/api/v1/documentos/enlace', headers=admin, json={
        'entidad': 'cliente', 'entidad_id': c['id'], 'nombre': 'Carpeta compartida',
        'url': 'https://drive.google.com/x'})
    db.commit()
    return c['id'], venta['id']


# ------------------------------------------- las nueve cosas, para quien ve todo

def test_la_ficha_trae_las_nueve_cosas_que_pide_el_requisito(cliente, admin,
                                                             cliente_completo):
    cliente_id, _ = cliente_completo
    f = ficha(cliente, admin, cliente_id)

    assert f['oportunidades'], 'faltan las oportunidades'
    assert f['dinero']['ventas'], 'faltan las ventas'
    assert f['dinero']['pagos'], 'faltan los pagos'
    assert f['dinero']['saldo'] is not None, 'falta el saldo'
    assert f['tramites'], 'faltan los trámites'
    assert f['tareas'], 'faltan las tareas'
    assert f['documentos'], 'faltan los documentos'
    assert f['cronologia'], 'falta la cronología'
    assert 'alertas' in f, 'falta el bloque de alertas'


def test_el_saldo_de_la_ficha_es_el_de_la_vista_y_no_una_resta_aparte(
        cliente, admin, cliente_completo, db):
    """RN-01: el saldo lo calcula la vista, nunca una columna ni una cuenta
    hecha en otro lado. Dos formas de calcularlo es tener dos verdades."""
    cliente_id, negocio_id = cliente_completo
    f = ficha(cliente, admin, cliente_id)

    de_la_vista = db.execute(text(
        'select saldo from v_estado_financiero where negocio_id = :n'),
        {'n': negocio_id}).scalar()
    assert float(f['dinero']['saldo']) == float(de_la_vista)

    venta = next(v for v in f['dinero']['ventas'] if v['id'] == negocio_id)
    assert float(venta['saldo']) == float(de_la_vista)


# -------------------------------------- y lo que cada rol puede y no puede ver

def test_operaciones_ve_si_el_cliente_esta_al_dia_pero_no_los_montos(
        cliente, usuario, cliente_completo):
    """La respuesta de la administradora del 29/09: a operaciones no se le
    oculta nada «salvo lo de la contabilidad». Pero sin saber si el cliente pagó
    el anticipo no puede arrancar el trámite, y eso es `pagos.estado`.
    """
    cliente_id, _ = cliente_completo
    cab = entrar(cliente, usuario('operaciones'))
    f = ficha(cliente, cab, cliente_id)

    assert f['dinero']['ve_montos'] is False
    assert f['dinero']['al_dia'] is not None, 'sí tiene que saber si está al día'
    assert f['dinero']['pagos'] == [], 'no puede ver los pagos'
    assert f['dinero']['total_pagado'] is None
    assert f['dinero']['saldo'] is None


def test_quien_ve_ventas_pero_no_montos_ve_que_compro_y_no_cuanto(
        cliente, usuario, cliente_completo):
    """Saber que el cliente compró el premium no es saber cuánto pagó."""
    cliente_id, _ = cliente_completo
    cab = entrar(cliente, usuario('operaciones'))
    f = ficha(cliente, cab, cliente_id)

    for v in f['dinero']['ventas']:
        assert v['servicio'] is not None, 'sí ve qué compró'
        assert float(v['valor_pactado']) == 0, 'pero no por cuánto'
        assert float(v['saldo']) == 0


def test_finanzas_si_ve_la_plata(cliente, usuario, cliente_completo):
    cliente_id, _ = cliente_completo
    cab = entrar(cliente, usuario('finanzas'))
    f = ficha(cliente, cab, cliente_id)

    assert f['dinero']['ve_montos'] is True
    assert f['dinero']['pagos'], 'finanzas ve los pagos'
    assert float(f['dinero']['total_pagado']) > 0


def test_la_ficha_dice_si_un_bloque_esta_vacio_o_si_no_le_corresponde(
        cliente, usuario, cliente_completo):
    """No es lo mismo «este cliente no tiene ventas» que «usted no las ve».
    Confundirlos hace que alguien crea que el cliente nunca compró."""
    cliente_id, _ = cliente_completo
    cab = entrar(cliente, usuario('operaciones'))
    f = ficha(cliente, cab, cliente_id)

    assert f['ve_oportunidades'] is True
    assert f['dinero']['ve_montos'] is False
    assert f['ve_tramites'] is True


def test_un_documento_reservado_no_sale_en_la_ficha_de_quien_no_puede_verlo(
        cliente, admin, usuario, cliente_completo):
    """El pasaporte escaneado no lo ve el comercial aunque pueda abrir la ficha."""
    cliente_id, _ = cliente_completo
    cliente.post('/api/v1/documentos/enlace', headers=admin, json={
        'entidad': 'cliente', 'entidad_id': cliente_id, 'nombre': 'Pasaporte escaneado',
        'url': 'https://drive.google.com/reservado', 'restringido': True})

    de_admin = ficha(cliente, admin, cliente_id)['documentos']
    assert any(d['nombre'] == 'Pasaporte escaneado' for d in de_admin)

    cab = entrar(cliente, usuario('comercial'))
    del_comercial = ficha(cliente, cab, cliente_id)['documentos']
    assert not any(d['nombre'] == 'Pasaporte escaneado' for d in del_comercial)
    assert any(d['nombre'] == 'Carpeta compartida' for d in del_comercial), (
        'los que no son reservados sí los ve')


def test_los_documentos_de_la_ficha_juntan_los_del_cliente_y_los_de_sus_tramites(
        cliente, admin, cliente_completo, db):
    """Para quien atiende, «los documentos de Ana» son todos, no los de una
    pantalla por un lado y los de otra por el otro."""
    cliente_id, _ = cliente_completo
    caso_id = db.execute(text("""
        select ca.id from casos ca join solicitantes so on so.id = ca.solicitante_id
         where so.cliente_id = :c limit 1"""), {'c': cliente_id}).scalar()
    assert caso_id, 'la venta tuvo que crear un trámite'

    cliente.post('/api/v1/documentos/enlace', headers=admin, json={
        'entidad': 'caso', 'entidad_id': caso_id, 'nombre': 'Soporte del trámite',
        'url': 'https://drive.google.com/tramite'})

    docs = ficha(cliente, admin, cliente_id)['documentos']
    nombres = {d['nombre'] for d in docs}
    assert {'Carpeta compartida', 'Soporte del trámite'} <= nombres, docs
    sobre = {d['nombre']: d['sobre'] for d in docs}
    assert sobre['Soporte del trámite'] == 'un trámite'
    assert sobre['Carpeta compartida'] == 'el cliente'
