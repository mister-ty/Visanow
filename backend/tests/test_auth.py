"""Actividad 2.1 — autenticación (RF-025 PDF, RNF-02)."""
import pyotp
from sqlalchemy import select, text

from app.core import seguridad as seg
from app.models.esquema import Auditoria, Usuarios
from app.services import notificaciones
from tests.conftest import entrar

LOGIN = '/api/v1/auth/login'
YO = '/api/v1/auth/yo'


def test_ingreso_correcto_devuelve_token_y_perfil(cliente, usuario):
    p = usuario('operaciones')
    cab = entrar(cliente, p)
    r = cliente.get(YO, headers=cab)
    assert r.status_code == 200
    yo = r.json()
    assert yo['rol'] == 'operaciones'
    assert 'casos.editar' in yo['permisos']
    assert 'pagos.editar' not in yo['permisos']


def test_no_revela_si_el_correo_existe(cliente, usuario):
    p = usuario('comercial')
    errada = cliente.post(LOGIN, json={'email': p.email, 'password': 'no-es-esta-1'})
    inexistente = cliente.post(LOGIN, json={'email': 'nadie@visanow.co', 'password': 'no-es-esta-1'})
    assert errada.status_code == inexistente.status_code == 401
    assert errada.json() == inexistente.json()


def test_usuario_inactivo_no_entra(cliente, usuario, db):
    p = usuario('comercial')
    p.u.activo = False
    db.commit()
    r = cliente.post(LOGIN, json={'email': p.email, 'password': p.password})
    assert r.status_code == 401


def test_cinco_intentos_bloquean_aunque_despues_acierte(cliente, usuario, db):
    p = usuario('comercial')
    for _ in range(5):
        cliente.post(LOGIN, json={'email': p.email, 'password': 'errada-123'})
    r = cliente.post(LOGIN, json={'email': p.email, 'password': p.password})
    assert r.status_code == 423
    assert r.json()['codigo'] == 'cuenta_bloqueada'
    assert db.scalar(select(Auditoria).where(Auditoria.entidad_id == p.u.id,
                                             Auditoria.operacion == 'bloqueo'))


def test_sin_token_con_token_alterado_o_de_otro_tipo(cliente, usuario):
    p = usuario('comercial')
    token = entrar(cliente, p)['Authorization'].split()[1]
    assert cliente.get(YO).status_code == 401
    alterado = token[:-4] + ('AAAA' if not token.endswith('AAAA') else 'BBBB')
    assert cliente.get(YO, headers={'Authorization': f'Bearer {alterado}'}).status_code == 401
    token_mfa = seg.crear_token(p.u.id, 'mfa', 5)
    assert cliente.get(YO, headers={'Authorization': f'Bearer {token_mfa}'}).status_code == 401


def test_contrasena_temporal_obliga_a_cambiarla(cliente, usuario):
    p = usuario('comercial', listo=False)
    cab = entrar(cliente, p)
    r = cliente.get('/api/v1/usuarios', headers=cab)
    assert r.status_code == 403 and r.json()['codigo'] == 'cambio_password_requerido'

    r = cliente.post('/api/v1/auth/cambiar-password', headers=cab,
                     json={'actual': p.password, 'nueva': 'NuevaClave2026'})
    assert r.status_code == 200
    nueva = {'Authorization': f"Bearer {r.json()['access_token']}"}
    # Ya no la frena la contraseña: ahora la frena el permiso, que comercial no tiene
    r = cliente.get('/api/v1/usuarios', headers=nueva)
    assert r.status_code == 403 and r.json()['codigo'] == 'sin_permiso'


def test_cambiar_contrasena_cierra_las_demas_sesiones(cliente, usuario):
    p = usuario('comercial')
    vieja = entrar(cliente, p)
    r = cliente.post('/api/v1/auth/cambiar-password', headers=vieja,
                     json={'actual': p.password, 'nueva': 'OtraClave2026x'})
    nueva = {'Authorization': f"Bearer {r.json()['access_token']}"}
    r = cliente.get(YO, headers=vieja)
    assert r.status_code == 401 and r.json()['codigo'] == 'sesion_cerrada'
    assert cliente.get(YO, headers=nueva).status_code == 200


def test_politica_de_contrasena(cliente, usuario):
    p = usuario('comercial')
    cab = entrar(cliente, p)
    r = cliente.post('/api/v1/auth/cambiar-password', headers=cab,
                     json={'actual': p.password, 'nueva': 'corta'})
    assert r.status_code == 422 and r.json()['codigo'] == 'password_debil'


def test_activar_doble_factor_y_entrar_con_el(cliente, usuario, db):
    p = usuario('comercial')
    cab = entrar(cliente, p)
    inicio = cliente.post('/api/v1/auth/mfa/iniciar', headers=cab).json()
    assert inicio['uri'].startswith('otpauth://totp/')

    # El secreto se guarda cifrado, nunca en claro
    db.refresh(p.u)
    assert p.u.mfa_secreto != inicio['secreto']
    assert seg.descifrar(p.u.mfa_secreto) == inicio['secreto']

    totp = pyotp.TOTP(inicio['secreto'])
    assert cliente.post('/api/v1/auth/mfa/confirmar', headers=cab,
                        json={'codigo': totp.now()}).status_code == 204

    desafio = cliente.post(LOGIN, json={'email': p.email, 'password': p.password}).json()
    assert desafio['requiere_mfa'] is True and 'access_token' not in desafio
    errado = str((int(totp.now()) + 1) % 1_000_000).zfill(6)
    r = cliente.post('/api/v1/auth/mfa/verificar', json={'token_mfa': desafio['token_mfa'], 'codigo': errado})
    assert r.status_code == 401
    r = cliente.post('/api/v1/auth/mfa/verificar', json={'token_mfa': desafio['token_mfa'], 'codigo': totp.now()})
    assert r.status_code == 200 and 'access_token' in r.json()


def test_perfiles_sensibles_no_operan_sin_doble_factor(cliente, usuario):
    """RNF-02: administradora y finanzas no hacen nada hasta activar el doble factor."""
    p = usuario('administradora', con_mfa=False)
    cab = entrar(cliente, p)
    r = cliente.get('/api/v1/usuarios', headers=cab)
    assert r.status_code == 403 and r.json()['codigo'] == 'mfa_requerido'
    yo = cliente.get(YO, headers=cab).json()
    assert yo['mfa_requerido'] is True

    inicio = cliente.post('/api/v1/auth/mfa/iniciar', headers=cab).json()
    cliente.post('/api/v1/auth/mfa/confirmar', headers=cab,
                 json={'codigo': pyotp.TOTP(inicio['secreto']).now()})
    assert cliente.get('/api/v1/usuarios', headers=cab).status_code == 200


def test_recuperacion_sirve_una_sola_vez(cliente, usuario, monkeypatch):
    enviados = []
    monkeypatch.setattr(notificaciones, 'enviar_recuperacion', lambda email, token: enviados.append(token))
    p = usuario('comercial')

    assert cliente.post('/api/v1/auth/recuperar', json={'email': 'nadie@visanow.co'}).status_code == 202
    assert enviados == []
    assert cliente.post('/api/v1/auth/recuperar', json={'email': p.email}).status_code == 202
    assert len(enviados) == 1

    datos = {'token': enviados[0], 'nueva': 'Recuperada2026'}
    assert cliente.post('/api/v1/auth/restablecer', json=datos).status_code == 204
    assert cliente.post('/api/v1/auth/restablecer', json={**datos, 'nueva': 'OtraVez2026x'}).status_code == 422
    r = cliente.post(LOGIN, json={'email': p.email, 'password': 'Recuperada2026'})
    assert r.status_code == 200


def test_el_ingreso_queda_auditado_sin_secretos(cliente, usuario, db):
    p = usuario('comercial')
    entrar(cliente, p)
    registro = db.scalar(select(Auditoria).where(Auditoria.entidad_id == p.u.id,
                                                 Auditoria.operacion == 'login'))
    assert registro is not None
    creacion = db.scalar(select(Auditoria).where(Auditoria.entidad_id == p.u.id,
                                                 Auditoria.operacion == 'insert'))
    assert 'password_hash' not in (creacion.despues or {})
    assert 'mfa_secreto' not in (creacion.despues or {})


def test_la_auditoria_es_inalterable(db, usuario):
    """RNF-05: ni la propia aplicación puede modificar o borrar la auditoría."""
    usuario('comercial')
    for sentencia in ("update auditoria set operacion = 'manipulada'", 'delete from auditoria'):
        try:
            with db.begin_nested():
                db.execute(text(sentencia))
            raise AssertionError(f'Se permitió: {sentencia}')
        except Exception as e:
            assert 'inalterable' in str(e)
