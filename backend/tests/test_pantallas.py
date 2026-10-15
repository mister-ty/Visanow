"""Lo que hace que una pantalla sirva o se muera en silencio.

Estas pruebas leen el codigo del frontend. Es raro, y vale la pena: las tres
cosas que vigilan ya pasaron en este proyecto, ninguna rompe la compilacion, y
ninguna da error en ningun lado. Una pantalla que no esta en el menu, o cuyo
permiso no lo tiene nadie, simplemente no existe para quien la necesita, y nadie
se entera hasta que alguien la pide.

El typecheck no las ve porque no son errores de tipos: son acuerdos entre el
frontend y la base de datos.
"""
import pathlib
import re

import pytest
from sqlalchemy import text

UI = pathlib.Path(__file__).resolve().parents[2] / 'ui' / 'src'
PAGINAS = UI / 'paginas'


def fuente(ruta: pathlib.Path) -> str:
    return ruta.read_text(encoding='utf-8')


# ------------------------------------------- una pantalla que nadie puede ver

def test_todo_permiso_que_el_menu_exige_existe_y_algun_rol_lo_tiene(db):
    """Un permiso mal escrito, o que ningun rol tiene, esconde la pantalla.

    No falla nada: la entrada del menu simplemente no se dibuja. Quien la
    construyo la ve porque es administradora; el resto del equipo nunca sabe
    que existe.
    """
    nav = fuente(UI / 'navegacion.tsx')
    pedidos = set(re.findall(r"permiso: '([a-z_.]+)'", nav))
    assert pedidos, 'no se encontro ningun permiso en navegacion.tsx'

    existen = {r[0] for r in db.execute(text('select codigo from permisos'))}
    inventados = sorted(pedidos - existen)
    assert not inventados, (
        f'navegacion.tsx exige permisos que no existen: {inventados}. '
        f'Esas pantallas no se le muestran a nadie.')

    concedidos = {r[0] for r in db.execute(text(
        'select distinct pe.codigo from permisos pe '
        'join roles_permisos rp on rp.permiso_id = pe.id'))}
    de_nadie = sorted(pedidos - concedidos)
    assert not de_nadie, (
        f'estos permisos existen pero ningun rol los tiene: {de_nadie}. '
        f'Las pantallas que los exigen estan muertas.')


def test_toda_entrada_del_menu_tiene_su_ruta_registrada(db):
    """Una entrada del menu sin ruta en main.tsx lleva a una pagina en blanco."""
    nav = fuente(UI / 'navegacion.tsx')
    principal = fuente(UI / 'main.tsx')

    rutas_menu = set(re.findall(r"ruta: '(/[a-z0-9\-/]*)'", nav))
    rutas_app = set(re.findall(r"path: '(/[a-z0-9\-/:]*)'", principal))
    # Las que todavia no estan construidas se marcan y se atienden aparte.
    pendientes = set(re.findall(r"ruta: '(/[a-z0-9\-/]*)'[^}]*pendiente", nav))

    sin_ruta = sorted(rutas_menu - rutas_app - pendientes)
    assert not sin_ruta, (
        f'el menu ofrece estas rutas y main.tsx no las registra: {sin_ruta}')


# -------------------------------------- una tabla que empuja la pagina entera

#: Una tabla sin contenedor que deslice empuja la pagina a lo ancho en un
#: telefono: se mueve el encabezado, el menu, todo. Con el contenedor, la tabla
#: se desliza sola y el resto queda quieto (RNF-01).
def _tablas_sin_contenedor(texto: str) -> list[int]:
    sueltas = []
    for m in re.finditer(r'<Table[ >\n]', texto):
        i = m.start()
        if texto[i:i + 7] == '<Table.':
            continue
        antes = texto[:i]
        if antes.count('<Table.ScrollContainer') <= antes.count('</Table.ScrollContainer>'):
            sueltas.append(antes.count('\n') + 1)
    return sueltas


@pytest.mark.parametrize('pagina', sorted(p.name for p in PAGINAS.glob('*.tsx')))
def test_ninguna_tabla_empuja_la_pagina_a_lo_ancho(pagina):
    sueltas = _tablas_sin_contenedor(fuente(PAGINAS / pagina))
    assert not sueltas, (
        f'{pagina}: hay tablas sin <Table.ScrollContainer> en las lineas {sueltas}. '
        f'En un telefono empujan la pagina entera a lo ancho.')


def test_el_guardia_de_las_tablas_de_verdad_atrapa_una(tmp_path):
    """Que la prueba de arriba pase con una tabla suelta seria lo peor que
    podria pasarle: diria que todo esta bien sin mirar nada."""
    suelta = '<Stack>\n  <Table>\n    <Table.Thead />\n  </Table>\n</Stack>'
    envuelta = ('<Stack>\n  <Table.ScrollContainer minWidth={600}>\n'
                '    <Table>\n      <Table.Thead />\n    </Table>\n'
                '  </Table.ScrollContainer>\n</Stack>')
    assert _tablas_sin_contenedor(suelta) == [2]
    assert _tablas_sin_contenedor(envuelta) == []


# --------------------------------- una pantalla que muestra 100 de 189 y calla

#: Pantallas que todavia piden un listado paginado sin ofrecer paginador.
#:
#: Esta VACIA, y es la gracia. Tenia el tablero de tramites y el embudo mientras
#: se trabajaban (RF-022 y RF-011); al cerrarlos salieron. Es un permiso, no una
#: meta: sacar una de aqui no rompe nada, agregar una es declarar por escrito que
#: una pantalla miente, y eso cuesta explicarlo.
EN_OBRA: set[str] = set()


def _pide_listado_paginado(texto: str) -> bool:
    return bool(re.search(r'tamano:\s*\w', texto))


def _ofrece_paginador(texto: str) -> bool:
    """Las dos formas honestas de no cortar una lista en silencio.

    La primera es paginar. La segunda es avisar que se corto, y es la que
    corresponde a un BUSCADOR: un paginador dentro de un desplegable es la
    solucion equivocada -nadie pasa paginas en un combo, se escribe mas- pero el
    problema de fondo es el mismo y hay que resolverlo igual. `avisoDeCorte`
    (ui/src/componentes/Paginacion.tsx) es ese aviso.

    Lo que esta prueba NO acepta es la tercera forma, que es la que habia: pedir
    las primeras N y callarse.
    """
    return ('PiePaginacion' in texto or '<Pagination' in texto
            or 'avisoDeCorte' in texto)


@pytest.mark.parametrize('pagina', sorted(p.name for p in PAGINAS.glob('*.tsx')))
def test_ninguna_pantalla_corta_un_listado_sin_ofrecer_paginador(pagina):
    """Mostrar 100 de 189 e imprimir «189» debajo (RNF-08).

    Medido el 10/10: siete de las nueve pantallas de listado pedian tamano=100
    fijo, nunca mandaban pagina y no tenian control de paginas. No falla nada y
    no se ve: la tabla se llena, el pie anuncia el total de verdad, y las 89
    filas que faltan no son alcanzables por ningun camino. Quien busca un
    tramite y no lo encuentra concluye que no esta, y lo vuelve a crear.
    """
    texto = fuente(PAGINAS / pagina)
    if pagina in EN_OBRA or not _pide_listado_paginado(texto):
        return
    assert _ofrece_paginador(texto), (
        f'{pagina}: pide un listado con «tamano» y no dibuja paginador, asi que '
        f'corta la lista sin que se note. El pie compartido esta en '
        f'ui/src/componentes/Paginacion.tsx (PiePaginacion).')


def test_el_guardia_del_paginador_de_verdad_atrapa_una_pantalla_que_trunca():
    """Lo mismo que con las tablas: que pase sin mirar nada seria lo peor."""
    trunca = "const consulta = { tamano: 100 }\nreturn <Table />"
    pagina = ("const consulta = { pagina, tamano: TAMANO_PAGINA }\n"
              "return <><Table /><PiePaginacion total={d?.total} /></>")
    ninguna = 'return <Text>Hola</Text>'

    assert _pide_listado_paginado(trunca) and not _ofrece_paginador(trunca)
    assert _pide_listado_paginado(pagina) and _ofrece_paginador(pagina)
    assert not _pide_listado_paginado(ninguna)


# ------------------------- una peticion que en produccion no llega a la API

def test_ninguna_peticion_a_la_api_va_con_direccion_relativa():
    """Compila, funciona en desarrollo, y en produccion devuelve HTML (RNF-08).

    Las peticiones normales pasan por `api` (openapi-fetch), que ya lleva
    `baseUrl: VITE_API_URL`. Pero tres cosas se piden con `fetch` a pelo porque
    no son JSON -la exportacion, la subida de un archivo y la descarga de su
    contenido- y las tres traian la direccion escrita relativa.

    En desarrollo eso funciona: el proxy de Vite manda `/api` al backend. En
    produccion la pantalla vive en Vercel, la API en otro dominio, y vercel.json
    reescribe `/(.*)` a `/index.html`: la peticion le cae al propio frontend y
    recibe la pagina entera en HTML donde esperaba un archivo. Exportar a Excel,
    subir un pasaporte escaneado y descargarlo estaban rotos los tres, y nada lo
    decia: ni el typecheck, ni el build, ni una prueba.
    """
    relativas = []
    for archivo in sorted(UI.rglob('*.ts')) + sorted(UI.rglob('*.tsx')):
        for m in re.finditer(r"""fetch\(\s*['"`]/api""", fuente(archivo)):
            linea = fuente(archivo)[:m.start()].count('\n') + 1
            relativas.append(f'{archivo.relative_to(UI)}:{linea}')

    assert not relativas, (
        f'Estas peticiones usan una direccion relativa a la API: {relativas}. '
        'En produccion no llegan a la API, llegan al propio frontend y reciben '
        "index.html. Hay que prefijarlas con `urlApi` de src/api/cliente.ts.")


# ------------- una cabecera que el navegador esconde cuando cambia de dominio

def test_las_cabeceras_que_la_pantalla_lee_estan_declaradas_como_visibles():
    """El navegador esconde las cabeceras propias cuando el dominio no es el mismo.

    Solo entrega siete por omision; cualquier otra, aunque el servidor la mande,
    queda oculta y `r.headers.get(...)` devuelve null sin ningun error. En
    desarrollo no se nota, porque el proxy de Vite hace que todo sea el mismo
    origen; en produccion la pantalla esta en Vercel y la API en Render.

    La exportacion manda tres propias y las tres se leen en el frontend: el
    nombre del archivo, cuantas filas trae y cuales columnas se omitieron. La
    tercera es la que de verdad importa: sin ella, quien no puede ver los montos
    se lleva un archivo sin esas columnas y nada se lo dice.

    Esta prueba lee lo que el frontend pide y exige que el backend lo declare,
    asi que una cabecera nueva queda cubierta el dia que alguien la lea.
    """
    from app.main import CABECERAS_VISIBLES

    leidas = set()
    for archivo in sorted(UI.rglob('*.ts')) + sorted(UI.rglob('*.tsx')):
        texto = fuente(archivo)
        for m in re.finditer(r"""headers\.get\(\s*['"]([^'"]+)['"]""", texto):
            leidas.add(m.group(1).lower())

    # Las que el navegador entrega sin que nadie las declare.
    DE_REGALO = {'cache-control', 'content-language', 'content-length',
                 'content-type', 'expires', 'last-modified', 'pragma'}
    declaradas = {h.lower() for h in CABECERAS_VISIBLES}
    escondidas = sorted(leidas - DE_REGALO - declaradas)

    assert not escondidas, (
        f'El frontend lee estas cabeceras y el backend no las declara visibles: '
        f'{escondidas}. En produccion vuelven vacias, sin error. Agreguelas a '
        f'CABECERAS_VISIBLES en app/main.py.')
    assert leidas, 'no se encontro ninguna lectura de cabeceras; la prueba no esta mirando nada'


# ----------- una funcion que existe en la API y no se alcanza desde la pantalla

#: Lo que RF-020 pide en PLURAL y el backend ya resolvia, pero no se alcanzaba
#: desde ninguna pantalla: abrir el tramite de varias personas en una pasada, y
#: ponerle los demas que lo trabajan. Las dos estaban hechas, probadas y en el
#: openapi, y grep sobre ui/src daba cero.
#:
#: Una funcion que solo existe en la API es, para quien usa el sistema, una
#: funcion que no existe: la familia de cuatro se seguia dando de alta de a uno.
EN_LA_PANTALLA = {
    'casos/lote': 'abrir el tramite de varias personas de una vez (RF-020)',
    'colaboradores': 'decir quien mas trabaja el tramite (RF-020, RF-026)',
}


def test_lo_que_la_api_resuelve_en_plural_se_alcanza_desde_la_pantalla():
    fuentes = '\n'.join(fuente(a) for a in
                        sorted(UI.rglob('*.ts')) + sorted(UI.rglob('*.tsx')))
    assert fuentes, 'no se leyo ningun archivo del frontend'

    faltan = [f'{clave} ({para})' for clave, para in EN_LA_PANTALLA.items()
              if clave not in fuentes]
    assert not faltan, (
        'La API resuelve esto y ninguna pantalla lo usa, asi que para quien '
        f'trabaja no existe: {faltan}')
