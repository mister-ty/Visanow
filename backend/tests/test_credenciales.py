"""El sistema no tiene dónde guardar la contraseña consular de un cliente (RNF-10).

Los Excel que trae VisaNow incluyen, en texto plano y al lado del nombre, la
contraseña del portal consular de cada persona. El requisito dice que no se
almacenen cifradas en el sistema o, si se almacenan, que haya un gestor de
secretos con acceso trazable. La decisión D-09 escogió lo primero y lo llevó más
lejos: no se almacenan en ninguna forma, ni cifradas. Un dato que no está no se
filtra, no hay que rotarlo, no aparece en un respaldo y no hay que explicarlo en
un incidente. No existe la columna, y por eso tampoco hace falta el gestor.

Esa clase de decisión se deshace sola si nadie la vigila. Son dos renglones de
una migración y una casilla en un formulario, puestos por alguien que no sabía,
con la mejor intención: «es que la asesora necesita entrar al portal». Estas
pruebas son lo que hace que eso no pase callado:

- que ninguna tabla tenga una columna donde quepa esa credencial, y
- que la lectura de los Excel siga botando esas columnas, aunque el día de
  mañana el encabezado se escriba distinto.

La segunda no es teórica. El filtro era coincidencia exacta y sensible a
mayúsculas, y funcionaba por casualidad: las dos hojas reales traen literalmente
«CONTRASEÑA». Un libro que dijera «Clave consular» habría pasado derecho.
"""
import pytest
from sqlalchemy import text

from app.migracion.fuentes import es_columna_de_credencial, sin_credenciales

#: Las palabras que delatarían una columna de credencial, buscadas sobre los
#: nombres de columna de la base entera.
SOSPECHOSAS = r'(contrasena|contrase|clave|password|passwd|secreto|token|credencial)'

#: Las únicas columnas que pueden sonar a credencial, con el motivo por el que
#: cada una está bien. Todas son de la cuenta de alguien del equipo para entrar
#: a ESTE sistema; ninguna es de un cliente ni de un portal ajeno.
#:
#: La lista es exacta a propósito. Si aparece una columna nueva acá, esta prueba
#: falla y alguien tiene que decidir por escrito si de verdad va —que es
#: justamente lo que D-09 ya decidió que no.
PERMITIDAS = {
    ('usuarios', 'password_hash'),        # Argon2id, de un usuario del equipo
    ('usuarios', 'password_cambiado_en'), # una fecha, no un secreto
    ('usuarios', 'debe_cambiar_password'),  # un sí o no
    ('usuarios', 'mfa_secreto'),          # la semilla del doble factor, cifrada
    ('parametros', 'clave'),              # el nombre de un parámetro, no una clave
    ('alertas', 'clave_dedupe'),          # la huella que evita alertas repetidas
}


def test_ninguna_tabla_tiene_donde_guardar_la_credencial_de_un_cliente(db):
    """D-09: la columna no existe, y que no exista es la medida de seguridad."""
    halladas = {(t, c) for t, c in db.execute(text(f"""
        select table_name, column_name from information_schema.columns
         where table_schema = 'public' and column_name ~* '{SOSPECHOSAS}'
    """))}

    nuevas = sorted(halladas - PERMITIDAS)
    assert not nuevas, (
        f'Aparecieron columnas que pueden guardar una credencial: {nuevas}. '
        'RNF-10 y la decisión D-09 dicen que el sistema no las almacena, ni '
        'cifradas: la contraseña del portal consular de un cliente no entra. Si '
        'de verdad hace falta, hay que reabrir D-09 y entonces el requisito '
        'exige además un gestor de secretos con acceso trazable, que no existe.')

    # Al revés también: si una de las permitidas se dejó de llamar así, la lista
    # está desactualizada y la de arriba estaría comparando contra fantasmas.
    desaparecidas = sorted(PERMITIDAS - halladas)
    assert not desaparecidas, (
        f'Estas columnas ya no existen: {desaparecidas}. La lista de permitidas '
        'está vieja, así que esta prueba está vigilando menos de lo que cree.')


def test_ninguna_pantalla_pide_la_contrasena_de_un_cliente():
    """Lo mismo por el otro lado: que no haya dónde escribirla.

    Las pantallas que sí hablan de contraseñas son las de la cuenta del equipo
    —ingreso, cambio, doble factor, recuperación, usuarios, configuración—. En
    las de clientes, trámites y solicitantes no aparece la palabra.
    """
    import pathlib
    import re

    paginas = pathlib.Path(__file__).resolve().parents[2] / 'ui' / 'src' / 'paginas'
    de_la_cuenta = {'Ingreso.tsx', 'CambiarContrasena.tsx', 'DobleFactor.tsx',
                    'Recuperacion.tsx', 'Usuarios.tsx', 'Configuracion.tsx'}

    culpables = []
    for pagina in sorted(paginas.glob('*.tsx')):
        if pagina.name in de_la_cuenta:
            continue
        texto = pagina.read_text(encoding='utf-8')
        if re.search(r'contrase|password', texto, re.I):
            culpables.append(pagina.name)

    assert not culpables, (
        f'{culpables} hablan de contraseñas y no son pantallas de la cuenta del '
        'equipo. Si se le está pidiendo una credencial a un cliente, eso va '
        'contra RNF-10.')


# ----------------------------------- la lectura de los Excel sigue botándolas

@pytest.mark.parametrize('encabezado', [
    'CONTRASEÑA',            # como viene hoy en los dos libros reales
    'CONTRASENA',
    'Contraseña',            # el mismo título escrito por otra persona
    'contraseña',
    ' CONTRASEÑA ',          # con los espacios que deja Excel
    'CONTRASEÑA PORTAL',
    'Clave consular',
    'CLAVE',
    'Password',
    'PASSWD',
    'clave del AVE',
])
def test_un_encabezado_de_credencial_se_reconoce_escrito_como_sea(encabezado):
    """El filtro no puede depender de cómo alguien tituló una columna.

    Todos estos aparecieron o pueden aparecer en un libro de VisaNow, que se
    reorganiza mes a mes. Con la comparación exacta anterior, solo los dos
    primeros se reconocían.
    """
    assert es_columna_de_credencial(encabezado)


@pytest.mark.parametrize('encabezado', [
    'NOMBRE', 'PASAPORTE', 'TELÉFONO', 'CORREO', 'VALOR', 'FECHA DE CITA',
    'ESTADO', 'OBSERVACIONES', 'DS-160', '', None,
])
def test_una_columna_normal_no_se_bota(encabezado):
    """Buscar por pedazo abre la puerta a botar columnas buenas; estas son las
    que de verdad traen los libros y ninguna se toca."""
    assert not es_columna_de_credencial(encabezado)


def test_la_fila_llega_al_resto_del_programa_sin_la_credencial():
    """Que se reconozca no basta: hay que ver que salga de la fila.

    Se saca antes de que nadie lea la fila, así que el valor no se copia a
    ningún aporte, no se registra y no llega a la base. `migracion_filas` solo
    guarda archivo, hoja, número de fila y huella.
    """
    celdas = {
        'NOMBRE': 'Ana Pérez',
        'PASAPORTE': 'AB123456',
        'CONTRASEÑA': 'loquesea123',
        'Clave consular': 'otra-mas',
        'TELÉFONO': '3105177800',
    }
    sacadas = sin_credenciales(celdas)

    assert sorted(sacadas) == ['CONTRASEÑA', 'Clave consular']
    assert set(celdas) == {'NOMBRE', 'PASAPORTE', 'TELÉFONO'}
    assert 'loquesea123' not in str(celdas)
    assert 'otra-mas' not in str(celdas)
