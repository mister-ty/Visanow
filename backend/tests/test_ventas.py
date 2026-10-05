"""Actividades 3.3 y 3.4 — cotizar y convertir en venta (RF-013, RF-014, RF-040).

El precio depende de cuántas personas viajan y la lista lo dice: adelantos para
una son $700.000 y para cuatro $2.300.000, que no es cuatro veces. Hoy esa
cuenta se hace de cabeza o se copia de una cotización vieja, que puede ser de
otra época de precios.
"""
import datetime as dt

import pytest
from sqlalchemy import select, text

from app.models.esquema import Paises, Servicios
from tests.conftest import entrar


@pytest.fixture
def comercial(cliente, usuario):
    p = usuario('comercial')
    return entrar(cliente, p), p


@pytest.fixture
def familia(cliente, comercial):
    """Un cliente con tres personas que viajan: el caso típico de VisaNow."""
    cab, _ = comercial
    c = cliente.post('/api/v1/clientes', headers=cab,
                     json={'nombre': 'Carolina Vélez Duque'}).json()
    g = cliente.post('/api/v1/grupos', headers=cab,
                     json={'cliente_contacto_id': c['id'], 'nombre': 'Familia Vélez'}).json()
    for nombre in ('Carolina Vélez Duque', 'Andrés Vélez Duque', 'Sofía Vélez Duque'):
        cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'grupo_id': g['id'], 'nombre': nombre})
    return c['id']


def servicio_id(db, codigo: str) -> int:
    return db.scalar(select(Servicios.id).where(Servicios.codigo == codigo))


def crear_lead(cliente, cab, cliente_id, **extra):
    r = cliente.post('/api/v1/oportunidades', headers=cab, json={
        'cliente_id': cliente_id, 'proxima_accion': 'Enviar cotización', **extra})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ cotizar

def test_el_precio_sale_del_catalogo_y_no_es_lineal(cliente, comercial, db):
    """Cuatro personas no cuestan cuatro veces una. Es exactamente la cuenta que
    hoy se hace de cabeza."""
    cab, _ = comercial
    adelantos = servicio_id(db, 'adelantos')

    una = cliente.post('/api/v1/cotizar', headers=cab,
                       json={'servicio_id': adelantos, 'personas': 1}).json()
    cuatro = cliente.post('/api/v1/cotizar', headers=cab,
                          json={'servicio_id': adelantos, 'personas': 4}).json()

    assert una['valor_lista'] == 700000
    assert cuatro['valor_lista'] == 2300000
    assert cuatro['valor_lista'] < una['valor_lista'] * 4, 'el grupo tiene descuento por volumen'
    assert cuatro['valor_pactado'] == 2300000 and cuatro['descuento'] == 0


def test_el_descuento_se_resta_del_valor_de_lista(cliente, comercial, db):
    cab, _ = comercial
    c = cliente.post('/api/v1/cotizar', headers=cab, json={
        'servicio_id': servicio_id(db, 'adelantos'), 'personas': 1, 'descuento': 100000}).json()
    assert c['valor_lista'] == 700000 and c['descuento'] == 100000
    assert c['valor_pactado'] == 600000


def test_si_dan_el_precio_negociado_el_sistema_deduce_cuanto_se_rebajo(cliente, comercial, db):
    """Así el sistema siempre puede decir cuánto se rebajó y sobre qué, que es
    lo que después hay que poder explicarle a Finanzas."""
    cab, _ = comercial
    c = cliente.post('/api/v1/cotizar', headers=cab, json={
        'servicio_id': servicio_id(db, 'adelantos'), 'personas': 1,
        'valor_pactado': 550000}).json()
    assert c['valor_lista'] == 700000
    assert c['valor_pactado'] == 550000 and c['descuento'] == 150000


def test_la_tasa_consular_se_informa_pero_no_suma_al_precio(cliente, comercial, db):
    """Son 185 dólares por persona que el cliente le paga directo al consulado.
    Lo confirmó la administradora el 03/10: no es plata de VisaNow."""
    cab, _ = comercial
    c = cliente.post('/api/v1/cotizar', headers=cab, json={
        'servicio_id': servicio_id(db, 'asesoria_usa'), 'personas': 3}).json()

    assert c['tasa_consular_valor'] == 185 and c['tasa_consular_moneda'] == 'USD'
    assert c['tasa_consular_total'] == 555, '185 por cada una de las tres'
    assert c['valor_pactado'] == c['valor_lista'], 'la tasa no entra en el valor pactado'
    assert any('directamente al consulado' in a for a in c['avisos'])


def test_un_grupo_mas_grande_que_la_lista_avisa_en_vez_de_inventar(cliente, comercial, db):
    """La lista llega hasta cuatro personas. Para seis no hay tarifa: se toma la
    mayor como base y se dice que se negocia, en vez de multiplicar y mentir."""
    cab, _ = comercial
    c = cliente.post('/api/v1/cotizar', headers=cab, json={
        'servicio_id': servicio_id(db, 'adelantos'), 'personas': 6}).json()
    assert c['valor_lista'] == 2300000, 'toma la tarifa de cuatro como base'
    assert any('se negocia' in a for a in c['avisos'])


def test_se_cotiza_con_la_tarifa_del_dia_de_la_venta_y_no_con_la_ultima(cliente, comercial, db):
    """Hay dos épocas de precios en el catálogo. Cotizar una venta de hace meses
    con los precios de hoy la deja mal."""
    cab, _ = comercial
    analisis = servicio_id(db, 'analisis_perfil')
    # Se arman las dos épocas aquí y no se dependen del seed: una instalación
    # nueva solo trae la vigente, y la prueba tiene que valer en las dos.
    db.execute(text("""insert into tarifas (servicio_id, valor, moneda, vigente_desde,
                                            vigente_hasta, personas, modalidad)
                       values (:s, 80000, 'COP', date '2026-01-01', date '2026-09-18',
                               1, 'total')"""), {'s': analisis})
    db.execute(text('update tarifas set valor = 95000 where servicio_id = :s '
                    "and vigente_hasta is null"), {'s': analisis})
    db.commit()

    vieja = cliente.post('/api/v1/cotizar', headers=cab, json={
        'servicio_id': analisis, 'personas': 1, 'fecha': '2026-03-15'}).json()
    nueva = cliente.post('/api/v1/cotizar', headers=cab, json={
        'servicio_id': analisis, 'personas': 1, 'fecha': '2026-10-01'}).json()
    assert vieja['valor_lista'] == 80000, 'una venta de marzo se cotiza con el precio de marzo'
    assert nueva['valor_lista'] == 95000
    assert vieja['vigente_desde'] != nueva['vigente_desde']


# ------------------------------------------------------- convertir en venta

def test_ganar_crea_la_venta_y_un_tramite_por_persona_sin_redigitar(cliente, comercial,
                                                                    familia, db):
    """RF-014. Hacerlo a mano significa volver a digitar cliente, servicio y país
    tres veces, que es donde se cuelan los errores."""
    cab, p = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    lead = crear_lead(cliente, cab, familia,
                      servicio_id=servicio_id(db, 'adelantos'), pais_id=pais)

    r = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json={})
    assert r.status_code == 201, r.text
    venta = r.json()

    assert venta['cantidad_solicitantes'] == 3
    assert venta['valor_pactado'] == 1700000, 'la tarifa de tres personas'
    assert venta['oportunidad_id'] == lead['id']
    assert venta['vendedor_id'] == p.u.id, 'el asesor de la oportunidad es el vendedor'
    assert len(venta['casos']) == 3, 'un trámite por cada persona que viaja'
    assert {c['solicitante'] for c in venta['casos']} == {
        'Carolina Vélez Duque', 'Andrés Vélez Duque', 'Sofía Vélez Duque'}

    # La oportunidad quedó ganada y cerrada
    o = cliente.get(f'/api/v1/oportunidades/{lead["id"]}', headers=cab).json()
    assert o['estado'] == 'ganado' and o['cerrado_en'] is not None


def test_los_tramites_nacen_con_responsable_proxima_accion_y_la_venta(cliente, comercial,
                                                                      familia, db):
    """RN-04: un caso activo tiene responsable y próxima acción. Si al convertir
    nacieran sin eso, entrarían al tablero ya incumpliendo la regla."""
    cab, p = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    lead = crear_lead(cliente, cab, familia,
                      servicio_id=servicio_id(db, 'adelantos'), pais_id=pais)
    venta = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar',
                         headers=cab, json={}).json()

    caso = cliente.get(f'/api/v1/casos/{venta["casos"][0]["id"]}',
                       headers=entrar(cliente, p)).json()
    assert caso['responsable_id'] == p.u.id
    assert caso['proxima_accion'] == 'Pedir documentos al cliente'
    assert caso['sin_venta'] is False, 'el trámite queda enlazado a la venta'
    assert caso['estado'] == 'registrado'

    historial = cliente.get(f'/api/v1/casos/{caso["id"]}/historial', headers=cab).json()
    assert any('al ganar la venta' in (h['observacion'] or '') for h in historial)


def test_el_saldo_de_la_venta_nueva_lo_calcula_la_vista(cliente, comercial, familia, db):
    """RN-01: una venta sin pagos deja la cartera en el valor pactado, y eso lo
    dice la vista, no una columna."""
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    lead = crear_lead(cliente, cab, familia,
                      servicio_id=servicio_id(db, 'adelantos'), pais_id=pais)
    venta = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar',
                         headers=cab, json={}).json()

    fila = db.execute(text('select saldo, estado_financiero from v_estado_financiero '
                           'where negocio_id = :n'), {'n': venta['id']}).first()
    assert float(fila[0]) == 1700000
    assert fila[1] == 'pendiente_anticipo'


def test_se_puede_vender_solo_a_algunas_personas_del_grupo(cliente, comercial, familia, db):
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    personas = cliente.get(f'/api/v1/solicitantes?cliente_id={familia}', headers=cab).json()
    lead = crear_lead(cliente, cab, familia,
                      servicio_id=servicio_id(db, 'adelantos'), pais_id=pais)

    venta = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json={
        'solicitantes_ids': [personas[0]['id']]}).json()
    assert len(venta['casos']) == 1
    assert venta['valor_pactado'] == 700000, 'la tarifa de una persona'


def test_no_se_puede_ganar_dos_veces_la_misma_oportunidad(cliente, comercial, familia, db):
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    lead = crear_lead(cliente, cab, familia,
                      servicio_id=servicio_id(db, 'adelantos'), pais_id=pais)
    assert cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar',
                        headers=cab, json={}).status_code == 201
    r = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json={})
    assert r.status_code == 409 and r.json()['codigo'] == 'oportunidad_cerrada'


def test_sin_personas_registradas_no_se_puede_convertir(cliente, comercial, db):
    """El trámite se abre sobre la persona, no sobre el cliente: sin personas no
    hay a quién tramitarle."""
    cab, _ = comercial
    solo = cliente.post('/api/v1/clientes', headers=cab,
                        json={'nombre': 'Esteban Solo Pérez'}).json()['id']
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    lead = crear_lead(cliente, cab, solo, servicio_id=servicio_id(db, 'adelantos'), pais_id=pais)

    r = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json={})
    assert r.status_code == 422 and r.json()['codigo'] == 'sin_solicitantes'

    # Pero sí se puede vender sin abrir trámites todavía
    r = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab,
                     json={'abrir_tramites': False})
    assert r.status_code == 201 and r.json()['casos'] == []


def test_el_descuento_pactado_al_ganar_queda_guardado(cliente, comercial, familia, db):
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    lead = crear_lead(cliente, cab, familia,
                      servicio_id=servicio_id(db, 'adelantos'), pais_id=pais)
    venta = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json={
        'valor_pactado': 1500000, 'observaciones': 'Descuento por ser referida'}).json()

    assert venta['valor_lista'] == 1700000
    assert venta['valor_pactado'] == 1500000
    assert venta['descuento'] == 200000
    assert venta['observaciones'] == 'Descuento por ser referida'
