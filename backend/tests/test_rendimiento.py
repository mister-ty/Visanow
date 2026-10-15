"""El techo de los tres segundos y la paginación que de verdad pagina (RNF-08).

El requisito dice que los listados responden en menos de tres segundos con
paginación. Hasta hoy nada lo vigilaba, y las mediciones del 10/10 contaban una
historia incómoda: se cumplía por el volumen, no porque algo lo sostuviera.
`/pagos?tamano=999999` devolvía las 583 filas de una sola vez, y la bandeja de
tareas traía todas las filas que coincidían, las ordenaba en memoria y recortaba
la lista con `filas[desde:desde + tamano]` — una respuesta que parecía paginada
sobre un barrido completo de la tabla, que nadie notaba porque había cero tareas.

Vale la pena decir qué vigila cada prueba de este archivo, porque son tres cosas
distintas y una de ellas es más débil de lo que parece:

**El tope, revisado sobre las rutas mismas.** No es una lista escrita a mano: se
le pregunta a FastAPI cuáles de sus rutas reciben un `tamano` y se exige que
todas tengan máximo. Una ruta paginada nueva queda vigilada el día que se
escribe, sin que nadie se acuerde de volver acá.

**El N+1, contando consultas.** Esta es la que tiene dientes. Se pide la misma
bandeja con cinco filas y con cincuenta, y el número de consultas que llegan a
Postgres tiene que ser *el mismo*: si alguien quita un `selectinload`, pasa a ser
una consulta por fila y la diferencia salta. Es la regresión de rendimiento que
de verdad ocurre en este tipo de código.

**El tiempo, que es la más débil.** Con cinco mil filas sembradas, Postgres
contesta estos listados en milisegundos, así que el techo de tres segundos no se
va a romper por un descuido pequeño: esta prueba no mide que el sistema sea
rápido, sino que no se haya vuelto catastróficamente lento —un join cartesiano,
un orden sin índice sobre la tabla entera, una consulta por fila a tamaño 200—.
Está acá porque el requisito nombra el número y porque una regresión de ese
tamaño es exactamente la que nadie ve venir; no porque tres segundos sea un
límite exigente.
"""
import contextlib
import datetime as dt
import time
from zoneinfo import ZoneInfo

import annotated_types
import pytest
from fastapi import FastAPI, Query
from fastapi.routing import APIRoute
from sqlalchemy import event, text

from app.api.paginacion import TAMANO_MAXIMO
from app.main import app
from tests.conftest import entrar

BOGOTA = ZoneInfo('America/Bogota')

#: Cuántas filas se siembran para que las mediciones signifiquen algo. Con la
#: base vacía cualquier consulta es instantánea y una prueba de rendimiento sin
#: volumen no prueba nada: pasa igual con el código bueno y con el malo.
VOLUMEN = 5000

#: El presupuesto del requisito.
TECHO_SEGUNDOS = 3.0


# --------------------------------------------------------------- herramientas

def _rutas_paginadas(aplicacion: FastAPI) -> list[tuple[str, int | None]]:
    """Las rutas que reciben un `tamano`, con su máximo o None si no tiene.

    Se le pregunta a la aplicación en vez de mantener una lista: una lista a
    mano se queda vieja en la primera ruta nueva, y el agujero que esto vigila
    nació justamente así.
    """
    encontradas = []
    for ruta in aplicacion.routes:
        if not isinstance(ruta, APIRoute):
            continue
        for parametro in ruta.dependant.query_params:
            if parametro.name != 'tamano':
                continue
            topes = [m.le for m in parametro.field_info.metadata
                     if isinstance(m, annotated_types.Le)]
            encontradas.append((ruta.path, topes[0] if topes else None))
    return encontradas


def _normal(sentencia: str) -> str:
    """La sentencia en una línea y en minúsculas, para poder buscar dentro.

    SQLAlchemy arma el SQL con saltos de línea —«...tareas.creado_en \\nFROM
    tareas \\nWHERE...»— así que buscar « from tareas» con el espacio adelante no
    encuentra nunca nada. Eso ya hizo que esta misma prueba midiera el vacío.
    """
    return ' '.join(sentencia.split()).lower()


@contextlib.contextmanager
def contando_consultas(sesion):
    """Las sentencias SQL que salen mientras dure el bloque."""
    sentencias: list[str] = []
    conexion = sesion.get_bind()

    def anotar(conn, cursor, sentencia, parametros, contexto, muchas):
        sentencias.append(sentencia)

    event.listen(conexion, 'before_cursor_execute', anotar)
    try:
        yield sentencias
    finally:
        event.remove(conexion, 'before_cursor_execute', anotar)


@pytest.fixture
def admin(cliente, usuario):
    return usuario('administradora')


@pytest.fixture
def con_volumen(db, admin):
    """Cinco mil clientes y cinco mil tareas, cada tarea con su propio cliente.

    Que el cliente sea distinto en cada tarea no es un detalle: si todas
    apuntaran al mismo, el mapa de identidad de SQLAlchemy lo cargaría una vez y
    un N+1 pasaría desapercibido. Con clientes distintos, perder el
    `selectinload` significa una consulta por fila, que es lo que se quiere ver.
    """
    db.execute(text("""
        insert into clientes (nombre, telefono, consentimiento)
        select 'Volumen ' || g, '30' || lpad(g::text, 8, '0'), true
          from generate_series(1, :n) g
    """), {'n': VOLUMEN})
    db.execute(text("""
        insert into tareas (titulo, responsable_id, prioridad, estado, vence_en, cliente_id)
        select 'Tarea de volumen ' || row_number() over (order by c.id),
               :responsable,
               (array['alta', 'media', 'baja'])[1 + (c.id % 3)],
               'pendiente',
               now() + ((c.id % 60) || ' days')::interval,
               c.id
          from clientes c
         where c.nombre like 'Volumen %'
    """), {'responsable': admin.u.id})
    db.flush()
    return VOLUMEN


# ------------------------------------------------- el tope, sobre las rutas

def test_toda_ruta_paginada_tiene_tope_de_tamano():
    """Un valor por omisión no es un techo: `?tamano=999999` lo ignora."""
    sin_tope = [ruta for ruta, tope in _rutas_paginadas(app) if tope is None]
    assert not sin_tope, (
        'Estas rutas reciben «tamano» sin máximo, así que se les puede pedir la '
        f'tabla completa en una petición: {sin_tope}. El tope compartido está en '
        'app/api/paginacion.py (Tamano).')


def test_el_tope_es_el_mismo_en_todas_las_rutas():
    """Dos rutas ya tenían cada una su propio `le=200` suelto; un número
    repetido es un número que algún día no se actualiza."""
    topes = {tope for _, tope in _rutas_paginadas(app)}
    assert topes == {TAMANO_MAXIMO}, (
        f'Hay más de un máximo distinto en las rutas paginadas: {sorted(topes)}')


def test_la_revision_del_tope_si_detecta_una_ruta_sin_maximo():
    """Que la prueba de arriba no pase por no estar mirando nada.

    Se arma una aplicación de mentiras con el descuido exacto que se quiere
    evitar —`tamano` sin `le`— y se comprueba que la revisión lo señala.
    """
    descuidada = FastAPI()

    @descuidada.get('/descuidada')
    def _listar(pagina: int = 1, tamano: int = 50):  # el agujero, a propósito
        return []

    @descuidada.get('/cuidada')
    def _listar_bien(tamano: int = Query(50, le=100)):
        return []

    hallado = dict(_rutas_paginadas(descuidada))
    assert hallado['/descuidada'] is None, 'la revisión no vio la ruta sin tope'
    assert hallado['/cuidada'] == 100, 'la revisión no leyó el tope que sí está'


@pytest.mark.parametrize('ruta', [r for r, _ in _rutas_paginadas(app)])
def test_pedir_mas_del_tope_es_un_error_y_no_una_pagina_gigante(cliente, admin, ruta):
    """Que el tope esté declarado y que la ruta lo aplique son dos cosas."""
    cab = entrar(cliente, admin)
    r = cliente.get(ruta, headers=cab, params={'tamano': 999999})
    assert r.status_code == 422, (
        f'{ruta} aceptó tamano=999999 y respondió {r.status_code}: la paginación '
        'se desarma desde la barra de direcciones.')

    al_tope = cliente.get(ruta, headers=cab, params={'tamano': TAMANO_MAXIMO})
    assert al_tope.status_code == 200, (
        f'{ruta} rechazó el máximo permitido ({TAMANO_MAXIMO}): {al_tope.text}')


# ------------------------------------------ la bandeja pagina en la base

def test_la_bandeja_de_tareas_pagina_en_postgres_y_no_en_memoria(
        cliente, admin, con_volumen, db):
    """Antes traía las cinco mil filas y recortaba la lista en Python."""
    cab = entrar(cliente, admin)
    with contando_consultas(db) as sentencias:
        r = cliente.get('/api/v1/tareas', headers=cab, params={'tamano': 50})
    assert r.status_code == 200, r.text
    datos = r.json()

    assert len(datos['items']) == 50
    assert datos['total'] == VOLUMEN, 'el total sigue siendo el de la tabla entera'

    de_tareas = [_normal(s) for s in sentencias
                 if 'from tareas' in _normal(s) and 'count(' not in _normal(s)]
    assert de_tareas, (
        'ninguna consulta tocó tareas, así que esta prueba no está midiendo nada: '
        f'lo que salió fue {[_normal(s)[:60] for s in sentencias]}')
    con_limite = [s for s in de_tareas if 'limit' in s]
    assert con_limite, (
        'la consulta de tareas salió sin LIMIT, así que Postgres devolvió la '
        f'tabla completa y el recorte volvió a hacerse en memoria: {de_tareas[-1][:400]}')


def test_la_segunda_pagina_de_la_bandeja_no_repite_la_primera(
        cliente, admin, con_volumen):
    """Un OFFSET mal calculado se ve acá y en ningún otro lado."""
    cab = entrar(cliente, admin)
    primera = cliente.get('/api/v1/tareas', headers=cab,
                          params={'tamano': 50, 'pagina': 1}).json()['items']
    segunda = cliente.get('/api/v1/tareas', headers=cab,
                          params={'tamano': 50, 'pagina': 2}).json()['items']

    ids_primera = {t['id'] for t in primera}
    ids_segunda = {t['id'] for t in segunda}
    assert len(ids_primera) == 50 and len(ids_segunda) == 50
    assert not (ids_primera & ids_segunda), 'la segunda página repite filas de la primera'


def test_el_orden_de_la_bandeja_es_prioridad_y_despues_vencimiento(
        cliente, admin, db):
    """El orden que se movió de Python a SQL, fijado por escrito.

    La prioridad es texto, así que ordenar por la columna daría «alta, baja,
    media» y lo urgente no quedaría arriba. El orden correcto es: prioridad,
    después lo que vence antes, y las sin fecha al final porque no tienen
    urgencia declarada.
    """
    hoy = dt.datetime.now(BOGOTA)
    puestas = [
        ('Alta mañana', 'alta', hoy + dt.timedelta(days=1)),
        ('Alta hoy', 'alta', hoy),
        ('Media ayer', 'media', hoy - dt.timedelta(days=1)),
        ('Baja sin fecha', 'baja', None),
        ('Alta sin fecha', 'alta', None),
    ]
    cid = db.execute(text(
        "insert into clientes (nombre, consentimiento) values ('Para el orden', true) "
        'returning id')).scalar()
    for titulo, prioridad, vence in puestas:
        db.execute(text("""
            insert into tareas (titulo, responsable_id, prioridad, estado, vence_en, cliente_id)
            values (:t, :r, :p, 'pendiente', :v, :c)
        """), {'t': titulo, 'r': admin.u.id, 'p': prioridad, 'v': vence, 'c': cid})
    db.flush()

    cab = entrar(cliente, admin)
    r = cliente.get('/api/v1/tareas', headers=cab, params={'tamano': TAMANO_MAXIMO})
    assert r.status_code == 200, r.text
    titulos = [t['titulo'] for t in r.json()['items']
               if t['titulo'] in {p[0] for p in puestas}]

    assert titulos == ['Alta hoy', 'Alta mañana', 'Alta sin fecha',
                       'Media ayer', 'Baja sin fecha'], titulos


# ------------------------------------------------- una consulta por fila, no

@pytest.mark.parametrize('ruta', ['/api/v1/tareas', '/api/v1/clientes'])
def test_un_listado_no_dispara_una_consulta_por_fila(
        cliente, admin, con_volumen, db, ruta):
    """La regresión de rendimiento que de verdad pasa en este código.

    Si alguien quita un `selectinload`, cada fila de la página se trae su
    responsable y su cliente con una consulta aparte. El tiempo total no lo
    delata —sigue siendo rápido con cinco mil filas— pero el número de consultas
    deja de ser constante, y eso sí se puede afirmar.
    """
    cab = entrar(cliente, admin)
    # Fuera de la medición: el ingreso y el primer golpe de caché.
    cliente.get(ruta, headers=cab, params={'tamano': 5})

    with contando_consultas(db) as pocas:
        cliente.get(ruta, headers=cab, params={'tamano': 5})
    with contando_consultas(db) as muchas:
        cliente.get(ruta, headers=cab, params={'tamano': 50})

    # Sin esto la prueba se cumple comparando cero contra cero el día que la
    # captura de sentencias deje de funcionar. Ya pasó: el filtro de la prueba
    # de arriba traía cero y esta afirmaba 0 == 0 sin que nada se notara.
    assert len(pocas) >= 2, (
        f'{ruta}: no se capturó el SQL de la petición ({len(pocas)} sentencias), '
        'así que la comparación de abajo no significa nada.')

    assert len(muchas) == len(pocas), (
        f'{ruta}: pedir diez veces más filas disparó '
        f'{len(muchas) - len(pocas)} consultas más ({len(pocas)} → {len(muchas)}). '
        'Eso es una consulta por fila: falta cargar las relaciones de una vez.')


# ------------------------------------------------------- los índices medidos

def test_la_vista_de_cartera_tiene_los_indices_que_la_sostienen(db):
    """Dos índices que parecen de adorno y no lo son (migración 0027).

    `v_estado_financiero` le suma a cada venta sus pagos y sus ajustes, una vez
    por venta. Sin índice por `negocio_id`, armar la pantalla de cartera
    recorría la tabla de pagos 501 veces: medido, 18,4 ms contra 1,1 ms. El
    número de hoy no molesta a nadie; lo que importa es que el costo crece con
    pagos *por* ventas. Si alguien los quita por «no se usan», esto se lo dice.
    """
    faltan = [f'{tabla}.{columna}' for tabla, columna in
              (('pagos', 'negocio_id'), ('ajustes_negocio', 'negocio_id'))
              if not db.execute(text("""
                  select 1 from pg_indexes
                   where schemaname = 'public' and tablename = :t
                     and indexdef like '%(' || :c || '%'"""),
                  {'t': tabla, 'c': columna}).first()]
    assert not faltan, (
        f'Sin índice por {faltan}, la vista de cartera vuelve a recorrer la '
        'tabla completa una vez por venta. Ver la migración 0027.')


# --------------------------------------------------------- el techo de 3 s

@pytest.mark.parametrize('ruta', [
    '/api/v1/clientes',
    '/api/v1/tareas',
    '/api/v1/casos',
    '/api/v1/pagos',
    '/api/v1/cartera',
    '/api/v1/alertas',
    '/api/v1/oportunidades',
    '/api/v1/gastos',
    '/api/v1/conciliacion/movimientos',
    '/api/v1/rentabilidad/ventas',
    '/api/v1/auditoria',
])
def test_un_listado_lleno_responde_bajo_el_techo_de_tres_segundos(
        cliente, admin, con_volumen, ruta):
    """El número que nombra el requisito, afirmado.

    Lo que esta prueba alcanza a ver está dicho en la cabecera del archivo:
    detecta una regresión catastrófica, no una lentitud fina. Se mide a tamaño
    máximo, que es el caso peor que la API permite.
    """
    cab = entrar(cliente, admin)
    arranque = time.perf_counter()
    r = cliente.get(ruta, headers=cab, params={'tamano': TAMANO_MAXIMO})
    tardo = time.perf_counter() - arranque

    assert r.status_code == 200, r.text
    assert tardo < TECHO_SEGUNDOS, (
        f'{ruta} tardó {tardo:.2f} s a tamaño {TAMANO_MAXIMO}, por encima del '
        f'techo de {TECHO_SEGUNDOS} s del RNF-08.')
