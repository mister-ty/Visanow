"""Rentabilidad: la resta completa (RF-054).

Estas pruebas estan escritas con numeros que no se parecen entre si a proposito.
Si el margen se calculara sobre el bruto en vez del neto, o si se olvidara
restar una de las tres salidas, el resultado seria otro numero y la prueba lo
dice. Con cifras redondas y parecidas —todo en cien mil— un error de esos pasa
inadvertido, que es exactamente como se cuela un margen inflado.

La venta de referencia, de punta a punta:

    pactado                              1.600.000
    recaudado (bruto)                    1.600.000
    - costo del medio de pago               30.000
    = INGRESO NETO                       1.570.000
    - comision (4 % de lo vendido)          64.000
    - gastos directos (venta 50 + tramite 13) 63.000
    - costo del servicio (180 + 25 x 2)    230.000
    = MARGEN                             1.213.000
"""
import datetime as dt

import pytest
from sqlalchemy import select

from app.models.esquema import (CategoriasGasto, Comisiones, CostosServicio, Paises,
                                Servicios)
from app.services import usuarios as servicio_usuarios
from tests.conftest import entrar

FECHA = '2026-09-22'
PACTADO = 1_600_000
COSTO_MEDIO = 30_000
NETO = PACTADO - COSTO_MEDIO            # 1.570.000
COMISION = 64_000                       # 4 % de lo vendido: la regla general del equipo
GASTO_VENTA = 50_000
GASTO_TRAMITE = 13_000
GASTOS = GASTO_VENTA + GASTO_TRAMITE    # 63.000
COSTO_FIJO = 180_000
COSTO_POR_PERSONA = 25_000
PERSONAS = 2
COSTOS = COSTO_FIJO + COSTO_POR_PERSONA * PERSONAS   # 230.000
MARGEN = NETO - COMISION - GASTOS - COSTOS           # 1.213.000

SERVICIO = 'renovacion_completa'        # honorario y fuera de la meta del 10 %
TASA = 'pago_visa'                      # recaudo de terceros: plata del consulado


# ------------------------------------------------------------------- montaje

@pytest.fixture
def finanzas(cliente, usuario):
    return entrar(cliente, usuario('finanzas'))


@pytest.fixture
def comercial(cliente, usuario):
    p = usuario('comercial')
    return entrar(cliente, p), p


def _id_servicio(db, codigo: str) -> int:
    return db.scalar(select(Servicios.id).where(Servicios.codigo == codigo))


def vender(cliente, cab, db, *, servicio: str, nombre: str, valor: float,
           fecha: str = FECHA, personas: int = 1, tramites: bool = True) -> dict:
    """Una venta por el camino normal: cliente, personas, lead y ganar."""
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': nombre}).json()
    for i in range(personas):
        r = cliente.post('/api/v1/solicitantes', headers=cab,
                         json={'cliente_id': c['id'], 'nombre': f'{nombre} Viajero{i + 1}'})
        assert r.status_code == 201, r.text
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    lead = cliente.post('/api/v1/oportunidades', headers=cab, json={
        'cliente_id': c['id'], 'servicio_id': _id_servicio(db, servicio), 'pais_id': pais,
        'proxima_accion': 'Cotizar'}).json()
    r = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json={
        'fecha_venta': fecha, 'valor_pactado': valor, 'abrir_tramites': tramites})
    assert r.status_code == 201, r.text
    return r.json()


def pagar(cliente, cab, negocio_id: int, bruto: float, costo_medio: float = 0,
          fecha: str = FECHA) -> None:
    r = cliente.post('/api/v1/pagos', headers=cab, json={
        'negocio_id': negocio_id, 'monto_bruto': bruto, 'costo_medio': costo_medio,
        'fecha': fecha})
    assert r.status_code == 201, r.text


def gastar(cliente, cab, db, monto: float, *, negocio_id=None, caso_id=None) -> None:
    categoria = db.scalar(select(CategoriasGasto.id).order_by(CategoriasGasto.id))
    cuerpo = {'categoria_id': categoria, 'concepto': 'Mensajeria del tramite',
              'monto': monto, 'fecha': FECHA}
    if negocio_id:
        cuerpo['negocio_id'] = negocio_id
    if caso_id:
        cuerpo['caso_id'] = caso_id
    r = cliente.post('/api/v1/gastos', headers=cab, json=cuerpo)
    assert r.status_code == 201, r.text


def costar(db, servicio_id: int, concepto: str, monto: float, *, modalidad: str = 'total',
           desde: str = '2026-01-01', hasta: str | None = None, activo: bool = True) -> None:
    db.add(CostosServicio(servicio_id=servicio_id, concepto=concepto, monto=monto,
                          modalidad=modalidad, vigente_desde=dt.date.fromisoformat(desde),
                          vigente_hasta=dt.date.fromisoformat(hasta) if hasta else None,
                          activo=activo))
    db.commit()


@pytest.fixture
def venta(cliente, comercial, finanzas, db):
    """La venta de referencia del encabezado, con sus cuatro salidas puestas."""
    cab, _ = comercial
    v = vender(cliente, cab, db, servicio=SERVICIO, nombre='Rentable Cuadrada Perez',
               valor=PACTADO, personas=PERSONAS)
    pagar(cliente, finanzas, v['id'], PACTADO, COSTO_MEDIO)
    gastar(cliente, finanzas, db, GASTO_VENTA, negocio_id=v['id'])
    gastar(cliente, finanzas, db, GASTO_TRAMITE, caso_id=v['casos'][0]['id'])

    servicio_id = _id_servicio(db, SERVICIO)
    costar(db, servicio_id, 'Tramitador', COSTO_FIJO)
    costar(db, servicio_id, 'Traduccion', COSTO_POR_PERSONA, modalidad='por_persona')
    return v


def _margen(cliente, cab, negocio_id: int) -> dict:
    r = cliente.get(f'/api/v1/rentabilidad/ventas/{negocio_id}', headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


# -------------------------------------------------------------- la resta entera

def test_el_margen_de_una_venta_es_el_ingreso_neto_menos_comisiones_gastos_y_costos(
        cliente, finanzas, venta, db):
    """La frase del requisito, cifra por cifra.

    Que las cuatro piezas viajen aparte no es un adorno: es lo que permite
    rehacer la resta a mano y reclamar la que no cuadre.
    """
    m = _margen(cliente, finanzas, venta['id'])

    # Ninguna pieza puede ser cero: una resta de ceros no prueba que se reste.
    assert m['ingreso_neto'] == NETO
    assert m['comisiones'] == COMISION
    assert m['gastos_directos'] == GASTOS
    assert m['costo_servicio'] == COSTOS
    assert m['margen'] == MARGEN, (
        f"margen {m['margen']}: {m['ingreso_neto']} - {m['comisiones']} - "
        f"{m['gastos_directos']} - {m['costo_servicio']} tiene que dar {MARGEN}")
    # Y el porcentaje sobre el ingreso que de verdad entro
    assert m['margen_pct'] == pytest.approx(MARGEN / NETO * 100, abs=0.1)


def test_el_ingreso_es_el_neto_recibido_y_no_el_bruto(cliente, finanzas, venta):
    """Lo que se lleva la pasarela no es ingreso de la agencia.

    El tablero financiero suma `monto_bruto` y lo llama recaudado. Para el
    margen eso sobra por el costo del medio de pago, y ese costo ya esta
    descontado dentro del ingreso neto: por eso aparece a la vista pero no se
    resta otra vez.
    """
    m = _margen(cliente, finanzas, venta['id'])
    assert m['ingreso_bruto'] == PACTADO
    assert m['costo_medio'] == COSTO_MEDIO
    assert m['ingreso_neto'] == PACTADO - COSTO_MEDIO
    assert m['margen'] == m['ingreso_neto'] - m['comisiones'] - m['gastos_directos'] \
        - m['costo_servicio']


def test_un_gasto_del_tramite_tambien_se_le_resta_a_la_venta(cliente, finanzas, venta, db):
    """La mensajeria se carga al tramite, no a la venta, y es plata de esa venta igual."""
    m = _margen(cliente, finanzas, venta['id'])
    assert m['gastos_directos'] == GASTO_VENTA + GASTO_TRAMITE, (
        'el gasto cargado al tramite tiene que bajar el margen de su venta')


def test_un_gasto_de_la_casa_no_se_le_carga_a_ninguna_venta(cliente, finanzas, venta, db):
    """La publicidad del mes no es de nadie: se mira aparte y no toca el margen."""
    antes = _margen(cliente, finanzas, venta['id'])['margen']
    gastar(cliente, finanzas, db, 900_000)      # sin venta ni tramite: gasto general
    assert _margen(cliente, finanzas, venta['id'])['margen'] == antes


# ------------------------------------------------------------------- los costos

def test_el_costo_que_cuenta_es_el_que_regia_el_dia_de_la_venta(cliente, finanzas, venta, db):
    """Subirle hoy el precio al tramitador no puede cambiar el margen del ano pasado.

    Se le agregan tres costos que NO le corresponden a esta venta: uno que se
    vencio antes, uno que empieza despues y uno suspendido. Si alguno se colara,
    el margen bajaria y aqui se veria.
    """
    servicio_id = _id_servicio(db, SERVICIO)
    costar(db, servicio_id, 'Tramitador del ano pasado', 90_000,
           desde='2025-01-01', hasta='2025-12-31')
    costar(db, servicio_id, 'Tramitador del proximo trimestre', 500_000, desde='2026-11-01')
    costar(db, servicio_id, 'Convenio suspendido', 70_000, activo=False)

    m = _margen(cliente, finanzas, venta['id'])
    assert m['costo_servicio'] == COSTOS, 'solo cuentan los costos vigentes y activos'
    assert m['margen'] == MARGEN


def test_el_costo_por_persona_se_multiplica_por_quienes_viajan(cliente, finanzas, venta, db):
    """El traductor cobra por cada solicitante; el tramitador, una vez por la familia."""
    m = _margen(cliente, finanzas, venta['id'])
    assert PERSONAS == 2, 'la venta de referencia tiene que ser grupal para que esto pruebe algo'
    assert m['costo_servicio'] == COSTO_FIJO + COSTO_POR_PERSONA * PERSONAS
    assert m['costo_servicio'] != COSTO_FIJO + COSTO_POR_PERSONA, (
        'si no se multiplicara por las personas, el costo saldria de menos')


# -------------------------------------------------------------- la tasa consular

def test_la_tasa_consular_no_es_ingreso_y_no_infla_el_margen(cliente, comercial, finanzas, db):
    """RN del negocio: el recaudo de terceros se cobra y se le entrega al consulado.

    Si entrara como ingreso, el margen saldria inflado justo en lo que no se
    gano. Entra en su propia columna y en el margen vale cero.
    """
    cab, _ = comercial
    tasa = vender(cliente, cab, db, servicio=TASA, nombre='Tasa Consular Cliente',
                  valor=400_000, tramites=False)
    pagar(cliente, finanzas, tasa['id'], 400_000)

    m = _margen(cliente, finanzas, tasa['id'])
    assert m['es_recaudo_de_terceros'] is True
    assert m['recaudo_terceros'] == 400_000, 'la plata recaudada se muestra, aparte'
    assert m['ingreso_bruto'] == 0 and m['ingreso_neto'] == 0
    assert m['margen'] == 0, 'la tasa consular no deja margen: no es plata de la agencia'
    assert m['margen_pct'] is None, 'sin ingreso no hay porcentaje que mostrar'


def test_el_total_del_periodo_no_mete_la_tasa_consular_en_el_ingreso(
        cliente, comercial, finanzas, venta, db):
    cab, _ = comercial
    tasa = vender(cliente, cab, db, servicio=TASA, nombre='Tasa Aparte Cliente',
                  valor=400_000, tramites=False)
    pagar(cliente, finanzas, tasa['id'], 400_000)

    r = cliente.get('/api/v1/rentabilidad', headers=finanzas,
                    params={'desde': FECHA, 'hasta': FECHA})
    assert r.status_code == 200, r.text
    total = r.json()['total']
    assert total['ingreso_neto'] == NETO, 'los 400.000 del consulado no son ingreso'
    assert total['recaudo_terceros'] == 400_000
    assert total['margen'] == MARGEN


# ------------------------------------------------- por servicio y por periodo

def test_el_corte_por_servicio_cuadra_con_el_total(cliente, finanzas, venta, db):
    r = cliente.get('/api/v1/rentabilidad', headers=finanzas,
                    params={'servicio_id': _id_servicio(db, SERVICIO)})
    assert r.status_code == 200, r.text
    datos = r.json()

    fila = next(f for f in datos['por_servicio'] if f['ventas'])
    assert fila['ingreso_neto'] == NETO and fila['comisiones'] == COMISION
    assert fila['gastos_directos'] == GASTOS and fila['costo_servicio'] == COSTOS
    assert fila['margen'] == MARGEN
    assert sum(f['margen'] for f in datos['por_servicio']) == datos['total']['margen']


def test_el_corte_por_periodo_agrupa_por_el_mes_de_la_venta(cliente, finanzas, venta, db):
    r = cliente.get('/api/v1/rentabilidad', headers=finanzas,
                    params={'servicio_id': _id_servicio(db, SERVICIO)})
    assert r.status_code == 200, r.text
    meses = r.json()['por_periodo']
    assert [m['etiqueta'] for m in meses] == ['2026-09'], meses
    assert meses[0]['margen'] == MARGEN


def test_el_periodo_filtra_por_la_fecha_de_la_venta(cliente, finanzas, venta, db):
    """La venta y todo lo que costo van juntas al mes en que se vendio."""
    dentro = cliente.get('/api/v1/rentabilidad', headers=finanzas,
                         params={'desde': '2026-09-01', 'hasta': '2026-09-30',
                                 'servicio_id': _id_servicio(db, SERVICIO)}).json()
    fuera = cliente.get('/api/v1/rentabilidad', headers=finanzas,
                        params={'desde': '2026-10-01', 'hasta': '2026-10-31',
                                'servicio_id': _id_servicio(db, SERVICIO)}).json()
    assert dentro['total']['ventas'] == 1 and dentro['total']['margen'] == MARGEN
    assert fuera['total']['ventas'] == 0 and fuera['total']['margen'] == 0
    assert fuera['total']['margen_pct'] is None


def test_el_rango_de_fechas_invertido_se_rechaza(cliente, finanzas):
    r = cliente.get('/api/v1/rentabilidad', headers=finanzas,
                    params={'desde': '2026-10-31', 'hasta': '2026-10-01'})
    assert r.status_code == 422


# ------------------------------------------------------------------ por negocio

def test_la_lista_de_ventas_pone_primero_la_que_esta_dando_perdida(
        cliente, comercial, finanzas, venta, db):
    """La pregunta del dueno es cual venta se come la plata, no cual va bien."""
    cab, _ = comercial
    mala = vender(cliente, cab, db, servicio=SERVICIO, nombre='Perdida Clara Gomez',
                  valor=300_000)
    pagar(cliente, finanzas, mala['id'], 300_000)
    gastar(cliente, finanzas, db, 400_000, negocio_id=mala['id'])

    r = cliente.get('/api/v1/rentabilidad/ventas', headers=finanzas,
                    params={'servicio_id': _id_servicio(db, SERVICIO), 'orden': 'peores'})
    assert r.status_code == 200, r.text
    filas = r.json()['items']
    assert [f['negocio_id'] for f in filas][0] == mala['id']
    assert filas[0]['margen'] < 0, 'esa venta costo mas de lo que entro'
    assert filas[-1]['negocio_id'] == venta['id'] and filas[-1]['margen'] == MARGEN

    mejores = cliente.get('/api/v1/rentabilidad/ventas', headers=finanzas,
                          params={'servicio_id': _id_servicio(db, SERVICIO),
                                  'orden': 'mejores'}).json()['items']
    assert mejores[0]['negocio_id'] == venta['id']


def test_la_venta_trae_lo_pactado_y_el_saldo_para_leer_el_ingreso_en_contexto(
        cliente, comercial, finanzas, db):
    """Una venta sin pagar tiene margen negativo, y eso es la verdad: no entro un peso.

    La comision todavia no se ha ganado —se gana cuando el cliente termina de
    pagar— pero ya se resta: es un costo que esta venta genero, y no mostrarlo
    hasta que se pague dejaria ver un margen que esta a punto de encogerse. El
    criterio es no mostrar nunca el margen mejor de lo que es.
    """
    cab, _ = comercial
    v = vender(cliente, cab, db, servicio=SERVICIO, nombre='Sin Pagar Todavia',
               valor=PACTADO, personas=PERSONAS)
    gastar(cliente, finanzas, db, GASTO_VENTA, negocio_id=v['id'])

    m = _margen(cliente, finanzas, v['id'])
    assert m['valor_pactado'] == PACTADO and m['saldo'] == PACTADO
    assert m['ingreso_neto'] == 0
    assert m['comisiones'] == COMISION
    assert m['margen'] == -(COMISION + GASTO_VENTA), 'lo unico que paso es que salio plata'


# ------------------------------------------------- quien ve esto y quien no

def test_operaciones_no_ve_la_rentabilidad(cliente, usuario, venta):
    """Es «lo de la contabilidad» (respuesta del 29/09): comisiones y margen.

    Operaciones se crea con alcance «todos» porque tiene que ver todos los
    tramites, asi que cuidar esto por alcance no alcanzaria: ver plata es un
    permiso.
    """
    cab = entrar(cliente, usuario('operaciones'))
    for ruta in ('/api/v1/rentabilidad', '/api/v1/rentabilidad/ventas',
                 f'/api/v1/rentabilidad/ventas/{venta["id"]}'):
        r = cliente.get(ruta, headers=cab)
        assert r.status_code == 403, f'{ruta}: {r.status_code} {r.text[:200]}'
        assert r.json()['codigo'] == 'sin_permiso'


def test_finanzas_si_ve_la_rentabilidad(cliente, finanzas, venta):
    assert cliente.get('/api/v1/rentabilidad', headers=finanzas).status_code == 200
    assert cliente.get('/api/v1/rentabilidad/ventas', headers=finanzas).status_code == 200


def test_quien_solo_ve_lo_suyo_no_suma_la_agencia_pero_si_ve_sus_ventas(
        cliente, usuario, comercial, finanzas, db, venta):
    """RNF-03 en el servicio: el alcance es control de acceso, no filtro de pantalla.

    La venta de referencia la cerro otra comercial. Quien tiene alcance limitado
    no puede sumar la agencia entera, y de las ventas solo ve las suyas.
    """
    admin = usuario('administradora')
    limitada = usuario('comercial')
    servicio_usuarios.editar(db, admin.u, limitada.u.id, alcance='asignados')
    db.commit()
    cab = entrar(cliente, limitada)

    for ruta in ('/api/v1/rentabilidad', '/api/v1/rentabilidad/ventas'):
        r = cliente.get(ruta, headers=cab)
        assert r.status_code == 403, f'{ruta}: {r.status_code} {r.text[:200]}'
        assert r.json()['codigo'] == 'sin_alcance'

    # La venta de otra: no la ve.
    ajena = cliente.get(f'/api/v1/rentabilidad/ventas/{venta["id"]}', headers=cab)
    assert ajena.status_code == 403 and ajena.json()['codigo'] == 'sin_alcance'

    # La suya: si.
    mia = vender(cliente, cab, db, servicio=SERVICIO, nombre='Venta Propia Suya',
                 valor=PACTADO, personas=PERSONAS)
    pagar(cliente, finanzas, mia['id'], PACTADO, COSTO_MEDIO)
    r = cliente.get(f'/api/v1/rentabilidad/ventas/{mia["id"]}', headers=cab)
    assert r.status_code == 200, r.text
    assert r.json()['ingreso_neto'] == NETO


def test_una_venta_que_no_existe_no_devuelve_un_margen_en_cero(cliente, finanzas, venta):
    """Un 404 y no un margen de ceros: inventar una cifra para algo que no existe
    es peor que decir que no existe.

    Ojo con esta prueba: un 404 tambien lo da una ruta que no existe, asi que
    comprobar solo el codigo la volveria un adorno que pasa sin que nada este
    implementado. Por eso primero se pide una venta de verdad —si la ruta no
    estuviera, ahi se cae— y despues se exige que el 404 sea el del dominio, con
    su mensaje, y no el generico de «ruta no encontrada».
    """
    assert cliente.get(f'/api/v1/rentabilidad/ventas/{venta["id"]}',
                       headers=finanzas).status_code == 200

    r = cliente.get('/api/v1/rentabilidad/ventas/99999999', headers=finanzas)
    assert r.status_code == 404
    assert r.json()['detalle'] == 'La venta no existe.'


# ------------------------------------------------------------- las comisiones

def test_la_comision_anulada_no_se_descuenta(cliente, finanzas, venta, db):
    """Una comision anulada es plata que no salio: no puede bajar el margen."""
    comision = db.scalars(select(Comisiones)
                          .where(Comisiones.negocio_id == venta['id'])).first()
    comision.estado = 'anulada'
    db.commit()

    m = _margen(cliente, finanzas, venta['id'])
    assert m['comisiones'] == 0
    assert m['margen'] == MARGEN + COMISION
