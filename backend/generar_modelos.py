"""Regenera app/models/esquema.py a partir de la base de datos.

El esquema se gobierna por SQL (db/schema/ y las migraciones de Alembic); los
modelos de SQLAlchemy son un reflejo de él y no se editan a mano. Después de
cada migración que cambie tablas:

    python -m alembic upgrade head
    python generar_modelos.py
"""
import os
import pathlib
import subprocess
import sys

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parent
DESTINO = AQUI / 'app' / 'models' / 'esquema.py'

CABECERA = '''"""GENERADO por generar_modelos.py a partir de la base de datos. NO EDITAR A MANO.

Para cambiar una tabla: escribir una migración de Alembic, aplicarla y volver
a correr generar_modelos.py.
"""
'''


def url_de_la_base() -> str:
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    for linea in (RAIZ / '.env').read_text(encoding='utf-8').splitlines():
        linea = linea.split('#')[0].strip()
        if linea.startswith('DATABASE_URL='):
            return linea.partition('=')[2].strip()
    sys.exit('No se encontró DATABASE_URL en el entorno ni en el .env')


def main() -> None:
    sqlacodegen = pathlib.Path(sys.executable).parent / 'sqlacodegen'
    salida = subprocess.run([str(sqlacodegen), url_de_la_base(), '--outfile', str(DESTINO)],
                            capture_output=True, text=True)
    if salida.returncode != 0:
        sys.exit(salida.stderr)
    DESTINO.write_text(CABECERA + DESTINO.read_text(encoding='utf-8'), encoding='utf-8')
    clases = DESTINO.read_text(encoding='utf-8').count('\nclass ') - 1
    print(f'{DESTINO.relative_to(RAIZ)}: {clases} modelos')


if __name__ == '__main__':
    main()
