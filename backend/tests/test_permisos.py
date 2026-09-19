"""Actividad 2.1 — roles y permisos (RNF-03) y criterio de aceptación 9."""
import pytest

from app.core.deps import requiere
from app.core.errores import Prohibido
from app.services import usuarios as servicio
from tests.conftest import entrar


def test_criterio_aceptacion_9_operaciones_no_edita_comisiones_ni_pagos(db, usuario):
    """Criterio 9: «Un usuario de operaciones no puede editar reglas de comisión
    ni valores conciliados». Se verifica sobre la misma dependencia que protege
    los endpoints, no sobre la lista de permisos."""
    operaciones = usuario('operaciones').u
    finanzas = usuario('finanzas').u
    for permiso in ('comisiones.editar', 'pagos.editar', 'ajustes.editar'):
        with pytest.raises(Prohibido):
            requiere(permiso)(operaciones, db)
        assert requiere(permiso)(finanzas, db) is finanzas


def test_quien_no_tiene_permiso_recibe_403(cliente, usuario):
    cab = entrar(cliente, usuario('operaciones'))
    r = cliente.get('/api/v1/usuarios', headers=cab)
    assert r.status_code == 403 and r.json()['codigo'] == 'sin_permiso'


def test_administradora_crea_usuario_con_contrasena_temporal(cliente, usuario):
    cab = entrar(cliente, usuario('administradora'))
    r = cliente.post('/api/v1/usuarios', headers=cab,
                     json={'nombre': 'Laura Gómez', 'email': 'laura@visanow.co', 'rol': 'comercial'})
    assert r.status_code == 201
    creado = r.json()
    assert creado['usuario']['debe_cambiar_password'] is True
    assert len(creado['password_temporal']) >= 10

    duplicado = cliente.post('/api/v1/usuarios', headers=cab,
                             json={'nombre': 'Otra', 'email': 'LAURA@visanow.co', 'rol': 'comercial'})
    assert duplicado.status_code == 409
    rol_malo = cliente.post('/api/v1/usuarios', headers=cab,
                            json={'nombre': 'Otra', 'email': 'otra@visanow.co', 'rol': 'gerente'})
    assert rol_malo.status_code == 422


def test_cambiar_rol_surte_efecto_de_inmediato(cliente, usuario):
    admin = entrar(cliente, usuario('administradora'))
    p = usuario('comercial')
    cab = entrar(cliente, p)
    assert 'pagos.editar' not in cliente.get('/api/v1/auth/yo', headers=cab).json()['permisos']
    cliente.patch(f'/api/v1/usuarios/{p.u.id}', headers=admin, json={'rol': 'finanzas'})
    # Mismo token: los permisos se leen en cada solicitud, no viajan en el token
    assert 'pagos.editar' in cliente.get('/api/v1/auth/yo', headers=cab).json()['permisos']


def test_desactivar_cierra_el_acceso(cliente, usuario):
    admin = entrar(cliente, usuario('administradora'))
    p = usuario('comercial')
    cab = entrar(cliente, p)
    cliente.patch(f'/api/v1/usuarios/{p.u.id}', headers=admin, json={'activo': False})
    assert cliente.get('/api/v1/auth/yo', headers=cab).status_code == 401


def test_la_administradora_no_puede_desactivarse_a_si_misma(cliente, usuario):
    p = usuario('administradora')
    cab = entrar(cliente, p)
    r = cliente.patch(f'/api/v1/usuarios/{p.u.id}', headers=cab, json={'activo': False})
    assert r.status_code == 403 and r.json()['codigo'] == 'autoedicion'


def test_restablecer_contrasena_cierra_sesiones_y_obliga_a_cambiarla(cliente, usuario):
    admin = entrar(cliente, usuario('administradora'))
    p = usuario('comercial')
    vieja = entrar(cliente, p)
    r = cliente.post(f'/api/v1/usuarios/{p.u.id}/restablecer-password', headers=admin)
    temporal = r.json()['password_temporal']
    assert cliente.get('/api/v1/auth/yo', headers=vieja).status_code == 401
    p.password = temporal
    yo = cliente.get('/api/v1/auth/yo', headers=entrar(cliente, p)).json()
    assert yo['debe_cambiar_password'] is True


def test_solo_una_administradora_gestiona_administradoras(db, usuario):
    """Defensa en profundidad: aunque otro rol recibiera permisos sobre usuarios,
    no podría tomar el control de una cuenta de administradora."""
    comercial = usuario('comercial').u
    admin = usuario('administradora').u
    with pytest.raises(Prohibido):
        servicio.restablecer_password(db, comercial, admin.id)
    with pytest.raises(Prohibido):
        servicio.editar(db, comercial, comercial.id, rol='administradora')
    with pytest.raises(Prohibido):
        servicio.crear(db, comercial, nombre='Intrusa', email='x@visanow.co', rol='administradora')


def test_reiniciar_doble_factor_tambien_reinicia_la_contrasena(cliente, usuario):
    """Hallazgo de la revisión: al quitar solo el doble factor, quien tuviera la
    contraseña por phishing podía entrar en ese intervalo y activar su propio teléfono."""
    admin = entrar(cliente, usuario('administradora'))
    p = usuario('finanzas')
    vieja = entrar(cliente, p)
    r = cliente.post(f'/api/v1/usuarios/{p.u.id}/reiniciar-mfa', headers=admin)
    assert r.status_code == 200 and r.json()['usuario']['mfa_habilitado'] is False
    assert cliente.get('/api/v1/auth/yo', headers=vieja).status_code == 401
    # La contraseña conocida (la que pudo robarse) ya no sirve
    assert cliente.post('/api/v1/auth/login',
                        json={'email': p.email, 'password': p.password}).status_code == 401


def test_crear_admin_rechaza_un_correo_que_el_login_no_aceptaria(monkeypatch):
    """Hallazgo de la revisión: crear_admin aceptaba correos que la API rechaza,
    y quedaba una administradora activa que nunca podía ingresar."""
    import sys
    from app import crear_admin
    monkeypatch.setattr(sys, 'argv', ['crear_admin', '--nombre', 'X', '--email', 'admin@visanow.local'])
    with pytest.raises(SystemExit) as e:
        crear_admin.main()
    assert 'Correo inválido' in str(e.value)


def test_matriz_de_roles(cliente, usuario):
    cab = entrar(cliente, usuario('administradora'))
    roles = {r['codigo']: set(r['permisos']) for r in cliente.get('/api/v1/roles', headers=cab).json()}
    assert set(roles) == {'administradora', 'comercial', 'operaciones', 'finanzas',
                          'apoyo_externo', 'solo_lectura'}
    assert len(roles['administradora']) == 75
    assert all(p.endswith('.ver') for p in roles['solo_lectura'])
