"""Alta de trámites, su procedencia y el tablero operativo (RF-020, RF-021, RF-022).

Van en un archivo aparte de `test_casos.py` —que vigila los estados, el
checklist y el historial— porque lo que se prueba aquí es otra pregunta: cómo
entra un trámite al sistema, de dónde viene lo que dice, y qué ve quien tiene
que repartir el trabajo del día.

Lo que cada prueba defiende, en el orden de los requisitos:

- La familia se da de alta UNA vez (RF-020). La venta se cierra para el grupo y
  el trámite se abre por persona, así que para cuatro personas el formulario se
  llenaba cuatro veces, y la cuarta salía distinta de la primera: el país bien y
  la modalidad en blanco.
- «Híbrido» existe de verdad (RF-021). Un trámite que nació a mano y después se
  amarró al SaaS es mixto; llamarlo «saas» borra que alguien lo abrió, lo
  cotizó y lo trabajó antes de que el SaaS supiera que existía.
- El tablero filtra por las siete dimensiones del requisito (RF-022), y
  «antigüedad» no es «tiempo sin movimiento»: un trámite de hace cinco meses que
  se movió ayer no es un trámite quieto, y antes el tablero solo sabía responder
  la segunda pregunta.
- Hay UNA definición de riesgo en el producto. Había dos —cinco días en la lista
  de trámites y quince en el tablero de indicadores—, de modo que la fila que la
  persona veía en rojo no estaba contada en el número que mira la administradora.
- El tablero operativo cuenta los trámites SIN VENTA. El sistema permite
  abrirlos (la operación y el dinero viven hoy en archivos distintos) y el
  tablero los dejaba fuera con un INNER JOIN a negocios: trámites reales que no
  existían para quien mira los números.
"""
import csv
import datetime as dt
import io
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models.esquema import Modalidades, Negocios, Paises, Sedes, Servicios, TiposVisa
from app.services.casos import DIAS_RIESGO_ALTO
from tests.conftest import entrar

CASOS = '/api/v1/casos'
OPERATIVO = '/api/v1/tableros/operativo'


@pytest.fixture
def operaciones(cliente, usuario):
    p = usuario('operaciones')
    return entrar(cliente, p), p


@pytest.fixture
def admin(cliente, usuario):
    return entrar(cliente, usuario('administradora'))


@pytest.fixture
def pais_usa(db):
    return db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))


@pytest.fixture
def catalogo(db, pais_usa):
    """Los cinco campos del alta salen de catálogos sembrados, no de ids inventados."""
    return {
        'tipo_visa_id': db.scalar(select(TiposVisa.id).where(TiposVisa.pais_id == pais_usa)
                                  .order_by(TiposVisa.id)),
        'modalidad_id': db.scalar(select(Modalidades.id).where(Modalidades.codigo == 'grupal')),
        'sede_id': db.scalar(select(Sedes.id).order_by(Sedes.id)),
    }


def una_persona(cliente, cab, nombre):
    """Un cliente con una persona que viaja, que es sobre quien se abre el trámite."""
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': nombre}).json()
    r = cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'cliente_id': c['id'], 'nombre': nombre})
    assert r.status_code == 201, r.text
    return c, r.json()


def crear_caso(cliente, cab, solicitante_id, pais_id, **extra):
    r = cliente.post(CASOS, headers=cab, json={
        'solicitante_id': solicitante_id, 'pais_id': pais_id,
        'proxima_accion': 'Pedir documentos al cliente', **extra})
    assert r.status_code == 201, r.text
    return r.json()


def listar(cliente, cab, **params):
    r = cliente.get(CASOS, headers=cab, params={'tamano': 200, **params})
    assert r.status_code == 200, r.text
    return r.json()['items']


def ids(items):
    return [c['id'] for c in items]


def indicador(cliente, cab, clave):
    r = cliente.get(OPERATIVO, headers=cab)
    assert r.status_code == 200, r.text
    return next(i for i in r.json()['indicadores'] if i['clave'] == clave)


def envejecer(db, caso_id, *, entrada_dias=None, quieto_dias=None):
    """Mueve en el tiempo lo que el reloj tardaría días en producir.

    Las dos fechas se tocan por separado a propósito: la entrada y el último
    movimiento son las dos preguntas que el tablero confundía en una.
    """
    if entrada_dias is not None:
        db.execute(text('update casos set creado_en = now() - make_interval(days => :d) '
                        'where id = :i'), {'d': entrada_dias, 'i': caso_id})
    if quieto_dias is not None:
        db.execute(text('update casos set ultima_actividad_en = now() - make_interval(days => :d) '
                        'where id = :i'), {'d': quieto_dias, 'i': caso_id})
    db.commit()


# ------------------------------------------------------- RF-020: el alta

def test_el_alta_abre_un_tramite_por_persona_con_los_cinco_campos(
        cliente, operaciones, admin, catalogo, pais_usa):
    """Una familia de cuatro se da de alta una vez y no cuatro.

    El requisito habla de «solicitantes» en plural y hasta hoy el alta aceptaba
    uno: para la familia Basante había que pasar cuatro veces por el mismo
    formulario, eligiendo cuatro veces el mismo país, la misma modalidad y la
    misma sede. Aquí se eligen una vez y valen para todos, que es además la
    única forma de que los cuatro trámites de una familia queden iguales.
    """
    cab, p = operaciones
    personas = [una_persona(cliente, admin, n)[1] for n in
                ('Hernán Basante Rojas', 'Luz Díaz Mora', 'Juan Basante Díaz', 'Ana Basante Díaz')]

    r = cliente.post(f'{CASOS}/lote', headers=cab, json={
        'solicitantes': [x['id'] for x in personas], 'pais_id': pais_usa,
        'responsable_id': p.u.id, 'proxima_accion': 'Pedir documentos al cliente', **catalogo})
    assert r.status_code == 201, r.text

    abiertos = r.json()
    assert len(abiertos) == 4
    assert {x['solicitante_id'] for x in abiertos} == {x['id'] for x in personas}
    for x in abiertos:
        assert x['pais_id'] == pais_usa and x['responsable_id'] == p.u.id
        assert x['tipo_visa_id'] == catalogo['tipo_visa_id']
        assert x['modalidad_id'] == catalogo['modalidad_id']
        assert x['sede_id'] == catalogo['sede_id']
        assert x['estado'] == 'registrado'


def test_el_alta_de_un_lote_no_abre_nada_si_una_persona_no_existe(
        cliente, operaciones, admin, pais_usa, db):
    """O entran los cuatro o no entra ninguno.

    Media familia dada de alta es peor que ninguna: nadie sabe cuáles quedaron,
    y el segundo intento duplica los que sí entraron.
    """
    cab, p = operaciones
    _, persona = una_persona(cliente, admin, 'Solo Uno Valido')
    antes = len(listar(cliente, cab))

    r = cliente.post(f'{CASOS}/lote', headers=cab, json={
        'solicitantes': [persona['id'], 999_999_999], 'pais_id': pais_usa,
        'responsable_id': p.u.id, 'proxima_accion': 'Pedir documentos'})
    assert r.status_code == 404, r.text
    assert len(listar(cliente, cab)) == antes, 'no puede quedar medio lote abierto'


def test_el_alta_pone_al_responsable_y_a_los_demas_de_una_vez(
        cliente, operaciones, usuario, admin, pais_usa):
    """«Responsables» en plural, sin romper que responda uno solo (RN-04).

    El responsable sigue siendo uno —un trámite con tres dueños no tiene
    ninguno—, y los demás entran como colaboradores (RF-026). Lo que no tenía
    sentido era que la única forma de sumarlos fuera abrir el trámite primero y
    acordarse después.
    """
    cab, p = operaciones
    otro = usuario('operaciones')
    _, persona = una_persona(cliente, admin, 'Persona Con Apoyo')

    caso = crear_caso(cliente, cab, persona['id'], pais_usa,
                      responsable_id=p.u.id, colaboradores=[otro.u.id])

    equipo = cliente.get(f'{CASOS}/{caso["id"]}/colaboradores', headers=cab).json()
    assert [c['usuario_id'] for c in equipo] == [otro.u.id]


def test_el_alta_de_una_persona_guarda_modalidad_y_sede(
        cliente, operaciones, admin, catalogo, pais_usa):
    """Cobertura de los dos campos del requisito que nadie probaba.

    La modalidad y la sede se podían mandar desde el primer día, pero ninguna
    prueba las mandaba: nada avisaba si un cambio dejaba de guardarlas.
    """
    cab, p = operaciones
    _, persona = una_persona(cliente, admin, 'Persona Con Modalidad')
    caso = crear_caso(cliente, cab, persona['id'], pais_usa, responsable_id=p.u.id, **catalogo)
    assert caso['modalidad_id'] == catalogo['modalidad_id']
    assert caso['sede_id'] == catalogo['sede_id']


# --------------------------------------------------- RF-021: la procedencia

def test_un_tramite_se_puede_marcar_hibrido_y_queda_en_el_historial(
        cliente, operaciones, admin, pais_usa):
    """«Marcar» es un verbo activo y no había con qué hacerlo.

    El valor «híbrido» estaba en la base y en el esquema desde el principio, y
    ningún servicio lo asignaba nunca: existía en el papel y no en el producto.
    """
    cab, p = operaciones
    _, persona = una_persona(cliente, admin, 'Persona Mixta Uno')
    caso = crear_caso(cliente, cab, persona['id'], pais_usa, responsable_id=p.u.id)
    assert caso['fuente'] == 'manual'

    r = cliente.post(f'{CASOS}/{caso["id"]}/fuente', headers=cab,
                     json={'fuente': 'hibrido', 'id_externo': 'HB-9001'})
    assert r.status_code == 200, r.text
    assert r.json()['fuente'] == 'hibrido' and r.json()['id_externo'] == 'HB-9001'

    campos = [h['campo'] for h in cliente.get(f'{CASOS}/{caso["id"]}/historial',
                                              headers=cab).json()]
    assert 'fuente' in campos, 'cambiar de dónde viene un trámite tiene que quedar dicho'


def test_marcar_del_saas_sin_numero_de_solicitud_no_pasa(cliente, operaciones, admin, pais_usa):
    """Un trámite «del SaaS» sin número de solicitud no se puede sincronizar con
    nada: el número es la llave con la que la importación lo reconoce (RF-032)."""
    cab, p = operaciones
    _, persona = una_persona(cliente, admin, 'Persona Sin Numero')
    caso = crear_caso(cliente, cab, persona['id'], pais_usa, responsable_id=p.u.id)

    r = cliente.post(f'{CASOS}/{caso["id"]}/fuente', headers=cab, json={'fuente': 'saas'})
    assert r.status_code == 422, r.text
    assert r.json()['codigo'] == 'falta_numero'


def test_el_numero_de_solicitud_de_otro_tramite_no_se_puede_robar(
        cliente, operaciones, admin, pais_usa):
    """Una solicitud del SaaS es de un trámite y de uno solo: si dos la tienen,
    la importación siguiente no sabe a cuál de los dos actualizar."""
    cab, p = operaciones
    _, uno = una_persona(cliente, admin, 'Persona Numero Propio')
    _, otro = una_persona(cliente, admin, 'Persona Numero Ajeno')
    crear_caso(cliente, cab, uno['id'], pais_usa, responsable_id=p.u.id, id_externo='SA-1234')
    segundo = crear_caso(cliente, cab, otro['id'], pais_usa, responsable_id=p.u.id)

    r = cliente.post(f'{CASOS}/{segundo["id"]}/fuente', headers=cab,
                     json={'fuente': 'saas', 'id_externo': 'SA-1234'})
    assert r.status_code == 409, r.text
    assert r.json()['codigo'] == 'solicitud_ya_vinculada'


def test_vincular_al_saas_lo_que_nacio_a_mano_lo_deja_hibrido(
        cliente, operaciones, admin, pais_usa):
    """El caso mixto que el requisito nombra, que es el más común de los tres.

    Alguien abre el trámite a mano, lo cotiza y lo empieza a trabajar; después
    aparece la solicitud en el SaaS y se amarran. Eso no es un trámite «del
    SaaS»: la mitad de lo que tiene lo escribió una persona aquí. Un trámite que
    sí nació en el SaaS, en cambio, sigue siendo del SaaS.
    """
    cab, p = operaciones
    _, manual = una_persona(cliente, admin, 'Persona Nacida A Mano')
    _, del_saas = una_persona(cliente, admin, 'Persona Nacida En Saas')
    a_mano = crear_caso(cliente, cab, manual['id'], pais_usa, responsable_id=p.u.id)
    importado = crear_caso(cliente, cab, del_saas['id'], pais_usa, responsable_id=p.u.id,
                           id_externo='SA-5000')
    assert importado['fuente'] == 'saas'

    r = cliente.post('/api/v1/saas/vincular', headers=cab,
                     json={'caso_id': a_mano['id'], 'numero_solicitud': 'SA-7788'})
    assert r.status_code == 200, r.text

    ficha = cliente.get(f'{CASOS}/{a_mano["id"]}', headers=cab).json()
    assert ficha['fuente'] == 'hibrido' and ficha['id_externo'] == 'SA-7788'
    campos = [h['campo'] for h in cliente.get(f'{CASOS}/{a_mano["id"]}/historial',
                                              headers=cab).json()]
    assert 'fuente' in campos, 'en auditoría no lo ve quien atiende al cliente'

    r = cliente.post('/api/v1/saas/vincular', headers=cab,
                     json={'caso_id': importado['id'], 'numero_solicitud': 'SA-5001'})
    assert r.status_code == 200, r.text
    assert cliente.get(f'{CASOS}/{importado["id"]}',
                       headers=cab).json()['fuente'] == 'saas'


def test_el_tablero_separa_los_tres_origenes(cliente, operaciones, admin, pais_usa):
    """Tres valores son tres, no dos: un híbrido no se puede ver como «SaaS»."""
    cab, p = operaciones
    _, persona = una_persona(cliente, admin, 'Persona Tres Origenes')
    caso = crear_caso(cliente, cab, persona['id'], pais_usa, responsable_id=p.u.id)
    cliente.post(f'{CASOS}/{caso["id"]}/fuente', headers=cab,
                 json={'fuente': 'hibrido', 'id_externo': 'HB-3003'})

    assert caso['id'] in ids(listar(cliente, cab, fuente='hibrido'))
    assert caso['id'] not in ids(listar(cliente, cab, fuente='saas'))
    assert caso['id'] not in ids(listar(cliente, cab, fuente='manual'))


# --------------------------------------------------- RF-022: el tablero

def test_el_tablero_filtra_por_servicio(cliente, operaciones, admin, db, pais_usa):
    """El servicio vendido no se podía ni filtrar ni ver en el tablero, y es con
    lo que se reparte el trabajo: adelantos no se atiende como una asesoría."""
    cab, p = operaciones
    grupo, persona = una_persona(cliente, admin, 'Persona Con Servicio')
    _, suelta = una_persona(cliente, admin, 'Persona Sin Venta')
    servicio_id = db.scalar(select(Servicios.id).where(Servicios.codigo == 'adelantos'))
    venta = Negocios(cliente_id=grupo['id'], servicio_id=servicio_id,
                     fecha_venta=dt.date(2026, 10, 1), valor_lista=Decimal('700000'),
                     valor_pactado=Decimal('700000'))
    db.add(venta)
    db.commit()

    con_venta = crear_caso(cliente, cab, persona['id'], pais_usa,
                           responsable_id=p.u.id, negocio_id=venta.id)
    sin_venta = crear_caso(cliente, cab, suelta['id'], pais_usa, responsable_id=p.u.id)

    del_servicio = listar(cliente, cab, servicio_id=servicio_id)
    assert con_venta['id'] in ids(del_servicio)
    assert sin_venta['id'] not in ids(del_servicio)
    assert next(c for c in del_servicio if c['id'] == con_venta['id'])['servicio']


def test_el_tablero_filtra_por_fecha_de_entrada_en_dias_de_bogota(
        cliente, operaciones, admin, db, pais_usa):
    """La fecha de entrada es el día de Bogotá, no el del reloj del servidor.

    El servidor corre en UTC y la agencia atiende de noche: un trámite abierto a
    las 8:30 p. m. del 9 entra en la base como el 10. Quien pregunta «qué entró
    el martes» pregunta por el martes de la oficina.
    """
    cab, p = operaciones
    _, tarde = una_persona(cliente, admin, 'Persona De Las Ocho')
    _, mediodia = una_persona(cliente, admin, 'Persona Del Mediodia')
    de_noche = crear_caso(cliente, cab, tarde['id'], pais_usa, responsable_id=p.u.id)
    de_dia = crear_caso(cliente, cab, mediodia['id'], pais_usa, responsable_id=p.u.id)

    # 01:30 UTC del 10 son las 8:30 p. m. del 9 en Bogotá; 18:00 UTC del 10 son
    # las 13:00 del 10.
    db.execute(text('update casos set creado_en = :t where id = :i'),
               [{'t': dt.datetime(2026, 3, 10, 1, 30, tzinfo=dt.timezone.utc), 'i': de_noche['id']},
                {'t': dt.datetime(2026, 3, 10, 18, 0, tzinfo=dt.timezone.utc), 'i': de_dia['id']}])
    db.commit()

    del_diez = ids(listar(cliente, cab, desde='2026-03-10', hasta='2026-03-10'))
    assert de_dia['id'] in del_diez
    assert de_noche['id'] not in del_diez, 'las 8:30 p. m. del 9 en Bogotá no son el 10'

    del_nueve = ids(listar(cliente, cab, desde='2026-03-09', hasta='2026-03-09'))
    assert de_noche['id'] in del_nueve and de_dia['id'] not in del_nueve


def test_la_antiguedad_no_es_el_tiempo_sin_movimiento(
        cliente, operaciones, admin, db, pais_usa):
    """Son dos preguntas distintas y el tablero solo sabía responder una.

    La columna «Quieto» cuenta desde el último movimiento. Un trámite que entró
    hace cien días y se movió hoy no está quieto, pero lleva cien días abierto:
    eso es lo que hay que mirar para saber si la agencia se está demorando.
    """
    cab, p = operaciones
    _, vieja = una_persona(cliente, admin, 'Persona De Hace Meses')
    _, nueva = una_persona(cliente, admin, 'Persona De Hoy')
    antiguo = crear_caso(cliente, cab, vieja['id'], pais_usa, responsable_id=p.u.id)
    reciente = crear_caso(cliente, cab, nueva['id'], pais_usa, responsable_id=p.u.id)
    envejecer(db, antiguo['id'], entrada_dias=100, quieto_dias=0)

    fila = next(c for c in listar(cliente, cab) if c['id'] == antiguo['id'])
    assert fila['dias_sin_movimiento'] == 0, 'se movió hoy'
    assert fila['antiguedad_dias'] >= 99, 'y lleva cien días abierto'

    viejos = ids(listar(cliente, cab, antiguedad_min=30))
    assert antiguo['id'] in viejos and reciente['id'] not in viejos

    por_antiguedad = listar(cliente, cab, orden='antiguedad')
    assert ids(por_antiguedad).index(antiguo['id']) < ids(por_antiguedad).index(reciente['id'])


def test_el_tablero_filtra_por_riesgo(cliente, operaciones, admin, db, pais_usa):
    """El riesgo se calculaba y se devolvía, y no se podía filtrar por él: para
    encontrar los trece en rojo había que mirar las doscientas filas."""
    cab, p = operaciones
    _, quieta = una_persona(cliente, admin, 'Persona Quieta')
    _, activa = una_persona(cliente, admin, 'Persona Activa')
    quieto = crear_caso(cliente, cab, quieta['id'], pais_usa, responsable_id=p.u.id)
    fresco = crear_caso(cliente, cab, activa['id'], pais_usa, responsable_id=p.u.id)
    envejecer(db, quieto['id'], quieto_dias=DIAS_RIESGO_ALTO + 2)

    altos = ids(listar(cliente, cab, riesgo='alto'))
    assert quieto['id'] in altos and fresco['id'] not in altos

    bajos = ids(listar(cliente, cab, riesgo='bajo'))
    assert fresco['id'] in bajos and quieto['id'] not in bajos


def test_el_tablero_filtra_por_responsable_y_por_pais(
        cliente, operaciones, usuario, admin, db, pais_usa):
    """Dos de las siete dimensiones que el API aceptaba y nadie ejercitaba."""
    cab, p = operaciones
    otro = usuario('operaciones')
    _, mia = una_persona(cliente, admin, 'Persona De Quien Prueba')
    _, ajena = una_persona(cliente, admin, 'Persona De Otro')
    pais_canada = db.scalar(select(Paises.id).where(Paises.iso2 == 'CA'))
    mio = crear_caso(cliente, cab, mia['id'], pais_usa, responsable_id=p.u.id)
    suyo = crear_caso(cliente, cab, ajena['id'], pais_canada, responsable_id=otro.u.id)

    del_responsable = ids(listar(cliente, cab, responsable_id=p.u.id))
    assert mio['id'] in del_responsable and suyo['id'] not in del_responsable

    de_canada = ids(listar(cliente, cab, pais_id=pais_canada))
    assert suyo['id'] in de_canada and mio['id'] not in de_canada


# ------------------------------- los dos hallazgos de fondo del tablero

def test_hay_una_sola_definicion_de_riesgo_en_el_producto(
        cliente, operaciones, admin, db, pais_usa):
    """La fila que la persona ve en rojo tiene que estar contada en el número
    que mira la administradora.

    Había dos definiciones: cinco días en la lista de trámites y quince en el
    tablero de indicadores. Con eso, un trámite quieto hace una semana salía en
    rojo en la pantalla de quien lo trabaja y no existía en «En riesgo» del
    tablero. Dos números que se contradicen hacen que no se crea ninguno.
    """
    cab, p = operaciones
    _, persona = una_persona(cliente, admin, 'Persona En Riesgo')
    caso = crear_caso(cliente, cab, persona['id'], pais_usa, responsable_id=p.u.id)
    envejecer(db, caso['id'], quieto_dias=DIAS_RIESGO_ALTO + 2)

    fila = next(c for c in listar(cliente, cab) if c['id'] == caso['id'])
    assert fila['riesgo'] == 'alto'

    en_riesgo = indicador(cliente, admin, 'riesgo')
    assert en_riesgo['valor'] >= 1, 'el tablero no cuenta lo que la lista pinta en rojo'
    assert f'{DIAS_RIESGO_ALTO}+' in en_riesgo['nombre'], \
        'el rótulo tiene que decir el mismo umbral que se usó para contar'


def test_el_tablero_operativo_cuenta_los_tramites_sin_venta(
        cliente, operaciones, admin, pais_usa):
    """Un trámite sin venta registrada es un trámite real.

    El sistema los permite a propósito: la operación y el dinero viven hoy en
    archivos distintos y al migrar hay trámites sin venta. El tablero los dejaba
    fuera con un INNER JOIN a negocios, así que la administradora leía menos
    trámites de los que su equipo estaba atendiendo.
    """
    cab, p = operaciones
    antes = indicador(cliente, admin, 'tramites')['valor']
    _, persona = una_persona(cliente, admin, 'Persona Sin Venta Registrada')
    caso = crear_caso(cliente, cab, persona['id'], pais_usa, responsable_id=p.u.id)
    assert caso['sin_venta'] is True

    assert indicador(cliente, admin, 'tramites')['valor'] == antes + 1
    assert indicador(cliente, admin, 'activos')['valor'] >= 1


# ------------------------------------------------- lo que se baja en archivo

def test_la_exportacion_de_tramites_lleva_el_origen_y_las_siete_dimensiones(
        cliente, operaciones, admin, db, pais_usa):
    """Lo que se ve en pantalla es lo que se baja (RF-075).

    El archivo de trámites no llevaba ni de dónde viene el trámite, ni su número
    de solicitud, ni el servicio, ni cuándo entró, ni cuánto lleva, ni el
    riesgo: justo las columnas con las que se reparte el trabajo fuera del
    sistema.
    """
    cab, p = operaciones
    _, persona = una_persona(cliente, admin, 'Persona Exportada')
    caso = crear_caso(cliente, cab, persona['id'], pais_usa,
                      responsable_id=p.u.id, id_externo='SA-8899')
    envejecer(db, caso['id'], entrada_dias=40, quieto_dias=DIAS_RIESGO_ALTO + 1)

    r = cliente.get('/api/v1/exportar/casos?formato=csv', headers=admin)
    assert r.status_code == 200, r.text
    filas = list(csv.reader(io.StringIO(r.content.decode('utf-8-sig')), delimiter=';'))
    encabezado = filas[0]
    for titulo in ('Origen', 'N.º de solicitud', 'Servicio', 'Entrada',
                   'Antigüedad (días)', 'Riesgo'):
        assert titulo in encabezado, encabezado

    fila = next(f for f in filas[1:] if f[0] == str(caso['id']))
    como = dict(zip(encabezado, fila, strict=True))
    assert como['Origen'] == 'saas' and como['N.º de solicitud'] == 'SA-8899'
    assert int(como['Antigüedad (días)']) >= 39
    assert como['Riesgo'] == 'alto'
    assert como['Entrada']
