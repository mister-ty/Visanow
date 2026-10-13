"""Actividad 2.1 — roles y permisos (RNF-03) y criterio de aceptación 9."""
import pytest
from sqlalchemy import select, text

from app import seed
from app.core.deps import requiere
from app.core.errores import Conflicto, Prohibido
from app.models.esquema import Roles
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
    assert all(p.endswith('.ver') for p in roles['solo_lectura'])
    # Saltarse el orden de los estados de un trámite lo autoriza solo la
    # administradora, aunque operaciones tenga todo lo demás sobre casos
    assert {r for r, p in roles.items() if 'casos.excepcion' in p} == {'administradora'}
    assert 'casos.eliminar' in roles['operaciones'] and 'casos.excepcion' not in roles['operaciones']
    assert roles['administradora'] >= set().union(*roles.values()) - {'x'}


def test_operaciones_no_ve_la_contabilidad(cliente, usuario):
    """Respuesta de la administradora del 29/09: al del control de la operación
    «no hay que ocultarle nada, solo lo de la contabilidad». Pero sin saber si
    el cliente pagó el anticipo no puede arrancar el trámite, y para eso está
    pagos.estado, que no muestra montos."""
    cab = entrar(cliente, usuario('administradora'))
    roles = {r['codigo']: set(r['permisos']) for r in cliente.get('/api/v1/roles', headers=cab).json()}

    contabilidad = {'pagos.ver', 'gastos.ver', 'comisiones.ver', 'ajustes.ver'}
    assert not (roles['operaciones'] & contabilidad), 'operaciones no debe ver la contabilidad'
    assert 'pagos.estado' in roles['operaciones'], 'sí debe saber si el cliente está al día'
    assert 'casos.editar' in roles['operaciones'], 'lo demás sigue igual'
    # Quien cobra sí necesita los montos
    assert 'pagos.ver' in roles['comercial'] and 'pagos.ver' in roles['finanzas']


# ------------------------- la matriz de permisos se configura, no solo se mira

def _rol(cliente, cab, codigo: str) -> dict:
    roles = {r['codigo']: r for r in cliente.get('/api/v1/roles', headers=cab).json()}
    return roles[codigo]


def _conceder(db, rol: str, *codigos: str) -> None:
    """Deja un estado de partida que la administradora pudo haber configurado."""
    db.execute(text("""insert into roles_permisos (rol_id, permiso_id)
                       select r.id, p.id from roles r, permisos p
                        where r.codigo = :rol and p.codigo = any(:codigos)
                       on conflict do nothing"""), {'rol': rol, 'codigos': list(codigos)})
    db.commit()


def test_solo_la_administradora_nace_con_la_llave_de_los_permisos(cliente, usuario):
    """Quien reescribe la matriz puede darse cualquier permiso del sistema. Eso
    arranca en un solo rol; prestarlo es una decisión, no el estado inicial."""
    cab = entrar(cliente, usuario('administradora'))
    roles = {r['codigo']: set(r['permisos'])
             for r in cliente.get('/api/v1/roles', headers=cab).json()}
    assert {r for r, p in roles.items() if 'usuarios.permisos' in p} == {'administradora'}
    assert 'usuarios.ver' in roles['solo_lectura'], 'mirar la matriz no es poder cambiarla'


def test_el_catalogo_de_permisos_se_puede_consultar_para_escogerlos(cliente, usuario):
    """Sin catálogo hay que acordarse de memoria de los códigos, y un código mal
    escrito es un permiso que nadie recibe y que nadie nota hasta que estorba."""
    cab = entrar(cliente, usuario('administradora'))
    r = cliente.get('/api/v1/permisos', headers=cab)
    assert r.status_code == 200, r.text
    catalogo = {p['codigo']: p for p in r.json()}
    assert len(catalogo) > 70, catalogo
    assert 'casos.ver' in catalogo
    assert catalogo['usuarios.permisos']['modulo'] == 'usuarios', 'se agrupa por módulo'
    assert all(p['nombre'] for p in catalogo.values()), 'cada casilla necesita su nombre'


def test_la_administradora_cambia_lo_que_puede_hacer_un_rol(cliente, usuario):
    """RF-077 pide «gestionar permisos». Mientras la matriz solo se consulte,
    mover un permiso exige editar código Python y volver a desplegar."""
    cab = entrar(cliente, usuario('administradora'))
    rol = _rol(cliente, cab, 'comercial')
    assert 'pagos.ver' in rol['permisos']
    quedan = sorted((set(rol['permisos']) - {'pagos.ver'}) | {'casos.editar'})

    r = cliente.put(f"/api/v1/roles/{rol['id']}/permisos", headers=cab,
                    json={'permisos': quedan})
    assert r.status_code == 200, r.text
    assert r.json()['permisos'] == quedan
    assert set(_rol(cliente, cab, 'comercial')['permisos']) == set(quedan), 'quedó guardado'


def test_quitarle_un_permiso_a_un_rol_se_lo_quita_ya_a_quien_lo_tenga(cliente, usuario):
    """Los permisos se consultan en cada solicitud y no viajan en el token: el
    cambio alcanza a quien esté con la pantalla abierta, sin volver a entrar.
    Por eso es un cambio que hay que pensar antes de guardarlo."""
    cab = entrar(cliente, usuario('administradora'))
    p = usuario('comercial')
    suyo = entrar(cliente, p)
    assert cliente.get('/api/v1/casos', headers=suyo).status_code == 200

    rol = _rol(cliente, cab, 'comercial')
    r = cliente.put(f"/api/v1/roles/{rol['id']}/permisos", headers=cab,
                    json={'permisos': [c for c in rol['permisos'] if c != 'casos.ver']})
    assert r.status_code == 200, r.text

    assert 'casos.ver' not in cliente.get('/api/v1/auth/yo', headers=suyo).json()['permisos']
    assert cliente.get('/api/v1/casos', headers=suyo).status_code == 403


def test_nadie_se_puede_quitar_a_si_misma_la_llave_de_los_permisos(cliente, usuario):
    """Si se la quita no le queda forma de devolvérsela: la instalación se
    arregla entrando a la base de datos por fuera del sistema."""
    cab = entrar(cliente, usuario('administradora'))
    rol = _rol(cliente, cab, 'administradora')
    assert 'usuarios.permisos' in rol['permisos']

    r = cliente.put(f"/api/v1/roles/{rol['id']}/permisos", headers=cab,
                    json={'permisos': [c for c in rol['permisos'] if c != 'usuarios.permisos']})
    assert r.status_code == 403, r.text
    assert r.json()['codigo'] == 'autoedicion'
    assert 'usuarios.permisos' in _rol(cliente, cab, 'administradora')['permisos'], 'nada cambió'


def test_otro_rol_con_la_llave_no_puede_cerrarle_la_puerta_a_la_administradora(
        cliente, usuario, db):
    """La llave se puede prestar. El rol administradora es la última puerta:
    quien la recibió prestada no puede usarla para dejar afuera a quien se la dio."""
    _conceder(db, 'finanzas', 'usuarios.permisos')
    prestada = entrar(cliente, usuario('finanzas'))
    admin = entrar(cliente, usuario('administradora'))
    rol = _rol(cliente, admin, 'administradora')

    r = cliente.put(f"/api/v1/roles/{rol['id']}/permisos", headers=prestada,
                    json={'permisos': ['casos.ver']})
    assert r.status_code == 403, r.text
    assert r.json()['codigo'] == 'requiere_admin'
    assert 'usuarios.permisos' in _rol(cliente, admin, 'administradora')['permisos']


def test_el_servicio_no_deja_la_instalacion_sin_nadie_que_gestione_permisos(db, usuario):
    """Defensa en profundidad: la ruta ya lo impide por otros dos caminos, pero
    el servicio no puede ser el que apague la última luz. Punto de partida: la
    llave se le prestó a finanzas y el rol administradora ya no la tiene."""
    _conceder(db, 'finanzas', 'usuarios.permisos')
    db.execute(text("""delete from roles_permisos
          where rol_id = (select id from roles where codigo = 'administradora')
            and permiso_id = (select id from permisos where codigo = 'usuarios.permisos')"""))
    db.commit()
    actor = usuario('administradora').u
    finanzas = db.scalar(select(Roles.id).where(Roles.codigo == 'finanzas'))
    sin_la_llave = sorted(servicio.permisos_de_rol(db, finanzas) - {'usuarios.permisos'})

    with pytest.raises(Conflicto) as e:
        servicio.fijar_permisos(db, actor, finanzas, sin_la_llave)
    assert e.value.codigo == 'ultimo_gestor_permisos'
    assert 'usuarios.permisos' in servicio.permisos_de_rol(db, finanzas), 'no se guardó nada'


def test_usuarios_editar_no_alcanza_para_reescribir_la_matriz(cliente, usuario, db):
    """Cambiarle el perfil a una persona es escoger entre los que ya existen;
    redefinir el perfil es poder darse cualquier permiso. No es la misma
    facultad, y el día que dar de alta cuentas se delegue, esta no se va con ella."""
    _conceder(db, 'finanzas', 'usuarios.ver', 'usuarios.crear', 'usuarios.editar')
    cab = entrar(cliente, usuario('finanzas'))
    otra = usuario('comercial').u
    assert cliente.patch(f'/api/v1/usuarios/{otra.id}', headers=cab,
                         json={'nombre': 'Nombre nuevo'}).status_code == 200, 'sí gestiona cuentas'

    rol = _rol(cliente, cab, 'comercial')
    r = cliente.put(f"/api/v1/roles/{rol['id']}/permisos", headers=cab,
                    json={'permisos': ['casos.ver']})
    assert r.status_code == 403, r.text
    assert r.json()['codigo'] == 'sin_permiso'


def test_quien_puede_reescribir_la_matriz_necesita_doble_factor(db, usuario):
    """Con la llave maestra se llega a cualquier otro permiso: pedir solo la
    contraseña para usarla sería dejar la puerta de atrás abierta (RNF-02)."""
    p = usuario('apoyo_externo', con_mfa=False)
    assert servicio.exige_mfa(db, p.u) is False, 'hoy no le hace falta'
    _conceder(db, 'apoyo_externo', 'usuarios.permisos')
    assert servicio.exige_mfa(db, p.u) is True


def test_un_permiso_que_no_existe_se_rechaza_diciendo_cual(cliente, usuario):
    """Un código mal escrito no puede quedar guardado como si no fuera nada: el
    rol se quedaría sin el permiso que la administradora creyó haberle dado."""
    cab = entrar(cliente, usuario('administradora'))
    rol = _rol(cliente, cab, 'comercial')
    r = cliente.put(f"/api/v1/roles/{rol['id']}/permisos", headers=cab,
                    json={'permisos': ['casos.ver', 'casos.borrar']})
    assert r.status_code == 422, r.text
    assert r.json()['codigo'] == 'permiso_inexistente'
    assert 'casos.borrar' in r.json()['detalle'], 'tiene que decir cuál para poder corregirlo'


def test_un_rol_que_no_existe_se_rechaza_con_el_error_del_dominio(cliente, usuario):
    cab = entrar(cliente, usuario('administradora'))
    r = cliente.put('/api/v1/roles/9999/permisos', headers=cab, json={'permisos': []})
    assert r.status_code == 404, r.text
    assert r.json()['codigo'] == 'noencontrado', 'el 404 lo da el servicio, no la ruta ausente'


def test_el_cambio_de_permisos_queda_en_auditoria_con_el_antes_y_el_despues(
        cliente, usuario, db):
    """Quitarle un permiso a un rol afecta de inmediato a todo el que lo tenga.
    El día que alguien pregunte «¿por qué ya no puedo?», la respuesta tiene que
    estar escrita y no haber que reconstruirla."""
    cab = entrar(cliente, usuario('administradora'))
    rol = _rol(cliente, cab, 'solo_lectura')
    r = cliente.put(f"/api/v1/roles/{rol['id']}/permisos", headers=cab,
                    json={'permisos': [c for c in rol['permisos'] if c != 'pagos.ver']})
    assert r.status_code == 200, r.text

    fila = db.execute(text("""select antes, despues from auditoria
                               where entidad = 'roles_permisos' and entidad_id = :rol
                               order by id desc limit 1"""), {'rol': rol['id']}).first()
    assert fila is not None, 'sin auditoría nadie puede responder por el cambio'
    antes, despues = fila
    assert 'pagos.ver' in antes['permisos'], 'lo que el rol podía hacer antes'
    assert 'pagos.ver' not in despues['permisos'], 'y lo que puede hacer ahora'
    assert despues['quitados'] == ['pagos.ver'], 'el resumen, para no comparar a ojo'
    assert despues['agregados'] == []


def test_guardar_la_misma_matriz_no_ensucia_la_auditoria(cliente, usuario, db):
    """Abrir la pantalla y guardar sin tocar nada no es un cambio: si cada
    guardado dejara un registro, lo que importa se perdería entre el ruido."""
    cab = entrar(cliente, usuario('administradora'))
    rol = _rol(cliente, cab, 'comercial')
    r = cliente.put(f"/api/v1/roles/{rol['id']}/permisos", headers=cab,
                    json={'permisos': rol['permisos']})
    assert r.status_code == 200, r.text
    assert db.scalar(text("""select count(*) from auditoria
                              where entidad = 'roles_permisos' and entidad_id = :rol"""),
                     {'rol': rol['id']}) == 0


# ----------------- el despliegue no le deshace a la administradora lo que hizo

def _cursor(db):
    """Un cursor psycopg sobre la MISMA transacción de la prueba: así el seed ve
    lo que se acaba de configurar y todo se deshace al terminar la prueba."""
    return db.connection().connection.cursor()


def test_el_proximo_despliegue_no_pisa_la_matriz_que_configuro_la_administradora(db):
    """El seed corre en cada despliegue (paso 6 de la guía). Si vuelve a
    repartir la matriz de seed.py, le deshace lo que decidió: le devuelve al rol
    el permiso que le quitó, y a la semana nadie entiende por qué el comercial
    volvió a ver los pagos."""
    cur = _cursor(db)
    cur.execute("""delete from roles_permisos
          where rol_id = (select id from roles where codigo = 'comercial')
            and permiso_id = (select id from permisos where codigo = 'pagos.ver')""")
    cur.execute("""insert into roles_permisos (rol_id, permiso_id)
                   select r.id, p.id from roles r, permisos p
                    where r.codigo = 'comercial' and p.codigo = 'casos.editar'""")

    seed.sembrar_matriz(cur, set())

    comercial = db.scalar(select(Roles.id).where(Roles.codigo == 'comercial'))
    quedaron = servicio.permisos_de_rol(db, comercial)
    assert 'pagos.ver' not in quedaron, 'el despliegue le devolvió lo que se le quitó'
    assert 'casos.editar' in quedaron, 'el despliegue le borró lo que se le dio'


def test_un_permiso_nuevo_del_sistema_le_llega_a_la_administradora(db):
    """Si el seed ya no reparte la matriz, lo que trae una versión nueva tiene
    que llegarle al rol que los tiene todos: una función nueva no puede nacer
    sin nadie que la pueda usar. A los demás los reparte la administradora."""
    cur = _cursor(db)
    cur.execute("""insert into permisos (codigo, nombre, modulo)
                   values ('informes.ver', 'Ver informes', 'informes')""")

    seed.sembrar_matriz(cur, {'informes.ver'})

    cur.execute("""select r.codigo from roles r
                     join roles_permisos rp on rp.rol_id = r.id
                     join permisos p on p.id = rp.permiso_id
                    where p.codigo = 'informes.ver'""")
    assert [c for (c,) in cur.fetchall()] == ['administradora']
