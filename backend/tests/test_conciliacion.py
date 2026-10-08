"""Conciliación del extracto bancario (RF-044, actividad 4.4).

La administradora explicó el 07/10 cómo lo resuelve hoy: «el cliente manda el
soporte por whatsapp y también me llega la notificación del correo, entonces a
veces el nombre es el de ellos otras veces es de otra persona, pero a la final el
cliente nos avisa y nos comparte el pantallazo».

De ahí sale lo que estas pruebas vigilan: que se cruce por valor y fecha, que no
se cruce por nombre, que lo ambiguo no se resuelva solo, y que lo que no es plata
de un cliente se pueda sacar de la bandeja sin inventarle un pago.
"""
import datetime as dt

import pytest
from sqlalchemy import select

from app.models.esquema import MovimientosBanco, Paises, Servicios
from tests.conftest import entrar


@pytest.fixture
def finanzas(cliente, usuario):
    return entrar(cliente, usuario('finanzas'))


@pytest.fixture
def vendedora(cliente, db, usuario):
    p = usuario('comercial')
    p.u.nombre = 'Angie Lorena'
    db.commit()
    return entrar(cliente, p), p


def servicio_id(db, codigo: str) -> int:
    return db.scalar(select(Servicios.id).where(Servicios.codigo == codigo))


def vender(cliente, cab, db, *, nombre, valor=None, fecha=None, servicio='asesoria_usa'):
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': nombre}).json()
    cliente.post('/api/v1/solicitantes', headers=cab,
                 json={'cliente_id': c['id'], 'nombre': nombre})
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    lead = cliente.post('/api/v1/oportunidades', headers=cab, json={
        'cliente_id': c['id'], 'servicio_id': servicio_id(db, servicio), 'pais_id': pais,
        'proxima_accion': 'Cotizar'}).json()
    cuerpo = {}
    if valor is not None:
        cuerpo['valor_pactado'] = valor
    if fecha:
        cuerpo['fecha_venta'] = fecha
    r = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


def mov(fecha, valor, *, banco='BANCOLOMBIA', descripcion='TRANSFERENCIA CTA SUC VIRTUAL',
        fila=None, nota_cliente=None):
    d = {'fecha': fecha, 'valor': valor, 'banco': banco, 'descripcion': descripcion}
    if fila is not None:
        d['fila'] = fila
    if nota_cliente:
        d['nota_cliente'] = nota_cliente
    return d


def importar(cliente, cab, movimientos, archivo='CUENTAS VISANOW.xlsx', hoja='EXTRACTO'):
    r = cliente.post('/api/v1/conciliacion/importar', headers=cab,
                     json={'movimientos': movimientos, 'archivo': archivo, 'hoja': hoja})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------- importación

def test_importar_el_mismo_extracto_dos_veces_no_duplica(cliente, finanzas):
    """Quien importa no deberia tener que acordarse de si ya lo hizo."""
    filas = [mov('2026-01-08', 240000, fila=1), mov('2026-01-08', 200000, fila=2)]

    primera = importar(cliente, finanzas, filas)
    assert primera['nuevos'] == 2 and primera['repetidos'] == 0

    segunda = importar(cliente, finanzas, filas)
    assert segunda['nuevos'] == 0 and segunda['repetidos'] == 2

    bandeja = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()
    assert bandeja['total'] == 2


def test_dos_consignaciones_iguales_el_mismo_dia_son_dos_movimientos(cliente, finanzas):
    """Dos clientes que consignan 200.000 el mismo dia son dos, no uno.

    Sin la fila de origen en la huella, el segundo se perderia en cada
    importacion y la caja no cuadraria nunca.
    """
    r = importar(cliente, finanzas, [mov('2026-01-08', 200000, fila=10),
                                     mov('2026-01-08', 200000, fila=11)])
    assert r['nuevos'] == 2

    bandeja = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()
    assert bandeja['total'] == 2
    assert bandeja['suma'] == 400000


def test_las_filas_sin_fecha_o_sin_valor_no_entran_y_se_cuentan(cliente, finanzas):
    """No se inventan: se dice cuantas lineas del archivo no entraron."""
    r = cliente.post('/api/v1/conciliacion/importar', headers=finanzas, json={
        'movimientos': [mov('2026-01-08', 240000, fila=1),
                        mov('2026-01-09', 0, fila=2)]})
    assert r.status_code == 201, r.text
    assert r.json()['nuevos'] == 1 and r.json()['sin_valor'] == 1


# ------------------------------------------------------------------- cruce

def test_el_cruce_automatico_cuadra_lo_que_no_tiene_duda(cliente, vendedora, finanzas, db):
    """Un solo pago candidato y del mismo dia: se cuadra sin preguntar."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Danilo Ramirez Cruce', valor=240000)
    cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': 240000, 'fecha': '2026-01-08'})

    importar(cliente, finanzas, [mov('2026-01-08', 240000, fila=1)])
    r = cliente.post('/api/v1/conciliacion/cruzar', headers=finanzas, json={})
    assert r.status_code == 200, r.text
    assert r.json()['cuadrados'] == 1, r.json()

    conciliados = cliente.get('/api/v1/conciliacion/movimientos?estado=conciliado',
                              headers=finanzas).json()
    assert conciliados['total'] == 1
    assert conciliados['items'][0]['negocio_id'] == venta['id']
    assert conciliados['items'][0]['cliente'] == 'Danilo Ramirez Cruce'


def test_dos_pagos_del_mismo_valor_no_se_cuadran_solos(cliente, vendedora, finanzas, db):
    """Equivocarse aqui es marcar pagada la venta de otro, asi que no se adivina."""
    cab, _ = vendedora
    for nombre in ('Primera Delmismo Valor', 'Segunda Delmismo Valor'):
        v = vender(cliente, cab, db, nombre=nombre, valor=200000)
        cliente.post('/api/v1/pagos', headers=finanzas, json={
            'negocio_id': v['id'], 'monto_bruto': 200000, 'fecha': '2026-01-08'})

    importar(cliente, finanzas, [mov('2026-01-08', 200000, fila=1)])
    r = cliente.post('/api/v1/conciliacion/cruzar', headers=finanzas, json={}).json()
    assert r['cuadrados'] == 0 and r['ambiguos'] == 1, r

    sin_cuadrar = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()
    movimiento = sin_cuadrar['items'][0]
    sug = cliente.get(f'/api/v1/conciliacion/movimientos/{movimiento["id"]}/candidatos',
                      headers=finanzas).json()
    assert len(sug['candidatos']) == 2, 'se le muestran las dos para que decida'
    assert sug['sin_duda'] is False


def test_no_se_cruza_por_el_nombre_de_quien_consigna(cliente, vendedora, finanzas, db):
    """«a veces el nombre es el de ellos otras veces es de otra persona».

    El movimiento trae el nombre del cliente en la descripcion, pero el valor no
    coincide: no puede cuadrar. Si cruzara por nombre, marcaria pagada una venta
    con una plata que no es.
    """
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Georgina Garcia Nombre', valor=1400000)
    cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': 1400000, 'fecha': '2026-01-06'})

    importar(cliente, finanzas, [mov('2026-01-06', 50000, fila=1,
                                     descripcion='TRANSFERENCIA GEORGINA GARCIA NOMBRE')])
    r = cliente.post('/api/v1/conciliacion/cruzar', headers=finanzas, json={}).json()
    assert r['cuadrados'] == 0 and r['sin_candidato'] == 1, r


def test_el_cruce_respeta_los_dias_de_gracia(cliente, vendedora, finanzas, db):
    """Una transferencia de la noche aparece al dia siguiente en el banco."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Transferencia Denoche Cliente', valor=640000)
    cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': 640000, 'fecha': '2026-01-02'})

    importar(cliente, finanzas, [mov('2026-01-03', 640000, fila=1)])
    movimiento = cliente.get('/api/v1/conciliacion/movimientos',
                             headers=finanzas).json()['items'][0]
    sug = cliente.get(f'/api/v1/conciliacion/movimientos/{movimiento["id"]}/candidatos',
                      headers=finanzas).json()
    assert len(sug['candidatos']) == 1
    assert sug['candidatos'][0]['dias_de_diferencia'] == 1
    assert sug['candidatos'][0]['exacto'] is False
    # No es del mismo dia, asi que el automatico no lo toca: lo confirma alguien.
    assert sug['sin_duda'] is False
    assert cliente.post('/api/v1/conciliacion/cruzar', headers=finanzas,
                        json={}).json()['cuadrados'] == 0


# ----------------------------------------------------------- conciliar a mano

def test_cuadrar_contra_una_venta_crea_el_pago_con_los_datos_del_banco(cliente, vendedora,
                                                                       finanzas, db):
    """El caso de todos los dias: el cliente avisa que consigno y el pago no
    esta registrado. Entonces nace del movimiento, con la fecha y el valor del
    banco, que son mas confiables que los que alguien teclee despues."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Roger Monterroza Banco', valor=1000000)
    importar(cliente, finanzas, [mov('2026-01-08', 1000000, fila=1,
                                     nota_cliente='ROGER  MONTERROZA Y FAMILIA')])
    movimiento = cliente.get('/api/v1/conciliacion/movimientos',
                             headers=finanzas).json()['items'][0]
    assert movimiento['nota_cliente'] == 'ROGER  MONTERROZA Y FAMILIA'

    r = cliente.post(f'/api/v1/conciliacion/movimientos/{movimiento["id"]}/conciliar',
                     headers=finanzas, json={'negocio_id': venta['id']})
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'conciliado' and r.json()['pago_id'] is not None

    pagos = cliente.get(f'/api/v1/pagos?negocio_id={venta["id"]}', headers=finanzas).json()
    assert pagos['total'] == 1, pagos
    assert pagos['items'][0]['monto_bruto'] == 1000000
    assert pagos['items'][0]['fecha'] == '2026-01-08', 'la fecha es la del banco'


def test_cuadrar_la_venta_completa_causa_la_comision(cliente, vendedora, finanzas, db):
    """La conciliacion no vive aparte: el pago que crea tambien gana la comision."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Pago Completo Porbanco', valor=1000000)
    importar(cliente, finanzas, [mov('2026-01-08', 1000000, fila=1)])
    movimiento = cliente.get('/api/v1/conciliacion/movimientos',
                             headers=finanzas).json()['items'][0]
    cliente.post(f'/api/v1/conciliacion/movimientos/{movimiento["id"]}/conciliar',
                 headers=finanzas, json={'negocio_id': venta['id']})

    comisiones = cliente.get('/api/v1/comisiones', headers=finanzas).json()
    suya = next(c for c in comisiones if c['negocio_id'] == venta['id'])
    assert suya['estado'] == 'causada', 'la venta quedo pagada, asi que la comision se gano'


def test_el_mismo_pago_no_se_puede_cuadrar_dos_veces(cliente, vendedora, finanzas, db):
    """La misma plata no puede entrar dos veces."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Doble Cuadre Cliente', valor=300000)
    pago = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': 300000, 'fecha': '2026-02-10'}).json()

    importar(cliente, finanzas, [mov('2026-02-10', 300000, fila=1),
                                 mov('2026-02-10', 300000, fila=2)])
    items = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()['items']

    primero = cliente.post(f'/api/v1/conciliacion/movimientos/{items[0]["id"]}/conciliar',
                           headers=finanzas, json={'pago_id': pago['id']})
    assert primero.status_code == 200, primero.text

    segundo = cliente.post(f'/api/v1/conciliacion/movimientos/{items[1]["id"]}/conciliar',
                           headers=finanzas, json={'pago_id': pago['id']})
    assert segundo.status_code == 409
    assert segundo.json()['codigo'] == 'pago_ya_conciliado'


def test_no_se_cuadran_valores_distintos(cliente, vendedora, finanzas, db):
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Valor Distinto Cliente', valor=500000)
    pago = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': 500000, 'fecha': '2026-02-10'}).json()

    importar(cliente, finanzas, [mov('2026-02-10', 480000, fila=1)])
    movimiento = cliente.get('/api/v1/conciliacion/movimientos',
                             headers=finanzas).json()['items'][0]
    r = cliente.post(f'/api/v1/conciliacion/movimientos/{movimiento["id"]}/conciliar',
                     headers=finanzas, json={'pago_id': pago['id']})
    assert r.status_code == 422 and r.json()['codigo'] == 'valores_distintos'


# -------------------------------------------------------------- descartar

def test_descartar_exige_motivo_y_no_borra_la_linea(cliente, finanzas, db):
    """En el extracto real hay intereses de ahorro de cinco pesos y reversos.

    Descartar no es borrar: la linea sigue con su motivo, porque el extracto
    tiene que seguir cuadrando contra el banco.
    """
    importar(cliente, finanzas, [mov('2026-01-02', 6.21, fila=1,
                                     descripcion='ABONO INTERESES AHORROS')])
    movimiento = cliente.get('/api/v1/conciliacion/movimientos',
                             headers=finanzas).json()['items'][0]

    sin_motivo = cliente.post(f'/api/v1/conciliacion/movimientos/{movimiento["id"]}/descartar',
                              headers=finanzas, json={'motivo': ''})
    assert sin_motivo.status_code == 422

    r = cliente.post(f'/api/v1/conciliacion/movimientos/{movimiento["id"]}/descartar',
                     headers=finanzas, json={'motivo': 'Intereses del banco, no es de un cliente'})
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'descartado'

    assert db.get(MovimientosBanco, movimiento['id']) is not None, 'la linea no se borra'
    bandeja = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()
    assert bandeja['total'] == 0, 'y sale de la bandeja'


def test_deshacer_devuelve_el_movimiento_a_la_bandeja(cliente, vendedora, finanzas, db):
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Deshacer Cuadre Cliente', valor=700000)
    importar(cliente, finanzas, [mov('2026-03-05', 700000, fila=1)])
    movimiento = cliente.get('/api/v1/conciliacion/movimientos',
                             headers=finanzas).json()['items'][0]
    cliente.post(f'/api/v1/conciliacion/movimientos/{movimiento["id"]}/conciliar',
                 headers=finanzas, json={'negocio_id': venta['id']})

    r = cliente.post(f'/api/v1/conciliacion/movimientos/{movimiento["id"]}/deshacer',
                     headers=finanzas)
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'sin_conciliar' and r.json()['pago_id'] is None
    # El pago no se borra: lo que se deshace es la afirmacion de que son el mismo.
    pagos = cliente.get(f'/api/v1/pagos?negocio_id={venta["id"]}', headers=finanzas).json()
    assert pagos['total'] == 1, pagos


# ------------------------------------- parcial, duplicado y reversado
#
# RF-044 los enumera: «marcar conciliado, parcial, duplicado, reversado o no
# identificado». Cada uno existe porque en el extracto real hay lineas que no
# son ninguno de los otros.

def test_un_movimiento_que_cubre_a_medias_queda_parcial(cliente, vendedora, finanzas, db):
    """El cliente paga una venta con dos transferencias."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Parcial Dostransfer Cliente', valor=800000)
    pago = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': 800000, 'fecha': '2026-02-01'}).json()

    importar(cliente, finanzas, [mov('2026-02-01', 500000, fila=1)])
    m = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()['items'][0]

    r = cliente.post(f'/api/v1/conciliacion/movimientos/{m["id"]}/parcial',
                     headers=finanzas, json={'pago_id': pago['id']})
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'parcial'
    assert r.json()['pago_id'] == pago['id']


def test_un_parcial_del_mismo_valor_no_es_parcial_sino_cuadre(cliente, vendedora,
                                                              finanzas, db):
    """Si los valores son iguales no es «a medias», es un cuadre."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Parcial Igual Cliente', valor=300000)
    pago = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': 300000, 'fecha': '2026-02-02'}).json()
    importar(cliente, finanzas, [mov('2026-02-02', 300000, fila=1)])
    m = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()['items'][0]

    r = cliente.post(f'/api/v1/conciliacion/movimientos/{m["id"]}/parcial',
                     headers=finanzas, json={'pago_id': pago['id']})
    assert r.status_code == 422 and r.json()['codigo'] == 'mismo_valor'


def test_un_pago_cubierto_a_medias_sigue_siendo_candidato(cliente, vendedora, finanzas, db):
    """Marcar un parcial no puede sacar ese pago de la lista: falta la otra mitad."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Mitad Ymitad Cliente', valor=800000)
    pago = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta['id'], 'monto_bruto': 800000, 'fecha': '2026-02-03'}).json()

    importar(cliente, finanzas, [mov('2026-02-03', 500000, fila=1),
                                 mov('2026-02-03', 800000, fila=2)])
    items = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()['items']
    por_valor = {float(i['valor']): i['id'] for i in items}
    cliente.post(f'/api/v1/conciliacion/movimientos/{por_valor[500000.0]}/parcial',
                 headers=finanzas, json={'pago_id': pago['id']})

    sug = cliente.get(f'/api/v1/conciliacion/movimientos/{por_valor[800000.0]}/candidatos',
                      headers=finanzas).json()
    assert [c['pago_id'] for c in sug['candidatos']] == [pago['id']], sug


def test_marcar_duplicado_apunta_al_bueno_y_no_borra_la_linea(cliente, finanzas, db):
    """El banco reporto dos veces la misma transferencia."""
    importar(cliente, finanzas, [mov('2026-02-05', 450000, fila=1),
                                 mov('2026-02-05', 450000, fila=2)])
    items = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()['items']
    bueno, repetido = items[0]['id'], items[1]['id']

    r = cliente.post(f'/api/v1/conciliacion/movimientos/{repetido}/duplicado',
                     headers=finanzas, json={'duplicado_de_id': bueno})
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'duplicado'
    assert r.json()['duplicado_de_id'] == bueno

    assert db.get(MovimientosBanco, repetido) is not None, 'la linea no se borra'
    bandeja = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()
    assert bandeja['total'] == 1, 'y deja de pedir que alguien le encuentre dueno'


def test_un_duplicado_no_puede_ser_de_si_mismo_ni_encadenarse(cliente, finanzas):
    importar(cliente, finanzas, [mov('2026-02-06', 150000, fila=1),
                                 mov('2026-02-06', 150000, fila=2),
                                 mov('2026-02-06', 150000, fila=3)])
    items = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()['items']
    a, b, c = items[0]['id'], items[1]['id'], items[2]['id']

    solo = cliente.post(f'/api/v1/conciliacion/movimientos/{a}/duplicado',
                        headers=finanzas, json={'duplicado_de_id': a})
    assert solo.status_code == 422 and solo.json()['codigo'] == 'duplicado_de_si_mismo'

    cliente.post(f'/api/v1/conciliacion/movimientos/{b}/duplicado',
                 headers=finanzas, json={'duplicado_de_id': a})
    cadena = cliente.post(f'/api/v1/conciliacion/movimientos/{c}/duplicado',
                          headers=finanzas, json={'duplicado_de_id': b})
    assert cadena.status_code == 422 and cadena.json()['codigo'] == 'cadena_de_duplicados'


def test_marcar_reversado_exige_motivo(cliente, finanzas):
    """En el extracto real hay varias: «Reverso COMPRA INTLTRI»."""
    importar(cliente, finanzas, [mov('2026-01-03', 19799.81, fila=1,
                                     descripcion='Reverso COMPRA INTLTRIP')])
    m = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()['items'][0]

    assert cliente.post(f'/api/v1/conciliacion/movimientos/{m["id"]}/reversado',
                        headers=finanzas, json={'motivo': ''}).status_code == 422

    r = cliente.post(f'/api/v1/conciliacion/movimientos/{m["id"]}/reversado',
                     headers=finanzas, json={'motivo': 'El banco devolvio la compra'})
    assert r.status_code == 200 and r.json()['estado'] == 'reversado'


def test_deshacer_limpia_el_apunte_de_duplicado(cliente, finanzas):
    importar(cliente, finanzas, [mov('2026-02-07', 90000, fila=1),
                                 mov('2026-02-07', 90000, fila=2)])
    items = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()['items']
    cliente.post(f'/api/v1/conciliacion/movimientos/{items[1]["id"]}/duplicado',
                 headers=finanzas, json={'duplicado_de_id': items[0]['id']})

    r = cliente.post(f'/api/v1/conciliacion/movimientos/{items[1]["id"]}/deshacer',
                     headers=finanzas).json()
    assert r['estado'] == 'sin_conciliar' and r['duplicado_de_id'] is None


def test_un_movimiento_cuadrado_no_cambia_de_estado_sin_deshacer(cliente, vendedora,
                                                                 finanzas, db):
    """Cambiarle el estado a uno ya cuadrado dejaria el cruce colgando."""
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Cuadrado Firme Cliente', valor=410000)
    importar(cliente, finanzas, [mov('2026-02-08', 410000, fila=1)])
    m = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()['items'][0]
    cliente.post(f'/api/v1/conciliacion/movimientos/{m["id"]}/conciliar',
                 headers=finanzas, json={'negocio_id': venta['id']})

    for ruta, cuerpo in (('reversado', {'motivo': 'Se devolvio'}),
                         ('descartar', {'motivo': 'No es de cliente'}),
                         ('duplicado', {'duplicado_de_id': m['id'] + 1})):
        r = cliente.post(f'/api/v1/conciliacion/movimientos/{m["id"]}/{ruta}',
                         headers=finanzas, json=cuerpo)
        assert r.status_code == 409, f'{ruta}: {r.status_code} {r.text}'
        assert r.json()['codigo'] == 'ya_conciliado'


# ------------------------------------------------------------------ resumen

def test_el_resumen_dice_cuanto_falta_por_cuadrar(cliente, vendedora, finanzas, db):
    cab, _ = vendedora
    venta = vender(cliente, cab, db, nombre='Resumen Delcierre Cliente', valor=900000)
    importar(cliente, finanzas, [mov('2026-03-10', 900000, fila=1),
                                 mov('2026-03-11', 5.0, fila=2, descripcion='INTERESES'),
                                 mov('2026-03-12', 120000, fila=3)])
    items = cliente.get('/api/v1/conciliacion/movimientos', headers=finanzas).json()['items']
    por_valor = {float(i['valor']): i['id'] for i in items}

    cliente.post(f'/api/v1/conciliacion/movimientos/{por_valor[900000.0]}/conciliar',
                 headers=finanzas, json={'negocio_id': venta['id']})
    cliente.post(f'/api/v1/conciliacion/movimientos/{por_valor[5.0]}/descartar',
                 headers=finanzas, json={'motivo': 'Intereses del banco'})

    r = cliente.get('/api/v1/conciliacion/resumen', headers=finanzas).json()
    assert r['conciliado'] == {'cuantos': 1, 'total': 900000.0}
    assert r['descartado'] == {'cuantos': 1, 'total': 5.0}
    assert r['sin_conciliar'] == {'cuantos': 1, 'total': 120000.0}


# -------------------------------------------------------------- permisos

def test_operaciones_no_cuadra_el_banco(cliente, usuario):
    """Operaciones no ve la contabilidad (respuesta del 29/09)."""
    cab = entrar(cliente, usuario('operaciones'))
    assert cliente.get('/api/v1/conciliacion/movimientos', headers=cab).status_code == 403
    assert cliente.get('/api/v1/conciliacion/resumen', headers=cab).status_code == 403
    assert cliente.post('/api/v1/conciliacion/cruzar', headers=cab,
                        json={}).status_code == 403
