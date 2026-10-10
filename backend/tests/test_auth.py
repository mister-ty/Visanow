"""Actividad 2.1 — autenticación (RF-025 PDF, RNF-02)."""

import pytest
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
    assert r.status_code == 401, 'con la contraseña correcta no debe entrar: está bloqueada'
    assert db.scalar(select(Auditoria).where(Auditoria.entidad_id == p.u.id,
                                             Auditoria.operacion == 'bloqueo'))
    assert db.scalar(select(Auditoria).where(Auditoria.entidad_id == p.u.id,
                                             Auditoria.operacion == 'login_bloqueado'))


def test_el_bloqueo_no_revela_si_la_cuenta_existe(cliente, usuario):
    """Hallazgo de la revisión: el 423 delataba qué correos tienen cuenta,
    porque un correo inexistente nunca se bloquea."""
    p = usuario('comercial')
    for _ in range(6):
        bloqueada = cliente.post(LOGIN, json={'email': p.email, 'password': 'errada-123'})
        inexistente = cliente.post(LOGIN, json={'email': 'nadie@visanow.co', 'password': 'errada-123'})
    assert bloqueada.status_code == inexistente.status_code == 401
    assert bloqueada.json() == inexistente.json()


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
    assert r.status_code == 204
    p.password = 'NuevaClave2026'
    nueva = entrar(cliente, p)
    # Ya no la frena la contraseña: ahora la frena el permiso, que comercial no tiene
    r = cliente.get('/api/v1/usuarios', headers=nueva)
    assert r.status_code == 403 and r.json()['codigo'] == 'sin_permiso'


def test_cambiar_contrasena_cierra_las_demas_sesiones(cliente, usuario):
    p = usuario('comercial')
    vieja = entrar(cliente, p)
    r = cliente.post('/api/v1/auth/cambiar-password', headers=vieja,
                     json={'actual': p.password, 'nueva': 'OtraClave2026x'})
    assert r.status_code == 204 and r.content == b'', 'no debe devolver un token nuevo'
    r = cliente.get(YO, headers=vieja)
    assert r.status_code == 401 and r.json()['codigo'] == 'sesion_cerrada'
    p.password = 'OtraClave2026x'
    assert cliente.get(YO, headers=entrar(cliente, p)).status_code == 200


def test_cambiar_contrasena_cuenta_para_el_bloqueo(cliente, usuario):
    """Hallazgo de la revisión: con un token robado se podía adivinar la
    contraseña actual sin límite y renovar la sesión indefinidamente."""
    p = usuario('comercial')
    cab = entrar(cliente, p)
    for _ in range(5):
        r = cliente.post('/api/v1/auth/cambiar-password', headers=cab,
                         json={'actual': 'adivinando-1', 'nueva': 'Atacante2026x'})
        assert r.status_code == 422
    r = cliente.post('/api/v1/auth/cambiar-password', headers=cab,
                     json={'actual': p.password, 'nueva': 'Atacante2026x'})
    assert r.status_code == 423, 'tras 5 fallos ni la contraseña correcta debe servir'
    assert cliente.post(LOGIN, json={'email': p.email, 'password': p.password}).status_code == 401


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
    r = cliente.post('/api/v1/auth/mfa/confirmar', headers=cab, json={'codigo': totp.now()})
    assert r.status_code == 200 and 'access_token' in r.json()

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
    r = cliente.post('/api/v1/auth/mfa/confirmar', headers=cab,
                     json={'codigo': pyotp.TOTP(inicio['secreto']).now()})
    nueva = {'Authorization': f"Bearer {r.json()['access_token']}"}
    assert cliente.get('/api/v1/usuarios', headers=nueva).status_code == 200


def test_token_sin_doble_factor_muere_al_activarlo(cliente, usuario):
    """Hallazgo de la revisión: un token obtenido solo con contraseña quedaba
    con acceso pleno en cuanto la dueña activaba el doble factor."""
    p = usuario('finanzas', con_mfa=False)
    robado = entrar(cliente, p)
    legitimo = entrar(cliente, p)
    inicio = cliente.post('/api/v1/auth/mfa/iniciar', headers=legitimo).json()
    cliente.post('/api/v1/auth/mfa/confirmar', headers=legitimo,
                 json={'codigo': pyotp.TOTP(inicio['secreto']).now()})
    r = cliente.get(YO, headers=robado)
    assert r.status_code == 401 and r.json()['codigo'] == 'sesion_cerrada'


def test_solo_lectura_tambien_exige_doble_factor(cliente, usuario):
    """Hallazgo de la revisión: solo_lectura veía comisiones, gastos, usuarios y
    auditoría con la sola contraseña, mientras que finanzas necesitaba doble factor."""
    cab = entrar(cliente, usuario('solo_lectura', con_mfa=False))
    r = cliente.get('/api/v1/usuarios', headers=cab)
    assert r.status_code == 403 and r.json()['codigo'] == 'mfa_requerido'
    # Comercial y operaciones no ven nada sensible: no se les exige
    cab = entrar(cliente, usuario('comercial'))
    assert cliente.get(YO, headers=cab).json()['mfa_requerido'] is False


def test_recuperacion_sirve_una_sola_vez(cliente, usuario, monkeypatch, db):
    enviados = []
    monkeypatch.setattr(notificaciones, 'enviar_recuperacion',
                        lambda email, token, minutos: enviados.append(token))
    p = usuario('comercial')

    assert cliente.post('/api/v1/auth/recuperar', json={'email': 'nadie@visanow.co'}).status_code == 202
    assert enviados == []
    # Mismo INSERT y COMMIT que el caso real: el tiempo de respuesta no delata la cuenta
    assert db.scalar(select(Auditoria).where(Auditoria.operacion == 'recuperacion',
                                             Auditoria.usuario_id.is_(None)))
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


# ------------------------------------------- el correo de recuperacion (RNF-02)

class _ServidorFalso:
    """Un SMTP de mentira que guarda lo que le mandan, para poder mirarlo."""
    enviados: list = []
    arranques: list = []

    def __init__(self, host, puerto, timeout=None, context=None):
        self.host, self.puerto, self.contexto = host, puerto, context
        _ServidorFalso.arranques.append((host, puerto))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.tls = context

    def login(self, usuario, clave):
        self.usuario = usuario

    def send_message(self, mensaje):
        _ServidorFalso.enviados.append(mensaje)


@pytest.fixture
def smtp_falso(monkeypatch):
    from app.core.config import ajustes
    from app.services import notificaciones

    _ServidorFalso.enviados, _ServidorFalso.arranques = [], []
    monkeypatch.setattr(notificaciones.smtplib, 'SMTP', _ServidorFalso)
    monkeypatch.setattr(notificaciones.smtplib, 'SMTP_SSL', _ServidorFalso)

    a = ajustes()
    for campo, valor in (('smtp_host', 'correo.ejemplo.com'), ('smtp_desde', 'no-responder@visanow.co'),
                         ('smtp_usuario', 'no-responder@visanow.co'), ('smtp_password', 'xx'),
                         ('smtp_puerto', 587), ('smtp_tls', True), ('smtp_ssl', False)):
        monkeypatch.setattr(a, campo, valor)
    return _ServidorFalso


def test_pedir_recuperacion_manda_el_correo_con_el_enlace(cliente, db, usuario, smtp_falso):
    u = usuario('comercial')
    r = cliente.post('/api/v1/auth/recuperar', json={'email': u.u.email})
    assert r.status_code == 202, r.text

    assert len(smtp_falso.enviados) == 1, 'no salio ningun correo'
    m = smtp_falso.enviados[0]
    assert m['To'] == u.u.email
    cuerpo = m.get_content()
    assert '/restablecer?token=' in cuerpo, cuerpo
    assert 'no haga nada' in cuerpo, 'tiene que decir que hacer si no lo pidio'


def test_el_correo_dice_la_misma_vigencia_que_aplica_el_servicio(cliente, usuario, smtp_falso):
    """Dos numeros que pueden separarse es un correo que miente a los dos meses."""
    from app.services.auth import MINUTOS_TOKEN_RECUPERACION

    u = usuario('comercial')
    cliente.post('/api/v1/auth/recuperar', json={'email': u.u.email})
    cuerpo = smtp_falso.enviados[0].get_content()
    assert f'{MINUTOS_TOKEN_RECUPERACION} minutos' in cuerpo, cuerpo


def test_el_enlace_del_correo_sirve_de_verdad(cliente, db, usuario, smtp_falso):
    """Que salga el correo no basta: el enlace que lleva tiene que funcionar."""
    import re
    u = usuario('comercial')
    cliente.post('/api/v1/auth/recuperar', json={'email': u.u.email})
    token = re.search(r'token=([\w.\-]+)', smtp_falso.enviados[0].get_content()).group(1)

    r = cliente.post('/api/v1/auth/restablecer',
                     json={'token': token, 'nueva': 'Nueva-Clave-Larga-2026'})
    assert r.status_code == 204, r.text


def test_un_correo_que_no_existe_no_manda_nada_ni_se_delata(cliente, smtp_falso):
    r = cliente.post('/api/v1/auth/recuperar', json={'email': 'nadie@ejemplo.com'})
    assert r.status_code == 202, 'responde igual, para no decir quien tiene cuenta'
    assert smtp_falso.enviados == [], 'pero no manda nada'


def test_sin_proveedor_no_se_finge_que_se_envio(cliente, usuario, monkeypatch):
    """«Le enviamos un correo» cuando no se envio nada deja a la persona
    esperando algo que no va a llegar. Que quede el error en el log.

    Se engancha un manejador al logger en vez de usar caplog: la peticion pasa
    por el cliente de pruebas y caplog no la ve, asi que la prueba habria pasado
    por no encontrar nada, que es la peor forma de pasar.
    """
    import logging
    from app.core.config import ajustes
    from app.services import notificaciones

    monkeypatch.setattr(ajustes(), 'smtp_host', '')
    assert notificaciones.hay_proveedor() is False
    assert notificaciones.enviar('quien@ejemplo.com', 'Prueba', 'cuerpo') is False, (
        'sin proveedor tiene que decir que NO envio')

    registros = []

    class Espia(logging.Handler):
        def emit(self, r):
            registros.append(r.getMessage())

    espia = Espia(level=logging.ERROR)
    log = logging.getLogger('visanow.notificaciones')
    log.addHandler(espia)
    try:
        u = usuario('comercial')
        r = cliente.post('/api/v1/auth/recuperar', json={'email': u.u.email})
    finally:
        log.removeHandler(espia)

    assert r.status_code == 202, 'la respuesta no cambia: delataria quien tiene cuenta'
    assert any('No hay proveedor de correo' in m for m in registros), registros
    assert any('restablecer la contrasena' in m or 'restablecer la contraseña' in m
               for m in registros), 'y tiene que decir cual es la salida mientras tanto'


def test_si_el_correo_falla_la_peticion_no_se_cae(cliente, usuario, monkeypatch):
    """Que el proveedor este caido no puede tumbar la operacion que lo pidio."""
    from app.core.config import ajustes
    from app.services import notificaciones

    for campo, valor in (('smtp_host', 'correo.ejemplo.com'), ('smtp_desde', 'x@visanow.co')):
        monkeypatch.setattr(ajustes(), campo, valor)

    def revienta(*a, **k):
        raise OSError('el servidor de correo no contesta')
    monkeypatch.setattr(notificaciones.smtplib, 'SMTP', revienta)

    u = usuario('comercial')
    assert cliente.post('/api/v1/auth/recuperar', json={'email': u.u.email}).status_code == 202


def test_el_certificado_se_valida(smtp_falso):
    """Mandar la contraseña del buzón por un canal sin validar el certificado es
    entregársela a quien se ponga en el medio."""
    from app.services import notificaciones
    assert notificaciones.enviar('quien@ejemplo.com', 'Prueba', 'cuerpo') is True
    import ssl
    enviado = smtp_falso.enviados[0]
    assert enviado['From'] == 'no-responder@visanow.co'
    # El contexto que se usa para STARTTLS valida nombre y cadena.
    ctx = notificaciones.ssl.create_default_context()
    assert ctx.check_hostname is True and ctx.verify_mode is ssl.CERT_REQUIRED
