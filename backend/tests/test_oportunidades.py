"""Actividades 3.1 y 3.2 — el embudo comercial (RF-010, RF-011, RF-012, RF-015).

Lo que se prueba es lo que hoy no se puede responder con los archivos: de dónde
salió cada cliente que compró, cuáles se enfriaron y por qué se perdieron los
que se perdieron.
"""
import pytest
from sqlalchemy import select, text

from app.models.esquema import Canales, Paises, Servicios
from tests.conftest import entrar

OPORTUNIDADES = '/api/v1/oportunidades'


@pytest.fixture
def comercial(cliente, usuario):
    p = usuario('comercial')
    return entrar(cliente, p), p


@pytest.fixture
def un_cliente(cliente, comercial):
    cab, _ = comercial
    return cliente.post('/api/v1/clientes', headers=cab,
                        json={'nombre': 'Daniela Ochoa Rivas'}).json()['id']


def crear_lead(cliente, cab, cliente_id, **extra):
    cuerpo = {'cliente_id': cliente_id, 'proxima_accion': 'Llamar para calificar', **extra}
    r = cliente.post(OPORTUNIDADES, headers=cab, json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------- alta

def test_un_lead_nace_con_dueno_y_con_proximo_paso(cliente, comercial, un_cliente, db):
    """Sin asesor no lo trabaja nadie, y sin próxima acción no está en el embudo:
    está olvidado. Es la misma regla que RN-04 pide para los trámites."""
    cab, p = comercial
    canal = db.scalar(select(Canales.id).where(Canales.codigo == 'instagram'))
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    o = crear_lead(cliente, cab, un_cliente, canal_id=canal, pais_id=pais,
                   valor_estimado=1250000, campania='Reel de septiembre')

    assert o['estado'] == 'nuevo_lead' and o['es_cierre'] is False
    assert o['asesor_id'] == p.u.id, 'queda a nombre de quien lo crea'
    assert o['canal_id'] == canal and o['campania'] == 'Reel de septiembre'
    assert o['valor_estimado'] == 1250000
    assert o['dias_sin_contacto'] == 0


def test_un_lead_sin_proxima_accion_se_rechaza(cliente, comercial, un_cliente):
    cab, _ = comercial
    r = cliente.post(OPORTUNIDADES, headers=cab, json={'cliente_id': un_cliente})
    assert r.status_code == 422


def test_se_guarda_quien_lo_recomendo(cliente, comercial, un_cliente):
    """El canal que más vende en los archivos es «recomendación», con 97 ventas.
    Sin saber quién recomendó, no hay a quién agradecerle ni a quién pedirle más."""
    cab, _ = comercial
    otro = cliente.post('/api/v1/clientes', headers=cab,
                        json={'nombre': 'Felipe Ochoa Rivas'}).json()
    o = crear_lead(cliente, cab, un_cliente, referido_por_cliente_id=otro['id'])
    detalle = cliente.get(f'{OPORTUNIDADES}/{o["id"]}', headers=cab).json()
    assert detalle['id'] == o['id']


# ------------------------------------------------------------------- el embudo

def test_la_oportunidad_recorre_el_embudo(cliente, comercial, un_cliente):
    cab, _ = comercial
    o = crear_lead(cliente, cab, un_cliente)
    for destino in ('contactado', 'calificado', 'cotizacion_enviada', 'seguimiento'):
        r = cliente.post(f'{OPORTUNIDADES}/{o["id"]}/estado', headers=cab,
                         json={'codigo_destino': destino,
                               'proxima_accion': f'Siguiente paso tras {destino}'})
        assert r.status_code == 200, r.text
        assert r.json()['estado'] == destino
        assert r.json()['cerrado_en'] is None


def test_perder_una_oportunidad_exige_decir_por_que(cliente, comercial, un_cliente):
    """RF-015. «No respondió» y «precio» llevan a decisiones distintas; «se
    perdió» no lleva a ninguna."""
    cab, _ = comercial
    o = crear_lead(cliente, cab, un_cliente)

    r = cliente.post(f'{OPORTUNIDADES}/{o["id"]}/estado', headers=cab,
                     json={'codigo_destino': 'perdido'})
    assert r.status_code == 422 and r.json()['codigo'] == 'falta_motivo'

    r = cliente.post(f'{OPORTUNIDADES}/{o["id"]}/estado', headers=cab,
                     json={'codigo_destino': 'perdido', 'motivo_perdida': 'inventado'})
    assert r.status_code == 422 and 'catálogo' in r.json()['detalle']

    r = cliente.post(f'{OPORTUNIDADES}/{o["id"]}/estado', headers=cab, json={
        'codigo_destino': 'perdido', 'motivo_perdida': 'precio',
        'nota': 'Le pareció caro contra la competencia'})
    assert r.status_code == 200, r.text
    assert r.json()['es_cierre'] is True and r.json()['cerrado_en'] is not None
    assert r.json()['motivo_perdida_id'] is not None


def test_mover_una_oportunidad_abierta_exige_proxima_accion(cliente, comercial, un_cliente, db):
    cab, _ = comercial
    o = crear_lead(cliente, cab, un_cliente)
    # Se le quita la próxima acción a propósito
    db.execute(text('update oportunidades set proxima_accion = null where id = :i'), {'i': o['id']})
    db.commit()
    r = cliente.post(f'{OPORTUNIDADES}/{o["id"]}/estado', headers=cab,
                     json={'codigo_destino': 'contactado'})
    assert r.status_code == 422 and r.json()['codigo'] == 'falta_proxima_accion'


def test_ganar_no_exige_motivo_y_cierra(cliente, comercial, un_cliente):
    cab, _ = comercial
    o = crear_lead(cliente, cab, un_cliente)
    r = cliente.post(f'{OPORTUNIDADES}/{o["id"]}/estado', headers=cab,
                     json={'codigo_destino': 'ganado'})
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'ganado' and r.json()['cerrado_en'] is not None


# ------------------------------------------------------------------- las listas

def test_el_embudo_cuenta_cuantas_y_cuanto_hay_en_cada_paso(cliente, comercial, un_cliente):
    cab, _ = comercial
    crear_lead(cliente, cab, un_cliente, valor_estimado=1000000)
    o = crear_lead(cliente, cab, un_cliente, valor_estimado=500000)
    cliente.post(f'{OPORTUNIDADES}/{o["id"]}/estado', headers=cab,
                 json={'codigo_destino': 'contactado', 'proxima_accion': 'Enviar cotización'})

    pasos = {p['codigo']: p for p in cliente.get(f'{OPORTUNIDADES}/embudo', headers=cab).json()}
    assert pasos['nuevo_lead']['cuantas'] == 1
    assert pasos['nuevo_lead']['valor_estimado'] == 1000000
    assert pasos['contactado']['cuantas'] == 1
    assert [p['orden'] for p in pasos.values()] == sorted(p['orden'] for p in pasos.values())


def test_las_cerradas_no_estorban_en_la_lista_del_dia(cliente, comercial, un_cliente):
    cab, _ = comercial
    viva = crear_lead(cliente, cab, un_cliente)
    muerta = crear_lead(cliente, cab, un_cliente)
    cliente.post(f'{OPORTUNIDADES}/{muerta["id"]}/estado', headers=cab,
                 json={'codigo_destino': 'perdido', 'motivo_perdida': 'no_respondio'})

    abiertas = cliente.get(OPORTUNIDADES, headers=cab).json()
    assert [o['id'] for o in abiertas['items']] == [viva['id']]
    todas = cliente.get(f'{OPORTUNIDADES}?incluir_cerradas=true', headers=cab).json()
    assert {o['id'] for o in todas['items']} == {viva['id'], muerta['id']}


def test_los_leads_frios_se_pueden_pescar(cliente, comercial, un_cliente, db):
    """Un lead que nadie tocó en un mes es el que más se pierde, y hoy no hay
    forma de encontrarlo: no existe la lista."""
    cab, _ = comercial
    frio = crear_lead(cliente, cab, un_cliente)
    tibio = crear_lead(cliente, cab, un_cliente)
    db.execute(text("update oportunidades set creado_en = now() - interval '40 days' "
                    'where id = :i'), {'i': frio['id']})
    db.commit()

    frios = cliente.get(f'{OPORTUNIDADES}?frias_desde=30', headers=cab).json()
    assert [o['id'] for o in frios['items']] == [frio['id']]
    assert tibio['id'] not in [o['id'] for o in frios['items']]


def test_registrar_un_contacto_lo_saca_de_la_lista_de_frios(cliente, comercial, un_cliente, db):
    cab, _ = comercial
    o = crear_lead(cliente, cab, un_cliente)
    db.execute(text("update oportunidades set creado_en = now() - interval '40 days' "
                    'where id = :i'), {'i': o['id']})
    db.commit()
    assert cliente.get(f'{OPORTUNIDADES}?frias_desde=30', headers=cab).json()['total'] == 1

    r = cliente.post(f'{OPORTUNIDADES}/{o["id"]}/contacto', headers=cab,
                     json={'proxima_accion': 'Mandar la cotización el lunes'})
    assert r.status_code == 200, r.text
    assert r.json()['dias_sin_contacto'] == 0
    assert cliente.get(f'{OPORTUNIDADES}?frias_desde=30', headers=cab).json()['total'] == 0


def test_el_canal_y_la_campania_se_pueden_filtrar(cliente, comercial, un_cliente, db):
    """Es la pregunta que hoy nadie puede responder: qué campaña trae clientes."""
    cab, _ = comercial
    instagram = db.scalar(select(Canales.id).where(Canales.codigo == 'instagram'))
    recomendado = db.scalar(select(Canales.id).where(Canales.codigo == 'recomendado'))
    por_insta = crear_lead(cliente, cab, un_cliente, canal_id=instagram)
    crear_lead(cliente, cab, un_cliente, canal_id=recomendado)

    r = cliente.get(f'{OPORTUNIDADES}?canal_id={instagram}', headers=cab).json()
    assert [o['id'] for o in r['items']] == [por_insta['id']]


# ----------------------------------------------------------------- el alcance

def test_una_comercial_con_alcance_propios_no_ve_las_de_la_otra(cliente, db, usuario, un_cliente):
    """RNF-03 en el embudo: Angie no tiene por qué ver el pipeline de Isa."""
    from app.services import usuarios as servicio_usuarios

    admin = usuario('administradora')
    una = usuario('comercial')
    otra = usuario('comercial')
    servicio_usuarios.editar(db, admin.u, otra.u.id, alcance='propios')
    db.commit()

    suya = crear_lead(cliente, entrar(cliente, una), un_cliente)
    cab_otra = entrar(cliente, otra)

    assert cliente.get(OPORTUNIDADES, headers=cab_otra).json()['total'] == 0
    r = cliente.get(f'{OPORTUNIDADES}/{suya["id"]}', headers=cab_otra)
    assert r.status_code == 404, 'la URL directa se salta el alcance'


# ------------------------------------------------- la regla de comisión (D-03)

def test_la_regla_de_comision_de_angie_quedo_sembrada_tal_como_la_dijo(db):
    """D-03, respondida el 03/10: Angie comisiona el 7 % del valor de la venta;
    sobre sus primeras 10 ventas premium del periodo se le paga el 10 %, y de
    ahí en adelante vuelve al 7 %. La renovación no cuenta para esas diez. Se
    gana cuando el cliente termina de pagar, y solo sobre el valor del servicio:
    la tasa consular es plata del consulado."""
    from app.models.esquema import ComisionesReglas

    regla = db.scalar(select(ComisionesReglas).where(ComisionesReglas.activo.is_(True)))
    assert regla is not None, 'la regla de D-03 tiene que estar sembrada'
    assert float(regla.porcentaje) == 7.0
    assert regla.base == 'vendido', 'el 7 % es del valor de la venta'
    assert regla.meta_cantidad == 10

    d = regla.definicion
    # Ganarla al pago total es el disparador, no la base: por eso va aquí y no
    # en la columna `base`, que solo admite vendido / cobrado / neto_recibido.
    assert d['se_causa_con'] == 'pago_total'
    assert 'recaudo_terceros' in d['excluye_de_la_base'], 'la tasa consular no comisiona'
    assert d['porcentaje_meta'] == 10.0
    assert 'renovacion' in d['servicios_excluidos_de_la_meta']


def test_la_tasa_consular_no_entra_en_la_base_de_comision(db):
    """Hay 39 ventas de tasa consular por 40 millones en los archivos. Si
    entraran en la base, la comisión saldría inflada el 11,7 %."""
    from app.models.esquema import ComisionesReglas, Servicios

    assert db.scalar(select(Servicios).where(Servicios.codigo == 'pago_visa')).tipo == \
        'recaudo_terceros'
    for regla in db.scalars(select(ComisionesReglas)):
        assert 'recaudo_terceros' in regla.definicion['excluye_de_la_base']
