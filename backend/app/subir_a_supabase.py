"""Lleva la base de desarrollo a Supabase: esquema y datos (actividad 6.3).

El camino corto seria volver a correr la migracion desde los Excel apuntando a
Supabase, pero eso serian otra vez cuarenta minutos de lectura y homologacion, y
volveria a tropezar con las mismas filas dudosas que ya se resolvieron una vez.
Lo que se copia aqui es el resultado: la base que ya se verifico contra lo que
la administradora recordaba.

Dos pasos y en este orden:

1. **El esquema lo pone alembic**, no un volcado. Asi la base de Supabase queda
   con su `alembic_version` al dia y el proximo despliegue puede seguir
   migrando normalmente. Un esquema copiado a mano deja a alembic sin saber en
   que version esta.
2. **Los datos van con `pg_dump --data-only`.** Incluye el catalogo sembrado, asi
   que NO hay que correr el seed despues: duplicaria filas o chocaria contra las
   llaves unicas.

Las llaves foraneas se desactivan durante la carga con
`session_replication_role = replica`, porque `pg_dump` no garantiza emitir las
tablas en orden de dependencia y un `casos` antes de su `solicitantes` aborta
todo. Se vuelven a activar al terminar; si el script se cae a mitad, la sesion
muere con el y el ajuste no queda pegado.

EL ORDEN IMPORTA. Esta carga va ANTES del primer despliegue de Render. Si
Render arranca primero, su `arranque.sh` siembra el catalogo y entonces el
volcado choca contra las llaves unicas. Si ya paso, use `--limpiar`.

Uso:

    python -m app.subir_a_supabase "postgresql+psycopg://postgres.xxx:CLAVE@aws-0-us-east-1.pooler.supabase.com:5432/postgres"

Use la cadena del **Session pooler** (puerto 5432). La de transacciones (6543)
no admite sentencias preparadas y psycopg las usa.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _psql_bin(nombre: str) -> str:
    """El binario de PostgreSQL, que en Windows no suele estar en el PATH."""
    import glob
    for patron in (rf'C:\Program Files\PostgreSQL\*\bin\{nombre}.exe',
                   rf'C:\Program Files (x86)\PostgreSQL\*\bin\{nombre}.exe'):
        encontrados = sorted(glob.glob(patron))
        if encontrados:
            return encontrados[-1]
    return nombre


def _sin_driver(url: str) -> str:
    """psql y pg_dump no entienden el prefijo de SQLAlchemy."""
    return url.replace('postgresql+psycopg://', 'postgresql://')


def _url_desarrollo() -> str:
    for linea in (RAIZ / '.env').read_text(encoding='utf-8').splitlines():
        linea = linea.split('#')[0].strip()
        if linea.startswith('DATABASE_URL='):
            return _sin_driver(linea.partition('=')[2].strip())
    raise SystemExit('No encontre DATABASE_URL en el .env de desarrollo.')


def _correr(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', **kw)
    if r.returncode != 0:
        print((r.stderr or r.stdout)[-1500:])
        raise SystemExit(f'Fallo: {" ".join(cmd[:2])}')
    return r


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Falta la cadena de conexion de Supabase.\n'
                         'Uso: python -m app.subir_a_supabase "postgresql+psycopg://..."')
    destino_sa = sys.argv[1].strip().strip('"')
    if not destino_sa.startswith(('postgresql://', 'postgresql+psycopg://')):
        raise SystemExit('La cadena tiene que empezar por postgresql:// o postgresql+psycopg://')
    destino = _sin_driver(destino_sa)
    if 'pooler.supabase.com:6543' in destino:
        print('AVISO: esa es la cadena del pooler de TRANSACCIONES (6543). No admite\n'
              '       sentencias preparadas y psycopg las usa: la API fallaria sola.\n'
              '       Use la del Session pooler (puerto 5432).\n')

    limpiar = '--limpiar' in sys.argv
    origen = _url_desarrollo()
    pg_dump, psql = _psql_bin('pg_dump'), _psql_bin('psql')

    # Si Render desplego primero, su arranque ya sembro el catalogo (roles,
    # permisos, servicios, tarifas...) y el volcado chocaria contra las llaves
    # unicas a mitad de la carga, dejando la base medio llena. Se mira antes.
    ya = subprocess.run([psql, '-t', '-A', '-c',
                         "select coalesce((select count(*) from roles), 0)",
                         destino], capture_output=True, text=True)
    sembrada = ya.returncode == 0 and (ya.stdout or '0').strip().isdigit() \
        and int(ya.stdout.strip()) > 0
    if sembrada and not limpiar:
        raise SystemExit(
            'La base de Supabase ya tiene catalogo sembrado: probablemente Render\n'
            'desplego antes que esta carga. El volcado chocaria contra las llaves\n'
            'unicas y la dejaria a medias.\n\n'
            'Si esos datos no importan (es el catalogo del arranque, no datos de\n'
            'clientes), vuelva a correr con --limpiar y se borra todo antes de cargar.')
    if sembrada and limpiar:
        print('0/3  vaciando lo que habia...')
        _correr([psql, '--quiet', '-v', 'ON_ERROR_STOP=1', '-c', """
            do $$
            declare t record;
            begin
              for t in select tablename from pg_tables where schemaname = 'public'
              loop
                execute format('alter table public.%I disable trigger all', t.tablename);
                execute format('truncate table public.%I cascade', t.tablename);
                execute format('alter table public.%I enable trigger all', t.tablename);
              end loop;
            end $$;""", destino])
        print('     listo')

    print('1/3  esquema, con alembic...')
    entorno = dict(os.environ, PYTHONPATH='.', DATABASE_URL=destino_sa,
                   PYTHONIOENCODING='utf-8')
    _correr([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
            cwd=str(RAIZ / 'backend'), env=entorno)
    print('     listo')

    print('2/3  volcando los datos de desarrollo...')
    with tempfile.TemporaryDirectory() as tmp:
        volcado = pathlib.Path(tmp) / 'datos.sql'
        _correr([pg_dump, '--data-only', '--no-owner', '--no-privileges',
                 '--exclude-table=alembic_version', '-f', str(volcado), origen])
        tamano = volcado.stat().st_size
        print(f'     {tamano:,} bytes')

        # Las llaves foraneas se apagan solo durante la carga: pg_dump no
        # garantiza el orden de dependencia entre tablas.
        envuelto = pathlib.Path(tmp) / 'carga.sql'
        envuelto.write_text(
            'set session_replication_role = replica;\n'
            + volcado.read_text(encoding='utf-8')
            + '\nset session_replication_role = origin;\n', encoding='utf-8')

        print('3/3  cargando en Supabase...')
        _correr([psql, '--quiet', '-v', 'ON_ERROR_STOP=1', '-f', str(envuelto), destino])

    print('     listo')
    r = _correr([psql, '-t', '-A', '-c',
                 "select (select count(*) from clientes) || ' clientes, ' || "
                 "(select count(*) from negocios) || ' ventas, ' || "
                 "(select count(*) from casos) || ' tramites, ' || "
                 "(select count(*) from pagos) || ' pagos'", destino])
    print('\nEn Supabase quedaron:', r.stdout.strip())
    print('\nNO corra el seed: el volcado ya trae el catalogo sembrado.')


if __name__ == '__main__':
    main()
