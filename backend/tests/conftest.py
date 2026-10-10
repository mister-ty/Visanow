"""Las pruebas corren contra PostgreSQL real, no contra SQLite: el sistema depende
de vistas, índices parciales, columnas generadas, citext y triggers que SQLite
no tiene. Se crea una base visanow_test desde cero con las mismas migraciones y
el mismo seed que producción, y cada prueba corre dentro de una transacción que
se deshace al terminar.

Requiere la base arriba:  docker compose up -d db
"""
import os
import pathlib
import re
import secrets
from types import SimpleNamespace

# La URL de pruebas se fija ANTES de importar la app: la configuración y el
# motor de base de datos se crean al importar.
RAIZ = pathlib.Path(__file__).resolve().parents[2]


def _url_del_env() -> str:
    for linea in (RAIZ / '.env').read_text(encoding='utf-8').splitlines():
        linea = linea.split('#')[0].strip()
        if linea.startswith('DATABASE_URL='):
            return linea.partition('=')[2].strip()
    raise RuntimeError('Falta DATABASE_URL en el .env')


URL_BASE = _url_del_env()

#: El nombre de la base de pruebas se puede cambiar con BASE_PRUEBAS.
#:
#: La suite entera recrea esta base desde cero, asi que dos corridas a la vez
#: sobre el mismo nombre se tumban la una a la otra: la segunda hace DROP de la
#: base que la primera esta usando y lo que se ve son errores que no tienen nada
#: que ver con el codigo. Pasa al revisar varias cosas en paralelo, o con dos
#: terminales abiertas.
#:
#: Por omision es la de siempre, asi que nadie tiene que hacer nada distinto.
BASE_PRUEBAS = os.environ.get('BASE_PRUEBAS', 'visanow_test')
URL_PRUEBAS = re.sub(r'/[^/]+$', f'/{BASE_PRUEBAS}', URL_BASE)
os.environ['DATABASE_URL'] = URL_PRUEBAS
os.environ['APP_ENV'] = 'local'
os.environ['MFA_ROLES_OBLIGATORIO'] = 'administradora,finanzas'

import psycopg  # noqa: E402
import pyotp  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core import seguridad as seg  # noqa: E402
from app.db.session import get_db, motor  # noqa: E402
from app.main import app  # noqa: E402
from app.services import usuarios as servicio_usuarios  # noqa: E402
from app.services.usuarios import exige_mfa  # noqa: E402


@pytest.fixture(scope='session', autouse=True)
def base_de_pruebas():
    mantenimiento = re.sub(r'/[^/]+$', '/postgres', URL_BASE.replace('postgresql+psycopg://', 'postgresql://'))
    with psycopg.connect(mantenimiento, autocommit=True) as c:
        c.execute(f'drop database if exists {BASE_PRUEBAS} with (force)')
        c.execute(f'create database {BASE_PRUEBAS}')

    from alembic import command
    from alembic.config import Config
    cfg = Config(str(RAIZ / 'backend' / 'alembic.ini'))
    cfg.set_main_option('script_location', str(RAIZ / 'backend' / 'alembic'))
    command.upgrade(cfg, 'head')

    from app import seed
    seed.main()
    yield
    motor.dispose()


@pytest.fixture
def db():
    conexion = motor.connect()
    transaccion = conexion.begin()
    sesion = Session(bind=conexion, join_transaction_mode='create_savepoint', expire_on_commit=False)
    yield sesion
    sesion.close()
    transaccion.rollback()
    conexion.close()


@pytest.fixture
def cliente(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def usuario(db):
    """Fábrica: usuario('finanzas') devuelve uno listo para entrar.
    Quien por sus permisos exige doble factor sale con él activado, salvo con_mfa=False."""
    def _crear(rol: str = 'operaciones', *, listo: bool = True, con_mfa: bool | None = None):
        email = f'{rol}.{secrets.token_hex(3)}@visanow.co'
        u, temporal = servicio_usuarios.crear(db, None, nombre=f'Prueba {rol}', email=email, rol=rol)
        if listo:
            u.debe_cambiar_password = False
        if con_mfa is None:
            con_mfa = listo and exige_mfa(db, u)
        secreto = None
        if con_mfa:
            secreto = pyotp.random_base32()
            u.mfa_secreto = seg.cifrar(secreto)
            u.mfa_habilitado = True
        db.commit()
        return SimpleNamespace(u=u, email=email, password=temporal, secreto=secreto)
    return _crear


def entrar(cliente, p) -> dict:
    """Ingresa (con doble factor si aplica) y devuelve la cabecera de autorización."""
    r = cliente.post('/api/v1/auth/login', json={'email': p.email, 'password': p.password})
    assert r.status_code == 200, r.text
    datos = r.json()
    if datos.get('requiere_mfa'):
        r = cliente.post('/api/v1/auth/mfa/verificar',
                         json={'token_mfa': datos['token_mfa'], 'codigo': pyotp.TOTP(p.secreto).now()})
        assert r.status_code == 200, r.text
        datos = r.json()
    return {'Authorization': f"Bearer {datos['access_token']}"}
