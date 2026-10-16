"""La misma venta anotada dos veces, y cómo se saca de la cartera (RF-040, RN-01).

Contado sobre producción: **16 ventas repetidas, $18.006.000 de más**, y 13 de
ellas son el mismo negocio anotado en `PAGOS` y en `PAGOS2026`. No fue un
descuido de quien cargó: la idempotencia de la carga es por `(archivo, hoja,
fila)`, así que el mismo hecho en dos hojas son dos filas y la llave no podía
verlo.

Y el problema no era solo que estuviera repetido, era que **no había forma de
corregirlo**: sobre una venta existían cotizar, ganar y consultar, y ninguna la
quitaba de la cartera. O sea que el saldo de 16 clientes estaba mal y el sistema
no tenía con qué arreglarlo. La cartera es el número con el que se decide a
quién se le cobra: la administradora lo dijo el 29/09 —«si las cargo mal, el
sistema le va a cobrar a gente que ya pagó»—.

Lo que estas pruebas fijan es que anular **no pierda plata**. En esas 16 los
pagos están repartidos entre las dos copias —$17,6 millones en una y $5,4 en la
otra—, así que anular a secas haría desaparecer dinero que sí entró y el
«cobrado» del mes quedaría mal sin que nadie se entere.
"""

import pytest
from sqlalchemy import select, text

from app.models.esquema import Negocios, Paises, Servicios
from tests.conftest import entrar


@pytest.fixture
def comercial(cliente, usuario):
    p = usuario('comercial')
    return entrar(cliente, p), p


@pytest.fixture
def finanzas(cliente, usuario):
    return entrar(cliente, usuario('finanzas'))


def _venta(cliente, cab, db, nombre: str, *, cliente_id: int | None = None) -> dict:
    """Una venta por el camino normal: cliente → persona → lead → ganar."""
    if cliente_id is None:
        cliente_id = cliente.post('/api/v1/clientes', headers=cab,
                                  json={'nombre': nombre}).json()['id']
        cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'cliente_id': cliente_id, 'nombre': nombre})
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    servicio = db.scalar(select(Servicios.id).where(Servicios.codigo == 'adelantos'))
    lead = cliente.post('/api/v1/oportunidades', headers=cab, json={
        'cliente_id': cliente_id, 'servicio_id': servicio, 'pais_id': pais,
        'proxima_accion': 'Enviar cotización'}).json()
    r = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json={})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def repetida(cliente, comercial, db):
    """Las dos copias de la misma venta, como las dejó la carga.

    Se les pone el origen a mano porque es lo que hay en producción: la misma
    venta con `origen_hoja` PAGOS en una fila y PAGOS2026 en la otra. Es el dato
    que permite entender de dónde salió el doble sin tener que abrir los Excel.
    """
    cab, _ = comercial
    una = _venta(cliente, cab, db, 'Yolanda Restrepo Gaviria')
    otra = _venta(cliente, cab, db, 'Yolanda Restrepo Gaviria',
                  cliente_id=una['cliente_id'])
    assert una['valor_pactado'] == otra['valor_pactado'] == 700000
    assert una['fecha_venta'] == otra['fecha_venta']

    for negocio_id, hoja, fila in ((una['id'], 'PAGOS', 118), (otra['id'], 'PAGOS2026', 42)):
        db.execute(text('update negocios set origen_archivo = :a, origen_hoja = :h, '
                        'origen_fila = :f where id = :n'),
                   {'a': 'PAGOS_VISANOW.xlsx', 'h': hoja, 'f': fila, 'n': negocio_id})
    db.commit()
    return una, otra


# --------------------------------------------------------------- encontrarlas

def test_la_lista_encuentra_la_misma_venta_anotada_dos_veces(cliente, finanzas, repetida):
    """Mismo cliente, mismo servicio, misma fecha y mismo valor.

    No es una heurística floja: que coincidan las cuatro cosas y sean negocios
    distintos es, en la práctica, imposible por casualidad.
    """
    una, otra = repetida

    r = cliente.get('/api/v1/ventas/repetidas', headers=finanzas)
    assert r.status_code == 200, r.text
    grupo = next(g for g in r.json() if g['cliente'] == 'Yolanda Restrepo Gaviria')

    assert {c['negocio_id'] for c in grupo['copias']} == {una['id'], otra['id']}
    assert grupo['valor_pactado'] == 700000
    # De qué hoja salió cada una: sin esto no se puede decidir cuál se queda.
    assert {c['origen'] for c in grupo['copias']} == {'PAGOS', 'PAGOS2026'}


def test_la_lista_se_pide_por_su_direccion_y_no_la_lee_como_un_id(cliente, finanzas):
    """La trampa del orden de las rutas, que no se ve de otra forma.

    `/ventas/{negocio_id}` estaba declarada antes y FastAPI resuelve por orden:
    la palabra «repetidas» entraba como si fuera un id y la respuesta era un 422
    por un entero que no es un entero. La ruta existía y no se podía llamar.
    """
    r = cliente.get('/api/v1/ventas/repetidas', headers=finanzas)
    assert r.status_code == 200, (
        'la ruta fija quedó detrás de la variable: «repetidas» se está leyendo '
        'como un id de negocio')
    assert isinstance(r.json(), list)


def test_dos_ventas_parecidas_pero_de_distinto_dia_no_son_la_misma(cliente, comercial,
                                                                   finanzas, db):
    """Un cliente que compra el mismo servicio dos veces es un cliente que
    vuelve, no un error. Marcarlo repetido sería inventarle un problema."""
    cab, _ = comercial
    una = _venta(cliente, cab, db, 'Gilberto Arango Mesa')
    otra = _venta(cliente, cab, db, 'Gilberto Arango Mesa', cliente_id=una['cliente_id'])
    db.execute(text("update negocios set fecha_venta = fecha_venta - interval '40 days' "
                    'where id = :n'), {'n': otra['id']})
    db.commit()

    nombres = [g['cliente'] for g in cliente.get('/api/v1/ventas/repetidas',
                                                 headers=finanzas).json()]
    assert 'Gilberto Arango Mesa' not in nombres


def test_la_lista_de_repetidas_no_se_la_dan_a_cualquiera(cliente, usuario, repetida):
    """Lo que enseña son montos y saldos, que es «lo de la contabilidad».
    Operaciones ve trámites y no plata: por eso exige `pagos.ver`."""
    r = cliente.get('/api/v1/ventas/repetidas',
                    headers=entrar(cliente, usuario('operaciones')))
    assert r.status_code == 403


# ------------------------------------------------------------------- anularlas

def test_no_se_anula_una_venta_que_todavia_tiene_pagos(cliente, finanzas, repetida):
    """El corazón del asunto. En las 16 de producción los pagos están repartidos
    entre las dos copias, así que anular a secas borra plata que sí entró."""
    una, _ = repetida
    cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': una['id'], 'monto_bruto': 300000, 'referencia': 'abono real'})

    r = cliente.post(f'/api/v1/ventas/{una["id"]}/anular', headers=finanzas,
                     json={'motivo': 'Repetida: la misma venta está en PAGOS2026'})
    assert r.status_code == 409, r.text
    assert r.json()['codigo'] == 'venta_con_pagos'
    # Y la venta sigue en la cartera: no se quedó a medias.
    assert db_saldo(cliente, finanzas, una['id']) == 400000


def db_saldo(cliente, cab, negocio_id) -> float:
    return cliente.get(f'/api/v1/ventas/{negocio_id}/estado-financiero',
                       headers=cab).json()['saldo']


def test_resuelto_el_pago_la_venta_se_anula_y_sale_de_la_cartera(cliente, finanzas,
                                                                 repetida, db):
    """El camino completo, que es el que va a recorrer la administradora.

    El pago repetido se marca duplicado —no se borra, que es plata— y entonces
    sí se puede anular la copia. Lo que tiene que pasar al final es que la
    cartera deje de contarla: el saldo de esa venta desaparece de la vista, y
    con ella de todo lo que cuelga, porque el saldo nunca sale de una columna.
    """
    una, otra = repetida
    pago = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': otra['id'], 'monto_bruto': 700000,
        'referencia': 'el mismo abono, anotado en las dos hojas'}).json()

    r = cliente.post(f'/api/v1/pagos/{pago["id"]}/estado', headers=finanzas, json={
        'estado': 'duplicado',
        'observacion': 'Mismo abono anotado en el libro de ventas y en la caja'})
    assert r.status_code == 200, r.text
    assert db_saldo(cliente, finanzas, otra['id']) == 700000, (
        'marcar el pago duplicado le devuelve el saldo entero a la copia')

    # Se mide aquí, con el pago ya resuelto: lo que falta por comprobar es que
    # anular baje la cartera, y no el efecto de haber quitado el pago.
    antes = cliente.get('/api/v1/cartera/resumen', headers=finanzas).json()

    r = cliente.post(f'/api/v1/ventas/{otra["id"]}/anular', headers=finanzas,
                     json={'motivo': 'Repetida: la misma venta ya está cargada desde PAGOS'})
    assert r.status_code == 200, r.text

    # Ya no está en la cartera: la vista no la cuenta.
    fila = db.execute(text('select 1 from v_estado_financiero where negocio_id = :n'),
                      {'n': otra['id']}).first()
    assert fila is None, 'la venta anulada sigue en la cartera'
    assert db.execute(text('select 1 from v_cartera where negocio_id = :n'),
                      {'n': otra['id']}).first() is None, (
        'v_cartera cuelga de la otra vista y tiene que heredar el filtro')

    # Y la copia que se queda sí sigue, con su saldo intacto.
    assert db_saldo(cliente, finanzas, una['id']) == 700000

    despues = cliente.get('/api/v1/cartera/resumen', headers=finanzas).json()
    assert despues['cartera'] == antes['cartera'] - 700000, (
        'anular tiene que bajar la cartera en el valor de la venta repetida')
    assert despues['vendido'] == antes['vendido'] - 700000, (
        'y el vendido también: la venta repetida no fue una venta')

    # Y deja de aparecer en la lista de repetidas: el caso quedó resuelto.
    nombres = [g['cliente'] for g in cliente.get('/api/v1/ventas/repetidas',
                                                 headers=finanzas).json()]
    assert 'Yolanda Restrepo Gaviria' not in nombres


def test_la_venta_anulada_no_se_borra_y_queda_con_quien_y_por_que(cliente, finanzas,
                                                                  usuario, repetida, db):
    """Una venta que desaparece de la base sin rastro es peor que una repetida:
    nadie puede responder después por qué los totales de octubre cambiaron."""
    _, otra = repetida
    motivo = 'Repetida: la misma venta ya está cargada desde PAGOS'

    r = cliente.post(f'/api/v1/ventas/{otra["id"]}/anular', headers=finanzas,
                     json={'motivo': motivo})
    assert r.status_code == 200, r.text

    n = db.get(Negocios, otra['id'])
    db.refresh(n)
    assert n is not None, 'la fila se borró'
    assert n.anulada_en is not None and n.anulada_por is not None
    assert n.motivo_anulacion == motivo
    assert float(n.valor_pactado) == 700000, 'el valor original se conserva'

    auditoria = db.execute(text("""select count(*) from auditoria
                                    where entidad = 'negocios' and entidad_id = :n
                                      and operacion = 'update'"""),
                           {'n': otra['id']}).scalar()
    assert auditoria >= 1, 'anular una venta tiene que quedar en la auditoría'


def test_anular_sin_motivo_no_se_permite(cliente, finanzas, repetida):
    """El motivo es lo que explica el cambio en los totales. Sin él, el mes que
    viene nadie sabe por qué la cartera bajó $18 millones."""
    _, otra = repetida
    r = cliente.post(f'/api/v1/ventas/{otra["id"]}/anular', headers=finanzas,
                     json={'motivo': '   '})
    assert r.status_code == 422, r.text
    assert r.json()['codigo'] == 'falta_motivo'


def test_una_venta_anulada_no_se_anula_otra_vez(cliente, finanzas, repetida):
    _, otra = repetida
    datos = {'motivo': 'Repetida desde PAGOS'}
    assert cliente.post(f'/api/v1/ventas/{otra["id"]}/anular',
                        headers=finanzas, json=datos).status_code == 200
    r = cliente.post(f'/api/v1/ventas/{otra["id"]}/anular', headers=finanzas, json=datos)
    assert r.status_code == 409 and r.json()['codigo'] == 'ya_anulada'


def test_anular_una_venta_no_lo_hace_quien_solo_consulta(cliente, usuario, repetida):
    """`solo_lectura` ve la lista porque tiene `pagos.ver`, y no puede tocarla:
    corregir la cartera exige `negocios.editar`."""
    _, otra = repetida
    cab = entrar(cliente, usuario('solo_lectura'))
    assert cliente.get('/api/v1/ventas/repetidas', headers=cab).status_code == 200
    r = cliente.post(f'/api/v1/ventas/{otra["id"]}/anular', headers=cab,
                     json={'motivo': 'Repetida'})
    assert r.status_code == 403
