"""Respaldo de la base de producción, con prueba de restauración (RNF-06).

El plan gratuito de Supabase no hace respaldos. Ahí viven los datos de 866
personas con sus pasaportes, así que «no hay respaldos» no es una limitación
aceptable: es un día de trabajo de todos perdido si algo se borra, y no hay
forma de volver atrás.

**La prueba de restauración es la mitad que importa.** Un archivo que nadie ha
restaurado nunca no es un respaldo, es un archivo. Por eso `verificar` no mira
que el archivo exista ni que pese: lo restaura de verdad en una base desechable
y cuenta las filas tabla por tabla contra el original. Si no cuadran, el
respaldo no sirve y hay que saberlo hoy, no el día que haga falta.

**Guarda varios días.** Un solo respaldo que se sobrescribe no protege del caso
más común, que no es el disco que se quema sino el borrado que nadie notó hasta
el martes siguiente.

**Para restaurar en otro servidor hay que crear antes las extensiones.**
`pg_dump --schema=public` no las incluye, porque una extensión pertenece a la
base y no al esquema. Son `citext`, `pg_trgm` y `unaccent`:

    create extension if not exists citext;
    create extension if not exists pg_trgm;
    create extension if not exists unaccent;
    pg_restore --no-owner --no-privileges -d <base> <archivo>.dump

Sin ellas, las tablas que usan `citext` -clientes, solicitantes y usuarios-
se restauran VACÍAS y el resto parece correcto. `verificar` las crea solo.

Uso:

    python -m app.respaldo crear          # saca el respaldo y lo verifica
    python -m app.respaldo crear --rapido # sin prueba de restauración
    python -m app.respaldo verificar      # restaura el último y lo compara
    python -m app.respaldo listar

La cadena de conexión se lee de `.env.respaldo` en la raíz del repositorio
(bloqueado por .gitignore) o de la variable `RESPALDO_URL`.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import pathlib
import subprocess
import sys
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo('America/Bogota')
RAIZ = pathlib.Path(__file__).resolve().parents[2]
DESTINO = pathlib.Path(os.environ.get('RESPALDO_CARPETA')
                       or (RAIZ.parent / '99_Respaldos'))
DIAS_A_GUARDAR = int(os.environ.get('RESPALDO_DIAS', '30'))


def _bin(nombre: str) -> str:
    for patron in (rf'C:\Program Files\PostgreSQL\*\bin\{nombre}.exe',
                   rf'C:\Program Files (x86)\PostgreSQL\*\bin\{nombre}.exe'):
        hallados = sorted(glob.glob(patron))
        if hallados:
            return hallados[-1]
    return nombre


def _sin_driver(url: str) -> str:
    return url.replace('postgresql+psycopg://', 'postgresql://')


def _url() -> str:
    """De dónde se respalda. Nunca escrita en el código ni en el repositorio."""
    if os.environ.get('RESPALDO_URL'):
        return _sin_driver(os.environ['RESPALDO_URL'])
    archivo = RAIZ / '.env.respaldo'
    if archivo.exists():
        for linea in archivo.read_text(encoding='utf-8').splitlines():
            linea = linea.split('#')[0].strip()
            if linea.startswith('RESPALDO_URL='):
                return _sin_driver(linea.partition('=')[2].strip())
    raise SystemExit(
        'No sé de dónde respaldar. Cree ' + str(RAIZ / '.env.respaldo') + ' con:\n'
        '    RESPALDO_URL=postgresql+psycopg://usuario:clave@host:5432/postgres\n'
        'o defina la variable de entorno RESPALDO_URL.')


def _url_local_scratch() -> str:
    """La base de desarrollo, que es donde se prueba la restauración.

    Se usa su servidor para crear una base desechable: restaurar sobre la de
    desarrollo seria destruirla, y restaurar sobre la de produccion seria
    absurdo.
    """
    for linea in (RAIZ / '.env').read_text(encoding='utf-8').splitlines():
        linea = linea.split('#')[0].strip()
        if linea.startswith('DATABASE_URL='):
            return _sin_driver(linea.partition('=')[2].strip())
    raise SystemExit('No encontré DATABASE_URL en el .env para probar la restauración.')


def _correr(cmd: list[str], permitir_fallo: bool = False) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace')
    if r.returncode != 0 and not permitir_fallo:
        print((r.stderr or r.stdout)[-1200:])
        raise SystemExit(f'Falló: {pathlib.Path(cmd[0]).name}')
    return r


def _contar(url: str) -> dict[str, int]:
    """Filas por tabla, para comparar origen contra restaurado."""
    sql = """
    select table_name, (xpath('/row/c/text()',
           query_to_xml(format('select count(*) as c from public.%I', table_name),
                        false, true, '')))[1]::text::int
      from information_schema.tables
     where table_schema = 'public' and table_type = 'BASE TABLE'
       and table_name <> 'alembic_version'
     order by table_name;"""
    r = _correr([_bin('psql'), '-t', '-A', '-F', '|', '-c', sql, url])
    return {l.split('|')[0]: int(l.split('|')[1])
            for l in r.stdout.strip().splitlines() if '|' in l}


def _extensiones_de(url: str) -> list[str]:
    """Las extensiones que el esquema `public` necesita para existir.

    `pg_dump --schema=public` NO las incluye: una extension es un objeto de la
    base, no del esquema. La primera prueba de restauracion lo descubrio de la
    peor forma posible y de la mejor: `clientes`, `solicitantes` y `usuarios`
    -las tres que usan `citext` para el correo- restauraron con CERO filas,
    porque el tipo no existia en el destino. El respaldo pesaba bien y parecia
    correcto.
    """
    r = _correr([_bin('psql'), '-t', '-A', '-c',
                 "select extname from pg_extension e "
                 "join pg_namespace n on n.oid = e.extnamespace "
                 "where n.nspname = 'public'", url])
    return [x.strip() for x in r.stdout.splitlines() if x.strip()]


# ------------------------------------------------------------------- crear

def crear(verificar_despues: bool = True) -> pathlib.Path:
    DESTINO.mkdir(parents=True, exist_ok=True)
    sello = dt.datetime.now(BOGOTA).strftime('%Y-%m-%d_%H%M')
    archivo = DESTINO / f'visanow-{sello}.dump'

    print(f'respaldando a {archivo.name} ...')
    # Formato propio de PostgreSQL: pesa menos y se restaura con pg_restore,
    # que puede hacerlo por partes. Solo el esquema `public`: lo demas que trae
    # Supabase (auth, storage) no es nuestro y no nos toca respaldarlo.
    _correr([_bin('pg_dump'), '--format=custom', '--compress=9',
             '--schema=public', '--no-owner', '--no-privileges',
             '--file', str(archivo), _url()])
    tamano = archivo.stat().st_size
    print(f'   {tamano:,} bytes')
    if tamano < 10_000:
        raise SystemExit('El respaldo pesa demasiado poco: algo salió mal.')

    limpiar()
    if verificar_despues:
        verificar(archivo)
    return archivo


def limpiar() -> None:
    """Borra lo más viejo que el plazo. Guardar para siempre tampoco sirve."""
    limite = dt.datetime.now(BOGOTA) - dt.timedelta(days=DIAS_A_GUARDAR)
    borrados = 0
    for viejo in DESTINO.glob('visanow-*.dump'):
        cuando = dt.datetime.fromtimestamp(viejo.stat().st_mtime, BOGOTA)
        if cuando < limite:
            viejo.unlink()
            borrados += 1
    if borrados:
        print(f'   {borrados} respaldo(s) de más de {DIAS_A_GUARDAR} días, eliminados')


# --------------------------------------------------------------- verificar

def ultimo() -> pathlib.Path:
    archivos = sorted(DESTINO.glob('visanow-*.dump'))
    if not archivos:
        raise SystemExit(f'No hay respaldos en {DESTINO}.')
    return archivos[-1]


def verificar(archivo: pathlib.Path | None = None) -> bool:
    """Restaura de verdad y compara fila por fila (RNF-06).

    Sobre una base desechable que se crea y se borra. Si esto no se hiciera, el
    respaldo seria una promesa: el dia que haga falta es tarde para descubrir
    que el archivo estaba truncado o que faltaba media tabla.
    """
    archivo = archivo or ultimo()
    print(f'\nprobando la restauración de {archivo.name} ...')

    local = _url_local_scratch()
    mantenimiento = local.rsplit('/', 1)[0] + '/postgres'
    nombre = 'visanow_restauracion'
    scratch = local.rsplit('/', 1)[0] + '/' + nombre

    _correr([_bin('psql'), '-q', '-c', f'drop database if exists {nombre} with (force)',
             mantenimiento])
    _correr([_bin('psql'), '-q', '-c', f'create database {nombre}', mantenimiento])
    try:
        # Sin esto, las tablas que usan `citext` se restauran vacias y el
        # respaldo parece correcto cuando no lo es.
        extensiones = _extensiones_de(_url())
        for ext in extensiones:
            _correr([_bin('psql'), '-q', '-c',
                     f'create extension if not exists "{ext}"', scratch])
        if extensiones:
            print(f'   extensiones preparadas: {", ".join(extensiones)}')
        # --no-owner: el dueño en Supabase no existe en el servidor local, y no
        # importa para contar filas.
        r = _correr([_bin('pg_restore'), '--no-owner', '--no-privileges',
                     '--dbname', scratch, str(archivo)], permitir_fallo=True)
        if r.returncode != 0:
            # pg_restore avisa de cosas que no son errores (extensiones que ya
            # existen, por ejemplo). Lo que decide es si las filas cuadran.
            print('   pg_restore terminó con avisos; se comparan las filas igual')

        origen, restaurado = _contar(_url()), _contar(scratch)
        faltan = [(t, origen[t], restaurado.get(t, 0))
                  for t in sorted(origen) if origen[t] != restaurado.get(t, 0)]
        total = sum(origen.values())
        if faltan:
            print(f'   NO CUADRA. {len(faltan)} tabla(s) con diferencias:')
            for t, a, b in faltan[:12]:
                print(f'      {t:<28} original={a:<7} restaurado={b}')
            return False
        print(f'   restauración correcta: {len(origen)} tablas, {total:,} filas, '
              f'todas cuadran')
        return True
    finally:
        _correr([_bin('psql'), '-q', '-c', f'drop database if exists {nombre} with (force)',
                 mantenimiento], permitir_fallo=True)


def listar() -> None:
    archivos = sorted(DESTINO.glob('visanow-*.dump'), reverse=True)
    if not archivos:
        print(f'No hay respaldos en {DESTINO}.')
        return
    print(f'{len(archivos)} respaldo(s) en {DESTINO}:')
    for a in archivos[:15]:
        cuando = dt.datetime.fromtimestamp(a.stat().st_mtime, BOGOTA)
        print(f'   {cuando:%Y-%m-%d %H:%M}   {a.stat().st_size:>10,} bytes   {a.name}')


def main() -> None:
    orden = sys.argv[1] if len(sys.argv) > 1 else 'crear'
    if orden == 'crear':
        archivo = crear(verificar_despues='--rapido' not in sys.argv)
        print(f'\nlisto: {archivo}')
    elif orden == 'verificar':
        if not verificar():
            raise SystemExit(1)
    elif orden == 'listar':
        listar()
    else:
        raise SystemExit('Órdenes: crear [--rapido] | verificar | listar')


if __name__ == '__main__':
    main()
