"""Actividad 2.2 — administración de catálogos.

sqladmin abre sus propias sesiones, así que estas pruebas crean usuarios
confirmados (no dentro de la transacción del fixture db, que no verían)."""
import secrets
from decimal import Decimal
from types import SimpleNamespace

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import seguridad as seg
from app.db.session import SesionLocal
from app.main import app
from app.models.esquema import Auditoria, Parametros, Servicios, Tarifas
from app.services import auth as servicio_auth
from app.services import usuarios as servicio_usuarios


def _usuario_real(rol: str, *, mfa: bool = True):
    email = f'admin.{rol}.{secrets.token_hex(3)}@visanow.co'
    with SesionLocal() as s:
        u, temporal = servicio_usuarios.crear(s, None, nombre=f'Panel {rol}', email=email, rol=rol)
        u.debe_cambiar_password = False
        secreto = None
        if mfa:
            secreto = pyotp.random_base32()
            u.mfa_secreto = seg.cifrar(secreto)
            u.mfa_habilitado = True
        s.commit()
        return SimpleNamespace(id=u.id, email=email, password=temporal, secreto=secreto)


def _entrar(cliente, p, codigo: str | None = None):
    return cliente.post('/admin/login', data={
        'username': p.email, 'password': p.password,
        'codigo': codigo if codigo is not None else pyotp.TOTP(p.secreto).now()})


@pytest.fixture
def panel():
    with TestClient(app) as c:
        yield c


def test_sin_sesion_manda_al_ingreso(panel):
    r = panel.get('/admin/servicios/list')
    assert r.url.path == '/admin/login'


def test_la_administradora_entra_y_ve_el_catalogo_real(panel):
    _entrar(panel, _usuario_real('administradora'))
    r = panel.get('/admin/servicios/list')
    assert r.status_code == 200 and r.url.path == '/admin/servicios/list'
    assert 'Asesoría USA + adelanto (Premium)' in r.text


def test_codigo_errado_no_entra(panel):
    p = _usuario_real('administradora')
    errado = str((int(pyotp.TOTP(p.secreto).now()) + 1) % 1_000_000).zfill(6)
    r = _entrar(panel, p, errado)
    assert 'Código de verificación incorrecto' in r.text
    assert panel.get('/admin/servicios/list').url.path == '/admin/login'


def test_quien_no_administra_catalogos_no_entra(panel):
    r = _entrar(panel, _usuario_real('finanzas'))
    assert 'no tiene acceso a la administración' in r.text
    assert panel.get('/admin/servicios/list').url.path == '/admin/login'


def test_sin_doble_factor_no_entra(panel):
    r = _entrar(panel, _usuario_real('administradora', mfa=False), '000000')
    assert 'Active primero el doble factor' in r.text


def test_editar_un_parametro_queda_auditado_con_antes_y_despues(panel):
    p = _usuario_real('administradora')
    _entrar(panel, p)
    r = panel.post('/admin/parametros/edit/cartera.plazo_saldo_dias',
                   data={'valor': '45', 'descripcion': 'Plazo ajustado en la prueba', 'save': 'Save'})
    assert r.status_code == 200, r.text[:500]
    with SesionLocal() as s:
        assert s.get(Parametros, 'cartera.plazo_saldo_dias').valor == 45
        registro = s.scalar(select(Auditoria).where(Auditoria.entidad == 'parametros',
                                                    Auditoria.usuario_id == p.id)
                            .order_by(Auditoria.id.desc()))
        # Se deja como estaba para no afectar otras pruebas
        s.get(Parametros, 'cartera.plazo_saldo_dias').valor = 30
        s.commit()
    assert registro is not None and registro.operacion == 'update'
    assert registro.antes['valor'] == 30 and registro.despues['valor'] == 45


def test_crear_una_tarifa_queda_auditada(panel):
    p = _usuario_real('administradora')
    _entrar(panel, p)
    with SesionLocal() as s:
        servicio_id = s.scalar(select(Servicios.id).where(Servicios.codigo == 'visa_canada'))
    r = panel.post('/admin/tarifas/create', data={
        'servicio': str(servicio_id), 'personas': '2', 'valor': '1100000', 'modalidad': 'total',
        'moneda': 'COP', 'vigente_desde': '2026-09-21', 'save': 'Save'})
    assert r.status_code == 200, r.text[:500]
    with SesionLocal() as s:
        tarifa = s.scalar(select(Tarifas).where(Tarifas.servicio_id == servicio_id, Tarifas.personas == 2))
        registro = s.scalar(select(Auditoria).where(Auditoria.entidad == 'tarifas',
                                                    Auditoria.entidad_id == tarifa.id))
    assert registro.operacion == 'insert' and registro.usuario_id == p.id
    assert Decimal(registro.despues['valor']) == Decimal('1100000')


def test_no_se_puede_borrar_un_catalogo(panel):
    _entrar(panel, _usuario_real('administradora'))
    with SesionLocal() as s:
        servicio_id = s.scalar(select(Servicios.id).where(Servicios.codigo == 'pasaporte'))
    r = panel.delete(f'/admin/servicios/delete?pks={servicio_id}')
    assert r.status_code in (403, 404, 405)
    with SesionLocal() as s:
        assert s.get(Servicios, servicio_id) is not None


def test_cambiar_la_contrasena_cierra_la_sesion_del_panel(panel):
    p = _usuario_real('administradora')
    _entrar(panel, p)
    assert panel.get('/admin/servicios/list').url.path == '/admin/servicios/list'
    with SesionLocal() as s:
        u = s.get(servicio_usuarios.Usuarios, p.id)
        servicio_auth.cambiar_password(s, u, p.password, 'OtraClave2026panel', None)
    assert panel.get('/admin/servicios/list').url.path == '/admin/login'


def test_las_veinte_vistas_abren_lista_creacion_y_edicion(panel):
    """Una vista mal configurada (un campo que el formulario no sabe dibujar, una
    relación rota) solo falla al abrirla. Se abren todas."""
    import re
    from app.admin import VISTAS
    _entrar(panel, _usuario_real('administradora'))
    fallas = []
    for vista in VISTAS:
        base = f'/admin/{vista.identity}'
        lista = panel.get(f'{base}/list')
        if lista.status_code != 200:
            fallas.append(f'{vista.identity} lista {lista.status_code}')
            continue
        if vista.can_create and panel.get(f'{base}/create').status_code != 200:
            fallas.append(f'{vista.identity} crear')
        primera = re.search(rf'{base}/edit/([^"\']+)', lista.text)
        if primera and panel.get(f'{base}/edit/{primera.group(1)}').status_code != 200:
            fallas.append(f'{vista.identity} editar')
    assert not fallas, fallas
