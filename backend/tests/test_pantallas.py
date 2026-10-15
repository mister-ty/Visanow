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

#: Pantallas que todavia piden un listado paginado sin ofrecer paginador: las
#: dos que estan en obra, el tablero de tramites (RF-022) y el embudo (RF-011).
#: Esto es un permiso, no una meta. Sacar una de aqui no rompe nada; agregar una
#: es declarar por escrito que una pantalla miente, y eso cuesta explicarlo.
EN_OBRA = {'Casos.tsx', 'Embudo.tsx'}


def _pide_listado_paginado(texto: str) -> bool:
    return bool(re.search(r'tamano:\s*\w', texto))


def _ofrece_paginador(texto: str) -> bool:
    return 'PiePaginacion' in texto or '<Pagination' in texto


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
