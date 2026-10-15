"""Actividades 3.1 y 3.2 — el embudo comercial (RF-010, RF-011, RF-012, RF-015).

Lo que se prueba es lo que hoy no se puede responder con los archivos: de dónde
salió cada cliente que compró, cuáles se enfriaron y por qué se perdieron los
que se perdieron.
"""
import datetime as dt
import pathlib
import re
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from app.models.esquema import Canales, Paises, Servicios
from tests.conftest import entrar

OPORTUNIDADES = '/api/v1/oportunidades'
BOGOTA = ZoneInfo('America/Bogota')
EMBUDO_TSX = pathlib.Path(__file__).resolve().parents[2] / 'ui' / 'src' / 'paginas' / 'Embudo.tsx'


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


def test_se_guarda_y_se_puede_leer_quien_lo_recomendo(cliente, comercial, un_cliente):
    """El canal que más vende en los archivos es «recomendación», con 97 ventas.
    Sin saber quién recomendó, no hay a quién agradecerle ni a quién pedirle más.

    Se guardaba y no se devolvía nunca, que para quien usa el sistema es lo
    mismo que no guardarlo. Se pide por los tres caminos —al crear, en el
    detalle y en la lista— porque la pantalla usa los tres.
    """
    cab, _ = comercial
    otro = cliente.post('/api/v1/clientes', headers=cab,
                        json={'nombre': 'Felipe Ochoa Rivas'}).json()
    o = crear_lead(cliente, cab, un_cliente, referido_por_cliente_id=otro['id'])
    assert o['referido_por_cliente_id'] == otro['id']
    assert o['referido_por'] == otro['nombre'], 'el nombre, no solo el número'

    detalle = cliente.get(f'{OPORTUNIDADES}/{o["id"]}', headers=cab).json()
    assert detalle['referido_por'] == otro['nombre']

    en_lista = [x for x in cliente.get(OPORTUNIDADES, headers=cab).json()['items']
                if x['id'] == o['id']]
    assert [x['referido_por'] for x in en_lista] == [otro['nombre']]


def test_un_referido_o_una_campania_que_no_existen_se_rechazan_con_claridad(
        cliente, comercial, un_cliente):
    """Un id inventado chocaba contra la llave foránea y salía un 500: la
    pantalla dice «error del servidor» y quien digita no sabe qué corregir."""
    cab, _ = comercial
    for campo in ('referido_por_cliente_id', 'campania_id'):
        r = cliente.post(OPORTUNIDADES, headers=cab,
                         json={'cliente_id': un_cliente, 'proxima_accion': 'Llamar',
                               campo: 999_999})
        assert r.status_code == 404, f'{campo} respondió {r.status_code}: {r.text}'


# ------------------------------------------------- la fecha de llegada (RF-010)

def test_la_fecha_del_lead_se_captura_no_se_asigna(cliente, comercial, un_cliente, db):
    """Un lead transcrito de la hoja «pauta» o del formulario de Google llegó el
    día que llegó, no el día que alguien alcanzó a digitarlo.

    Con la fecha de digitación, «cuántos leads trajo la pauta de septiembre» se
    responde mal, y el lead de hace mes y medio entra al sistema como si
    estuviera recién nacido: no aparece en la lista de fríos, que es justo la
    que lo rescataría.
    """
    cab, _ = comercial
    llegada = dt.datetime.now(BOGOTA).date() - dt.timedelta(days=40)
    o = crear_lead(cliente, cab, un_cliente, fecha=llegada.isoformat())

    guardada = db.scalar(text('select creado_en from oportunidades where id = :i'), {'i': o['id']})
    assert guardada.astimezone(BOGOTA).date() == llegada, 'quedó con la fecha de digitación'
    assert o['dias_sin_contacto'] == 40

    frios = cliente.get(f'{OPORTUNIDADES}?frias_desde=30', headers=cab).json()
    assert [x['id'] for x in frios['items']] == [o['id']], 'un lead viejo nace frío'


def test_un_lead_no_puede_llegar_manana(cliente, comercial, un_cliente):
    """Si la fecha se puede escribir, se puede escribir mal. Una fecha futura
    esconde el lead de la lista de fríos para siempre."""
    cab, _ = comercial
    manana = dt.datetime.now(BOGOTA).date() + dt.timedelta(days=1)
    r = cliente.post(OPORTUNIDADES, headers=cab,
                     json={'cliente_id': un_cliente, 'proxima_accion': 'Llamar para calificar',
                           'fecha': manana.isoformat()})
    assert r.status_code == 422, r.text
    assert r.json()['codigo'] == 'fecha_futura'


def test_la_fecha_de_llegada_se_mide_en_bogota_y_no_en_el_reloj_del_servidor():
    """El servidor corre en UTC y Colombia está en UTC-5: desde las siete de la
    noche de Bogotá, para el servidor ya es mañana. La agencia atiende de noche.

    Se prueba con instantes EXPLÍCITOS a propósito: este equipo está en Bogotá,
    así que comparar contra `date.today()` pasaría sin comprobar nada.
    """
    from app.core.errores import Invalido
    from app.services.oportunidades import _hoy, _llegada

    # 11 de octubre 02:30 UTC == 10 de octubre 21:30 en Bogotá
    de_noche = dt.datetime(2026, 10, 11, 2, 30, tzinfo=dt.timezone.utc)
    assert _hoy(de_noche) == dt.date(2026, 10, 10), 'se adelantó un día'
    assert de_noche.date() == dt.date(2026, 10, 11), 'así es como estaría mal'
    assert _hoy(dt.datetime(2026, 10, 11, 4, 59, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 10)
    assert _hoy(dt.datetime(2026, 10, 11, 5, 0, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 11)

    # El instante que se guarda es el comienzo de ese día en Bogotá, para que la
    # fecha que se lee de vuelta sea la que se escribió.
    instante = _llegada(dt.date(2026, 10, 10), ahora=de_noche)
    assert instante.utcoffset() == dt.timedelta(hours=-5) and instante.hour == 0
    assert instante.astimezone(dt.timezone.utc) == dt.datetime(2026, 10, 10, 5, 0,
                                                               tzinfo=dt.timezone.utc)

    # Y a las nueve y media de la noche del 10 en Bogotá, el 11 todavía es mañana
    # aunque el reloj del servidor ya diga 11.
    with pytest.raises(Invalido):
        _llegada(dt.date(2026, 10, 11), ahora=de_noche)


def test_la_fuente_de_un_lead_es_el_canal_la_campania_y_el_referido(
        cliente, comercial, un_cliente, db):
    """DECISIÓN sobre «fuente» (RF-010).

    El texto del RF-010 pide «canal, campaña/influencer/referido, interés, país,
    asesor y fuente», pero el Anexo A de la especificación v1.0 —que es el que
    lista los campos mínimos de una oportunidad— no la menciona: «Fecha,
    servicio, país, asesor, canal/campaña, estado, valor estimado, próxima
    acción, motivo pérdida». Donde el Anexo A sí dice «fuente» es en el caso, y
    ahí significa otra cosa: si el trámite entró por el SaaS, a mano o mezclado
    (RF-021, `casos.fuente`).

    Se decidió NO abrir una segunda columna «fuente» en oportunidades. De dónde
    salió un lead se responde con tres datos que ya existen y que son de
    catálogo: el canal, la campaña y, cuando llegó recomendado, quién lo
    recomendó. Dos campos que contestan la misma pregunta terminan contestando
    distinto —es exactamente lo que pasa hoy entre las hojas PAGOS y REV PAGOS,
    donde la misma deuda difiere en 37 millones—, y un «fuente» de texto libre
    al lado de un canal de catálogo convierte el informe de publicidad en una
    lista de sinónimos.

    Lo que sí había que arreglar, y es lo que prueba esto, es que los tres se
    puedan registrar Y leer de vuelta.
    """
    from app.models.esquema import Campanias

    cab, _ = comercial
    recomendado = db.scalar(select(Canales.id).where(Canales.codigo == 'recomendado'))
    campania = Campanias(codigo='reel-septiembre', nombre='Reel de septiembre', tipo='influencer')
    db.add(campania)
    db.flush()
    padrino = cliente.post('/api/v1/clientes', headers=cab,
                           json={'nombre': 'Marta Zapata Londoño'}).json()

    o = crear_lead(cliente, cab, un_cliente, canal_id=recomendado, campania_id=campania.id,
                   referido_por_cliente_id=padrino['id'])
    assert (o['canal_id'], o['campania_id'], o['referido_por']) == \
        (recomendado, campania.id, padrino['nombre'])

    tablas = {r[0] for r in db.execute(text(
        "select table_name from information_schema.columns where column_name = 'fuente'"))}
    assert 'oportunidades' not in tablas, (
        'se abrió una segunda columna «fuente» en oportunidades: hay que leer la '
        'decisión de arriba antes, porque deja la pregunta «de dónde salió este '
        'cliente» con dos respuestas que se van a contradecir.')
    assert 'casos' in tablas, '«fuente» es del caso (RF-021), y ahí sigue'


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


def test_el_dinero_de_cada_paso_del_embudo_respeta_los_filtros(cliente, comercial, un_cliente, db):
    """El encabezado de cada columna del tablero dice cuánta plata hay en ese
    paso, y salía de una consulta que no aceptaba filtros.

    Al filtrar por canal o por asesor cambiaba el número de tarjetas y no el
    total en pesos: la misma pantalla mostraba dos respuestas distintas a la
    misma pregunta, y la que está en grande era la equivocada.
    """
    cab, _ = comercial
    instagram = db.scalar(select(Canales.id).where(Canales.codigo == 'instagram'))
    recomendado = db.scalar(select(Canales.id).where(Canales.codigo == 'recomendado'))
    crear_lead(cliente, cab, un_cliente, canal_id=instagram, valor_estimado=1000000)
    crear_lead(cliente, cab, un_cliente, canal_id=recomendado, valor_estimado=500000)

    def embudo(consulta: str = '') -> dict:
        r = cliente.get(f'{OPORTUNIDADES}/embudo{consulta}', headers=cab)
        assert r.status_code == 200, r.text
        return {p['codigo']: p for p in r.json()}

    todos, solo_insta = embudo(), embudo(f'?canal_id={instagram}')
    assert (todos['nuevo_lead']['cuantas'], todos['nuevo_lead']['valor_estimado']) == (2, 1500000)
    assert solo_insta['nuevo_lead']['cuantas'] == 1
    assert solo_insta['nuevo_lead']['valor_estimado'] == 1000000, 'el dinero ignoró el filtro'

    # Un paso que se queda vacío por el filtro sigue siendo un paso del embudo:
    # la columna tiene que dibujarse igual, o la tarjeta no se puede arrastrar
    # a un estado que no existe en pantalla.
    assert solo_insta.keys() == todos.keys()
    assert solo_insta['contactado']['cuantas'] == 0


def test_el_motivo_de_la_perdida_se_puede_leer(cliente, comercial, un_cliente):
    """RF-015 obliga a decir por qué se perdió, y el motivo solo servía para
    guardarse: la API devolvía un número sin nombre y la nota no salía por
    ningún lado. Un motivo que nadie puede leer no cambia ninguna decisión."""
    cab, _ = comercial
    o = crear_lead(cliente, cab, un_cliente)
    r = cliente.post(f'{OPORTUNIDADES}/{o["id"]}/estado', headers=cab, json={
        'codigo_destino': 'perdido', 'motivo_perdida': 'precio',
        'nota': 'Le pareció caro contra la competencia'})
    assert r.status_code == 200, r.text
    assert r.json()['motivo_perdida'] == 'precio'
    assert r.json()['motivo_perdida_nombre'], 'el nombre que se le muestra a la gente'
    assert r.json()['motivo_perdida_nota'] == 'Le pareció caro contra la competencia'

    cerradas = cliente.get(f'{OPORTUNIDADES}?incluir_cerradas=true', headers=cab).json()['items']
    perdida = next(x for x in cerradas if x['id'] == o['id'])
    assert perdida['motivo_perdida'] == 'precio'
    assert perdida['motivo_perdida_nota'] == 'Le pareció caro contra la competencia'

    # Y si el cliente vuelve, la oportunidad deja de estar perdida: un lead vivo
    # «perdido por precio» es el dato más viejo contradiciendo al más nuevo.
    r = cliente.post(f'{OPORTUNIDADES}/{o["id"]}/estado', headers=cab,
                     json={'codigo_destino': 'contactado', 'proxima_accion': 'Volvió: recotizar'})
    assert r.status_code == 200, r.text
    assert r.json()['motivo_perdida'] is None and r.json()['motivo_perdida_nota'] is None


def test_corregir_un_lead_devuelve_el_dato_nuevo_y_no_el_de_antes(cliente, comercial, un_cliente):
    """Transcribir una hoja a la carrera produce leads con la fecha equivocada,
    y eso se arregla corrigiendo el lead, no creándolo de nuevo. Lo que falta
    comprobar es que lo que se devuelve después de corregir sea lo corregido: si
    sale el dato de antes, quien corrigió cree que no se guardó y lo repite.

    Lo que esta prueba sostiene es la fecha, que es lo que estaba roto. Que el
    nombre del referido también se recalcule ya lo hacía SQLAlchemy sola al
    cambiar la llave foránea; queda aquí de guardia, no como mérito.
    """
    cab, _ = comercial
    uno = cliente.post('/api/v1/clientes', headers=cab,
                       json={'nombre': 'Ana Posada Vélez'}).json()
    dos = cliente.post('/api/v1/clientes', headers=cab,
                       json={'nombre': 'Sara Mesa Duque'}).json()
    o = crear_lead(cliente, cab, un_cliente, referido_por_cliente_id=uno['id'])

    llegada = dt.datetime.now(BOGOTA).date() - dt.timedelta(days=5)
    r = cliente.patch(f'{OPORTUNIDADES}/{o["id"]}', headers=cab,
                      json={'referido_por_cliente_id': dos['id'], 'fecha': llegada.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()['referido_por'] == dos['nombre']
    assert dt.datetime.fromisoformat(r.json()['creado_en']).astimezone(BOGOTA).date() == llegada


def test_la_lista_pagina_y_no_acepta_un_tamano_sin_tope(cliente, comercial, un_cliente):
    """Sin tope, la pantalla pide «todo» y el día que haya 5.000 oportunidades
    la consulta y el navegador se caen juntos. Y `pagina=0` daba un OFFSET
    negativo: error de PostgreSQL, 500 en la cara del usuario."""
    cab, _ = comercial
    ids = [crear_lead(cliente, cab, un_cliente)['id'] for _ in range(3)]

    primera = cliente.get(f'{OPORTUNIDADES}?tamano=2&pagina=1', headers=cab).json()
    segunda = cliente.get(f'{OPORTUNIDADES}?tamano=2&pagina=2', headers=cab).json()
    assert primera['total'] == 3 and len(primera['items']) == 2
    assert len(segunda['items']) == 1
    assert {x['id'] for x in primera['items'] + segunda['items']} == set(ids)

    for mala in ('pagina=0', 'tamano=0', 'tamano=100000'):
        r = cliente.get(f'{OPORTUNIDADES}?{mala}', headers=cab)
        assert r.status_code == 422, f'«{mala}» respondió {r.status_code}'


# ------------------------------------------------- la pantalla del embudo (RF-011)
#
# Estas tres leen el código de Embudo.tsx, igual que test_pantallas.py y por la
# misma razón: un filtro que el backend ofrece y la pantalla no expone no rompe
# nada, no da error en ninguna parte, y deja sin respuesta justo la pregunta de
# quien lo necesitaba. No se ve hasta que alguien la pide.

def _bloque(texto: str, inicio: str) -> str:
    """El objeto literal que arranca en `inicio`, hasta su llave de cierre."""
    assert inicio in texto, f'no se encontró «{inicio}» en Embudo.tsx'
    i = texto.index(inicio) + len(inicio)
    profundidad, j = 1, i
    while profundidad and j < len(texto):
        profundidad += {'{': 1, '}': -1}.get(texto[j], 0)
        j += 1
    return texto[i:j]


def _filtros_que_ofrece_el_backend() -> set[str]:
    from app.main import app

    parametros = app.openapi()['paths'][OPORTUNIDADES]['get']['parameters']
    return {p['name'] for p in parametros if p['in'] == 'query'} - {'pagina', 'tamano'}


def test_la_pantalla_del_embudo_alcanza_todos_los_filtros_del_backend():
    """Ocho filtros existían en la API y la pantalla llegaba a cuatro. El de
    campaña era el que faltaba para contestar «qué campaña trae clientes que
    compran», que es la frase que la propia pantalla tiene escrita.

    Se mira lo que la pantalla MANDA, no lo que nombra: los dos objetos con los
    que arma sus consultas. `filtros` es el que viaja a las dos (lista y
    embudo); `consulta` le agrega lo que solo recorta la lista.
    """
    texto = EMBUDO_TSX.read_text(encoding='utf-8')
    manda = _bloque(texto, 'const filtros = {') + _bloque(texto, 'const consulta = {')
    faltan = sorted(f for f in _filtros_que_ofrece_el_backend() if f not in manda)
    assert not faltan, (
        f'las consultas de Embudo.tsx no mandan estos filtros: {faltan}. '
        f'Existen en la API y desde la pantalla no se alcanzan.')


def test_la_lista_filtrable_del_embudo_existe_como_vista():
    """RF-011 pide «tablero Kanban y lista filtrable». El tablero recorta
    tarjetas por columna; la lista es la que deja ver de un tirón una
    oportunidad cerrada, su motivo de pérdida y de dónde salió."""
    texto = EMBUDO_TSX.read_text(encoding='utf-8')
    assert '<Table' in texto, 'el embudo solo pinta el tablero: la lista no existe como vista'
    assert 'motivo_perdida' in texto, 'sin el motivo a la vista, perder no explica nada'
    assert 'referido_por' in texto, 'quién lo recomendó no se ve en ninguna parte'
    # Capturar la fecha de llegada y no mostrarla en ningún lado deja la mitad
    # del trabajo hecha: de esa fecha sale el conteo de leads de cada pauta.
    assert 'creado_en' in texto, 'la fecha en que llegó el lead no se ve'


def test_la_pantalla_del_embudo_no_se_come_en_silencio_las_tarjetas_que_sobran():
    """Pedía 200 fijas y nunca miraba cuántas había: pasadas las 200, las
    tarjetas simplemente no se dibujaban y nadie se enteraba."""
    from app.api.v1.oportunidades import TOPE_TAMANO

    texto = EMBUDO_TSX.read_text(encoding='utf-8')
    pedidos = [int(n) for n in re.findall(r'(?:tamano:|TAMANO\s*=)\s*(\d+)', texto)]
    assert pedidos and max(pedidos) <= TOPE_TAMANO, (
        f'Embudo.tsx pide {pedidos} y la API no da más de {TOPE_TAMANO} por página.')
    assert 'Pagination' in texto, 'no hay con qué pasar a la página siguiente'
    assert 'total' in texto, 'la pantalla no mira cuántas hay: no puede avisar que faltan'


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

    regla = db.scalars(select(ComisionesReglas)
                       .where(ComisionesReglas.nombre.like('Angie%'))).first()
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

    # En una base recién sembrada todavía no existe la usuaria dueña de la regla,
    # así que entra inactiva a propósito (migración 0010): una regla sin dueña se
    # vuelve la regla general y le regala el escalón del 10 % a cualquiera.
    assert regla.vendedor_id is None and not regla.activo
    assert 'inactiva_porque' in d, 'la regla tiene que decir por qué está apagada'


def test_la_tasa_consular_no_entra_en_la_base_de_comision(db):
    """Hay 39 ventas de tasa consular por 40 millones en los archivos. Si
    entraran en la base, la comisión saldría inflada el 11,7 %."""
    from app.models.esquema import ComisionesReglas

    assert db.scalar(select(Servicios).where(Servicios.codigo == 'pago_visa')).tipo == \
        'recaudo_terceros'
    for regla in db.scalars(select(ComisionesReglas)):
        assert 'recaudo_terceros' in regla.definicion['excluye_de_la_base']
