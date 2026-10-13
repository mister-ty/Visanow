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


# ----------------------------------- cartera por edades y filtros (RF-046)

@pytest.fixture
def deudor(cliente, comercial, finanzas, db):
    """Fábrica de ventas con saldo, con la edad de la mora puesta a la medida.

    Los datos se crean acá a propósito. En la base de hoy «cuotas_negocio» está
    vacía para las 477 ventas, y la cartera vencida sale de comparar lo pagado
    contra lo que ya era exigible según las cuotas: sin cuotas, toda la cartera
    reporta cero vencido y cero días de mora. Una prueba montada sobre esos
    datos pasaría sin haber comprobado nada.

    `mora` son los días que lleva sin pagarse el anticipo; `mora=None` deja las
    dos cuotas en el futuro, que es una venta al día con plata por vencer.
    """
    cab, _ = comercial

    def _crear(nombre: str, *, mora: int | None = None, vence_en: int = 30,
               servicio: str = 'adelantos', fecha_venta: str | None = None,
               vendedor_id: int | None = None) -> dict:
        c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': nombre}).json()
        cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'cliente_id': c['id'], 'nombre': nombre})
        pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
        serv = db.scalar(select(Servicios.id).where(Servicios.codigo == servicio))
        lead = cliente.post('/api/v1/oportunidades', headers=cab, json={
            'cliente_id': c['id'], 'servicio_id': serv, 'pais_id': pais,
            'proxima_accion': 'Enviar cotización'}).json()
        r = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json={})
        assert r.status_code == 201, r.text
        v = r.json()
        r = cliente.post(f'/api/v1/ventas/{v["id"]}/cuotas', headers=finanzas, json={})
        assert r.status_code == 201, r.text

        db.execute(text("""update cuotas_negocio
                              set fecha_pactada = current_date + :d
                            where negocio_id = :n and numero = 2"""),
                   {'d': vence_en, 'n': v['id']})
        db.execute(text("""update cuotas_negocio
                              set fecha_pactada = current_date + :d
                            where negocio_id = :n and numero = 1"""),
                   {'d': vence_en if mora is None else -mora, 'n': v['id']})
        if fecha_venta is not None:
            db.execute(text('update negocios set fecha_venta = :f where id = :n'),
                       {'f': fecha_venta, 'n': v['id']})
        if vendedor_id is not None:
            db.execute(text('update negocios set vendedor_id = :u where id = :n'),
                       {'u': vendedor_id, 'n': v['id']})
        db.commit()
        return v
    return _crear


def lista(cliente, cab, consulta: str = '') -> dict:
    r = cliente.get(f'/api/v1/cartera?tamano=200{consulta}', headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def edades(cliente, cab, consulta: str = '') -> dict:
    r = cliente.get(f'/api/v1/cartera/antiguedad?{consulta}', headers=cab)
    assert r.status_code == 200, r.text
    return {t['tramo']: t for t in r.json()}


def test_la_antiguedad_se_parte_en_los_tramos_de_la_contabilidad(cliente, finanzas, deudor):
    """RF-046. Un número de días suelto por fila no contesta la pregunta del
    cobro: «de lo que me deben, cuánto lleva entre 31 y 60 días». Los cortes son
    los de la contabilidad colombiana: 1-30, 31-60, 61-90 y más de 90.

    Los bordes van a propósito —30 y 31, 60 y 61, 90 y 91—: es donde se
    equivoca el corte, y una deuda que se cae al tramo de al lado cambia el
    informe y la decisión de a quién se llama hoy.
    """
    esperado = {30: '1_30', 31: '31_60', 60: '31_60', 61: '61_90', 90: '61_90', 91: 'mas_90'}
    ids = {dias: deudor(f'Deudor de {dias} días', mora=dias)['id'] for dias in esperado}

    filas = {f['negocio_id']: f for f in lista(cliente, finanzas)['items']}
    for dias, tramo in esperado.items():
        fila = filas[ids[dias]]
        assert fila['dias_vencido'] == dias
        assert fila['tramo'] == tramo, f'{dias} días de mora no cayó en «{tramo}»'


def test_el_corte_por_edades_dice_cuanto_hay_en_cada_tramo(cliente, finanzas, deudor):
    """Lo que de verdad se mira al cobrar: cuánta plata hay en cada edad.

    Sin el agregado hay que contar la tabla a mano, y por eso hoy nadie sabe
    cuánto de la cartera ya está en el tramo que la contabilidad da por perdido.
    """
    for dias in (10, 20, 45, 100):
        deudor(f'Deudor de {dias} días', mora=dias)
    deudor('Cliente al día', mora=None)

    tramos = edades(cliente, finanzas)
    assert list(tramos) == ['al_dia', '1_30', '31_60', '61_90', 'mas_90'], (
        'los tramos salen siempre y en orden de edad, aunque alguno esté vacío')

    assert tramos['1_30']['cuantas'] == 2, 'el de 10 y el de 20 días'
    assert tramos['1_30']['vencido'] == 280000, 'dos anticipos de 140.000 sin pagar'
    assert tramos['1_30']['saldo'] == 1400000
    assert tramos['31_60']['cuantas'] == 1 and tramos['31_60']['vencido'] == 140000
    assert tramos['61_90']['cuantas'] == 0, 'no hay nada en esa edad'
    assert tramos['mas_90']['cuantas'] == 1 and tramos['mas_90']['saldo'] == 700000
    assert tramos['al_dia']['cuantas'] == 1 and tramos['al_dia']['vencido'] == 0
    assert tramos['al_dia']['por_vencer'] == 700000

    assert sum(t['saldo'] for t in tramos.values()) == lista(cliente, finanzas)['suma_saldo'], (
        'el corte por edades y la lista tienen que hablar de la misma plata')


def test_la_cartera_se_filtra_por_tramo_de_antiguedad(cliente, finanzas, deudor):
    """«Muéstrame solo lo de 31 a 60 días»: es la lista de llamadas del día."""
    nuevo = deudor('Mora de 10 días', mora=10)['id']
    medio = deudor('Mora de 45 días', mora=45)['id']
    viejo = deudor('Mora de 100 días', mora=100)['id']

    r = lista(cliente, finanzas, '&tramo=31_60')
    ids = [f['negocio_id'] for f in r['items']]
    assert ids == [medio]
    assert nuevo not in ids and viejo not in ids
    assert r['suma_saldo'] == 700000

    assert cliente.get('/api/v1/cartera?tramo=cualquier_cosa',
                       headers=finanzas).status_code == 422, 'un tramo inventado no se traga'


def test_se_puede_filtrar_lo_que_vence_en_los_proximos_dias(cliente, finanzas, deudor, db):
    """«Por vencer» se veía pero no se podía filtrar, y es justo el filtro que
    sirve para llamar ANTES de que la plata se vuelva mora."""
    pronto = deudor('Le vence en 5 días', mora=None, vence_en=5)['id']
    lejos = deudor('Le vence en 60 días', mora=None, vence_en=60)['id']

    r = lista(cliente, finanzas, '&vence_en_dias=15')
    ids = [f['negocio_id'] for f in r['items']]
    assert pronto in ids and lejos not in ids
    assert r['suma_saldo'] == 700000

    fila = next(f for f in r['items'] if f['negocio_id'] == pronto)
    assert fila['tramo'] == 'al_dia', 'no debe nada vencido todavía'
    assert fila['por_vencer'] == 700000 and fila['vencido'] == 0
    en_cinco = db.execute(text('select current_date + 5')).scalar()
    assert fila['proximo_vencimiento'] == en_cinco.isoformat()


def test_la_cartera_se_filtra_por_servicio(cliente, finanzas, deudor):
    """La administradora no cobra igual un adelanto de cita que una renovación."""
    adelanto = deudor('Compró un adelanto', mora=10)
    renovacion = deudor('Compró una renovación', mora=10, servicio='renovacion')

    r = lista(cliente, finanzas, f'&servicio_id={renovacion["servicio_id"]}')
    ids = [f['negocio_id'] for f in r['items']]
    assert ids == [renovacion['id']]
    assert adelanto['id'] not in ids
    assert r['suma_saldo'] == 500000, 'el valor de la renovación, sin el adelanto'


def test_la_cartera_se_filtra_por_rango_de_fechas_de_venta(cliente, finanzas, deudor):
    """Para cerrar un periodo: qué quedó debiendo lo que se vendió en ese rango."""
    marzo = deudor('Venta de marzo', mora=10, fecha_venta='2026-03-15')['id']
    septiembre = deudor('Venta de septiembre', mora=10, fecha_venta='2026-09-20')['id']

    primer_semestre = [f['negocio_id'] for f in
                       lista(cliente, finanzas, '&desde=2026-01-01&hasta=2026-06-30')['items']]
    assert primer_semestre == [marzo]

    desde_agosto = [f['negocio_id'] for f in lista(cliente, finanzas, '&desde=2026-08-01')['items']]
    assert septiembre in desde_agosto and marzo not in desde_agosto


def test_el_filtro_de_antiguedad_minima_deja_fuera_la_mora_mas_nueva(cliente, finanzas, deudor):
    """`desde_dias` es el único filtro que toca la antigüedad y no tenía prueba.

    Y el corte por edades tiene que obedecerlo igual que la lista: si no, el
    informe de arriba y la tabla de abajo hablan de plata distinta.
    """
    nuevo = deudor('Mora de 5 días', mora=5)['id']
    viejo = deudor('Mora de 70 días', mora=70)['id']

    ids = [f['negocio_id'] for f in lista(cliente, finanzas, '&desde_dias=60')['items']]
    assert viejo in ids and nuevo not in ids

    tramos = edades(cliente, finanzas, 'desde_dias=60')
    assert tramos['61_90']['cuantas'] == 1
    assert tramos['1_30']['cuantas'] == 0, 'la mora de 5 días quedó fuera del filtro'


def test_la_cartera_se_filtra_por_vendedor_y_los_totales_tambien(cliente, finanzas, deudor,
                                                                 usuario):
    """Cada vendedora cobra lo suyo. Si los totales de arriba no obedecieran el
    filtro, la tarjeta diría un número y la suma de la tabla otro."""
    otra = usuario('comercial').u
    mia = deudor('Cliente de la casa', mora=10)['id']
    suya = deudor('Cliente de la otra vendedora', mora=10, vendedor_id=otra.id)['id']

    r = lista(cliente, finanzas, f'&vendedor_id={otra.id}')
    ids = [f['negocio_id'] for f in r['items']]
    assert ids == [suya]
    assert mia not in ids

    resumen = cliente.get(f'/api/v1/cartera/resumen?vendedor_id={otra.id}',
                          headers=finanzas).json()
    assert resumen['cartera'] == 700000, 'solo la cartera de esa vendedora'
    assert resumen['vencido'] == 140000
    assert resumen['cartera'] == r['suma_saldo'], 'la tarjeta y la tabla, la misma plata'


def test_la_cartera_se_filtra_por_cliente_y_el_corte_por_edades_tambien(cliente, finanzas,
                                                                        deudor):
    """Para la llamada: la deuda de ESTE cliente, con su edad, sin el resto."""
    uno = deudor('Mauricio Londoño', mora=100)
    otro = deudor('Gloria Sierra', mora=10)

    r = lista(cliente, finanzas, f'&cliente_id={uno["cliente_id"]}')
    ids = [f['negocio_id'] for f in r['items']]
    assert ids == [uno['id']]
    assert otro['id'] not in ids

    tramos = edades(cliente, finanzas, f'cliente_id={uno["cliente_id"]}')
    assert tramos['mas_90']['cuantas'] == 1
    assert tramos['1_30']['cuantas'] == 0, 'el otro cliente no entra en la cuenta'


def test_el_resumen_tambien_dice_cuanto_esta_por_vencer(cliente, finanzas, deudor):
    """Sin «por vencer» arriba, de la cartera solo se ve la mitad: lo que ya se
    pasó de fecha, y no lo que se va a pasar la semana entrante."""
    deudor('Debe con anticipo vencido', mora=20)
    r = cliente.get('/api/v1/cartera/resumen', headers=finanzas).json()
    assert r['vencido'] == 140000
    assert r['por_vencer'] == 560000, 'el saldo que todavía no es exigible'


def test_operaciones_tampoco_ve_el_corte_por_edades(cliente, usuario, deudor):
    """A operaciones se le oculta la contabilidad (respuesta del 29/09). El
    informe de cartera por edades es contabilidad."""
    cab = entrar(cliente, usuario('operaciones'))
    assert cliente.get('/api/v1/cartera/antiguedad', headers=cab).status_code == 403
# -------------------------------- buscar un pago por su referencia (RF-029)

def test_los_pagos_se_filtran_por_la_referencia_del_comprobante(cliente, finanzas, venta):
    """RF-029. La pregunta frecuente sobre un pago no es «cuáles hubo en
    octubre» sino «¿llegó este?», con el comprobante del cliente a la vista.

    Antes la pantalla pintaba la columna «Referencia» pero no se podía filtrar
    por ella: había que recorrer la lista con los ojos o adivinar la fecha.
    """
    for ref in ('BC-11112222', 'NEQUI-33334444'):
        assert cliente.post('/api/v1/pagos', headers=finanzas, json={
            'negocio_id': venta['id'], 'monto_bruto': 100000,
            'referencia': ref}).status_code == 201

    r = cliente.get('/api/v1/pagos?referencia=nequi', headers=finanzas).json()
    assert r['total'] == 1, f'el filtro no se aplicó, devolvió todo: {r}'
    assert r['items'][0]['referencia'] == 'NEQUI-33334444'

    # Por un pedazo del número, que es como la gente se acuerda de él
    r = cliente.get('/api/v1/pagos?referencia=1112', headers=finanzas).json()
    assert [p['referencia'] for p in r['items']] == ['BC-11112222']


def test_un_pedazo_que_no_existe_no_devuelve_la_lista_entera(cliente, finanzas, venta):
    """El daño silencioso de un filtro que no se aplica es devolver todo: quien
    busca cree que ese pago sí llegó porque ve pagos en la pantalla."""
    cliente.post('/api/v1/pagos', headers=finanzas,
                 json={'negocio_id': venta['id'], 'monto_bruto': 100000, 'referencia': 'BC-999'})
    r = cliente.get('/api/v1/pagos?referencia=ZZZ-000', headers=finanzas).json()
    assert r['total'] == 0 and r['items'] == []


def test_la_referencia_esta_indexada_para_no_recorrer_la_tabla(db):
    """Buscar por un pedazo de la referencia es un `ilike '%...%'`, y para esa
    pregunta un índice corriente no sirve de nada: PostgreSQL no lo puede usar y
    recorre la tabla fila por fila. Por eso va indexada por trigramas, la misma
    técnica con la que ya se buscan los nombres (migración 0004).

    Hoy son 583 pagos con referencia y el recorrido no se siente. El problema es
    que esa cuenta solo crece y la consulta se dispara con cada letra que
    alguien escribe en el buscador: es la clase de lentitud que no se nota el
    día que se escribe y después nadie sabe de dónde salió.
    """
    for tabla in ('pagos', 'movimientos_banco'):
        definicion = db.scalar(
            text('select indexdef from pg_indexes '
                 "where schemaname = 'public' and indexname = :i"),
            {'i': f'ix_{tabla}_referencia'})
        assert definicion, f'{tabla}.referencia quedó sin índice'
        assert 'gin_trgm_ops' in definicion, definicion
