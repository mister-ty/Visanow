"""Configuración de Alembic. La URL se lee del .env, nunca del alembic.ini."""
import os, pathlib, sys
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'backend'))


def _cargar_env() -> None:
    env = RAIZ / '.env'
    if not env.exists():
        return
    for linea in env.read_text(encoding='utf-8').splitlines():
        linea = linea.split('#')[0].strip()
        if '=' in linea:
            k, _, v = linea.partition('=')
            os.environ.setdefault(k.strip(), v.strip())


_cargar_env()
config = context.config
config.set_main_option('sqlalchemy.url', os.environ['DATABASE_URL'])
if config.config_file_name:
    # disable_existing_loggers=False a proposito. Por omision es True, y eso APAGA
    # todos los loggers que no esten declarados en alembic.ini: los de la
    # aplicacion entre ellos. En produccion no se nota porque arranque.sh corre
    # alembic en su propio proceso y despues hace exec de uvicorn, pero en
    # cualquier sitio donde alembic corra dentro del mismo proceso -las pruebas,
    # por ejemplo- la aplicacion se queda muda y no hay nada que lo diga.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = None  # el esquema se gobierna por SQL, no por autogenerate


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option('sqlalchemy.url'),
                      target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                    prefix='sqlalchemy.', poolclass=pool.NullPool)
    with conectable.connect() as conexion:
        context.configure(connection=conexion, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
