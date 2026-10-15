"""El respaldo, que es lo único que no se puede dar por bueno (RNF-06).

Este módulo no tenía ni una prueba, y es el que sostiene todo lo demás: el plan
gratuito de Supabase no hace respaldos, así que `app/respaldo.py` es la única
vuelta atrás que existe para los datos de 895 personas con sus pasaportes.

Lo que se prueba acá no es que el respaldo funcione —eso lo prueba `verificar`
restaurando de verdad contra una base desechable, y eso necesita producción—.
Lo que se prueba es lo que puede fallar **en silencio**, que en un respaldo es
la única falla que importa:

- que `comparar` no diga «todas cuadran» cuando no comparó nada;
- que `crear` no borre los respaldos viejos antes de saber que el nuevo sirve;
- que `crear` falle de verdad, con código distinto de cero, cuando el respaldo
  no pasa la prueba — antes imprimía «NO CUADRA» y después «listo», y salía con
  cero, de modo que una tarea programada lo reportaba bien todos los días;
- que `ultimo` encuentre de verdad el más reciente.

Las tres primeras son el mismo error, el que más veces ha aparecido en este
proyecto: una comprobación que se cumple sin comprobar.
"""
import datetime as dt
import os

import pytest

from app import respaldo


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    """Una carpeta de respaldos de mentiras, para no tocar 99_Respaldos."""
    monkeypatch.setattr(respaldo, 'DESTINO', tmp_path)
    return tmp_path


def dump(carpeta, nombre: str, *, dias_atras: float = 0, bytes_: int = 50_000):
    archivo = carpeta / nombre
    archivo.write_bytes(b'x' * bytes_)
    if dias_atras:
        cuando = (dt.datetime.now(respaldo.BOGOTA)
                  - dt.timedelta(days=dias_atras)).timestamp()
        os.utime(archivo, (cuando, cuando))
    return archivo


# --------------------------------------------- comparar, que no puede mentir

def test_comparar_no_da_por_bueno_un_respaldo_del_que_no_contó_nada():
    """El agujero: la comparación recorre las tablas del origen.

    Con el origen vacío la lista de diferencias sale vacía, y antes eso se leía
    como «las 0 tablas cuadran». Un respaldo marcado como verificado sin haber
    comparado una fila es peor que uno sin verificar: nadie lo vuelve a mirar.
    """
    with pytest.raises(SystemExit) as fallo:
        respaldo.comparar({}, {})
    assert 'no hay nada que comparar' in str(fallo.value)

    # Y tampoco si el origen está vacío pero el restaurado trae cosas: eso
    # significa que no se pudo contar, no que todo esté bien.
    with pytest.raises(SystemExit):
        respaldo.comparar({}, {'clientes': 895})


def test_comparar_señala_la_tabla_que_llegó_corta():
    """El caso real que se descubrió restaurando: las tablas con `citext`
    llegaron con cero filas porque faltaba la extensión, y el archivo pesaba
    bien."""
    origen = {'clientes': 895, 'pagos': 634, 'casos': 551}
    restaurado = {'clientes': 0, 'pagos': 634, 'casos': 551}

    assert respaldo.comparar(origen, restaurado) == [('clientes', 895, 0)]


def test_comparar_cuenta_como_diferencia_la_tabla_que_no_llegó():
    """Una tabla ausente no es cero filas por casualidad: es que no está."""
    assert respaldo.comparar({'clientes': 895}, {}) == [('clientes', 895, 0)]


def test_comparar_no_inventa_diferencias_cuando_todo_cuadra():
    origen = {'clientes': 895, 'pagos': 634}
    assert respaldo.comparar(origen, dict(origen)) == []


# ------------------------------------------------- cuál es el último respaldo

def test_ultimo_encuentra_el_mas_reciente_y_no_el_ultimo_alfabetico(carpeta):
    """El nombre lleva la fecha con ceros adelante justamente para esto.

    Si el sello del archivo no estuviera rellenado, «visanow-2026-10-9_900»
    quedaría después de «visanow-2026-10-13_1108» al ordenar como texto, y
    `verificar` probaría el respaldo equivocado sin decir nada.
    """
    dump(carpeta, 'visanow-2026-10-09_0900.dump')
    dump(carpeta, 'visanow-2026-10-13_1108.dump')
    esperado = dump(carpeta, 'visanow-2026-10-13_2200.dump')

    assert respaldo.ultimo() == esperado


def test_ultimo_avisa_cuando_no_hay_ninguno(carpeta):
    with pytest.raises(SystemExit) as fallo:
        respaldo.ultimo()
    assert 'No hay respaldos' in str(fallo.value)


# ------------------------------------------------- limpiar, que borra archivos

def test_limpiar_solo_borra_lo_mas_viejo_que_el_plazo(carpeta, monkeypatch):
    """Es la función más peligrosa del repositorio: borra la red de seguridad."""
    monkeypatch.setattr(respaldo, 'DIAS_A_GUARDAR', 30)
    reciente = dump(carpeta, 'visanow-2026-10-14_0800.dump', dias_atras=1)
    justo = dump(carpeta, 'visanow-2026-09-20_0800.dump', dias_atras=29)
    viejo = dump(carpeta, 'visanow-2026-08-01_0800.dump', dias_atras=75)

    respaldo.limpiar()

    assert reciente.exists(), 'borró el respaldo de ayer'
    assert justo.exists(), 'borró uno que todavía está dentro del plazo'
    assert not viejo.exists(), 'no borró el que ya pasó el plazo'


def test_limpiar_no_toca_lo_que_no_es_un_respaldo(carpeta, monkeypatch):
    """La carpeta es de la usuaria; puede tener otras cosas adentro."""
    monkeypatch.setattr(respaldo, 'DIAS_A_GUARDAR', 1)
    ajeno = carpeta / 'notas de la administradora.txt'
    ajeno.write_text('no borrar', encoding='utf-8')
    otro = dump(carpeta, 'export-contabilidad-2026.dump', dias_atras=400)

    respaldo.limpiar()

    assert ajeno.exists() and otro.exists()


# ------------------------------- crear: ni borra ni dice «listo» a la ligera

@pytest.fixture
def pg_falso(monkeypatch):
    """Reemplaza las llamadas a pg_dump: la prueba no respalda nada de verdad."""
    def _correr(cmd, permitir_fallo=False):
        if '--file' in cmd:
            destino = cmd[cmd.index('--file') + 1]
            with open(destino, 'wb') as f:
                f.write(b'x' * 50_000)
        return type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
    monkeypatch.setattr(respaldo, '_correr', _correr)
    monkeypatch.setattr(respaldo, '_url', lambda: 'postgresql://x/y')


def test_crear_falla_de_verdad_cuando_el_respaldo_no_pasa_la_prueba(
        carpeta, pg_falso, monkeypatch):
    """Antes imprimía «NO CUADRA» y después «listo», y salía con código 0.

    Una tarea programada que mira el código de salida lo habría reportado como
    exitoso todos los días. Es la peor forma de no tener respaldos: creyendo
    que sí.
    """
    monkeypatch.setattr(respaldo, 'verificar', lambda archivo=None: False)

    with pytest.raises(SystemExit) as fallo:
        respaldo.crear()
    assert 'NO pasó la prueba' in str(fallo.value)


def test_crear_no_borra_los_respaldos_viejos_si_el_nuevo_no_sirve(
        carpeta, pg_falso, monkeypatch):
    """`limpiar()` corría antes de verificar, así que un respaldo nuevo malo se
    llevaba por delante a los viejos, que eran los únicos que servían."""
    monkeypatch.setattr(respaldo, 'DIAS_A_GUARDAR', 30)
    monkeypatch.setattr(respaldo, 'verificar', lambda archivo=None: False)
    viejo_pero_bueno = dump(carpeta, 'visanow-2026-01-01_0800.dump', dias_atras=200)

    with pytest.raises(SystemExit):
        respaldo.crear()

    assert viejo_pero_bueno.exists(), (
        'borró el único respaldo que servía porque el nuevo "ya estaba hecho"')


def test_crear_si_limpia_cuando_el_nuevo_paso_la_prueba(
        carpeta, pg_falso, monkeypatch):
    monkeypatch.setattr(respaldo, 'DIAS_A_GUARDAR', 30)
    monkeypatch.setattr(respaldo, 'verificar', lambda archivo=None: True)
    viejo = dump(carpeta, 'visanow-2026-01-01_0800.dump', dias_atras=200)

    archivo = respaldo.crear()

    assert archivo.exists() and archivo.stat().st_size >= 10_000
    assert not viejo.exists(), 'con el nuevo verificado, sí hay que limpiar'


def test_crear_rechaza_un_respaldo_sospechosamente_pequeno(
        carpeta, monkeypatch):
    """Un dump de dos kilobytes no es la base de 895 personas."""
    def _correr(cmd, permitir_fallo=False):
        if '--file' in cmd:
            with open(cmd[cmd.index('--file') + 1], 'wb') as f:
                f.write(b'nada')
        return type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()
    monkeypatch.setattr(respaldo, '_correr', _correr)
    monkeypatch.setattr(respaldo, '_url', lambda: 'postgresql://x/y')

    with pytest.raises(SystemExit) as fallo:
        respaldo.crear(verificar_despues=False)
    assert 'pesa demasiado poco' in str(fallo.value)
