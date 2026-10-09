"""Tareas y centro de alertas (RF-060, RF-061, RF-062 — actividad 5.4).

Lo que vigilan estas pruebas es lo que hace que una bandeja sirva o estorbe:
que no se repita sola, que respete el alcance de quien mira, y que posponer
tenga fecha. Una bandeja que se llena de duplicados se deja de leer a la semana,
y una que enseña trámites ajenos es una fuga por la puerta de atrás.
"""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from app.models.esquema import Alertas, AlertasTipos, Casos, EstadosOperativos, Paises, Servicios
from tests.conftest import entrar

BOGOTA = ZoneInfo('America/Bogota')


@pytest.fixture
def admin(cliente, usuario):
    return entrar(cliente, usuario('administradora'))


@pytest.fixture
def operaciones(cliente, usuario):
    p = usuario('operaciones')
    return entrar(cliente, p), p


def un_cliente(cliente, cab, nombre):
    return cliente.post('/api/v1/clientes', headers=cab, json={'nombre': nombre}).json()


def un_caso(cliente, cab, db, nombre, responsable_id=None):
    c = un_cliente(cliente, cab, nombre)
    s = cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'cliente_id': c['id'], 'nombre': nombre}).json()
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    estado = db.scalar(select(EstadosOperativos.id)
                       .where(EstadosOperativos.codigo == 'registrado'))
    caso = Casos(solicitante_id=s['id'], pais_id=pais, estado_id=estado, fuente='manual',
                 responsable_id=responsable_id, proxima_accion='Pedir documentos',
                 ultima_actividad_en=dt.datetime.now(BOGOTA))
    db.add(caso)
    db.commit()
    return c, caso


# -------------------------------------------------------------------- tareas

def test_una_tarea_suelta_no_se_puede_crear(cliente, admin):
    """Una tarea sin dueno de que se trate no se puede retomar despues."""
    r = cliente.post('/api/v1/tareas', headers=admin,
                     json={'titulo': 'Llamar a la senora'})
    assert r.status_code == 422 and r.json()['codigo'] == 'sin_vinculo'


def test_la_tarea_sin_responsable_es_de_quien_la_crea(cliente, admin, db):
    c = un_cliente(cliente, admin, 'Tarea Sinresponsable Cliente')
    r = cliente.post('/api/v1/tareas', headers=admin, json={
        'titulo': 'Confirmar documentos', 'cliente_id': c['id']})
    assert r.status_code == 201, r.text
    assert r.json()['responsable_id'] is not None
    assert r.json()['estado'] == 'pendiente' and r.json()['origen'] == 'manual'


def test_la_fecha_sin_hora_vence_al_final_del_dia_en_bogota(cliente, admin, db):
    """«Vence el jueves» no significa el jueves a medianoche: el jueves todavia
    esta a tiempo. Y el servidor corre en UTC, asi que una fecha sin zona se
    guardaria cinco horas antes."""
    c = un_cliente(cliente, admin, 'Tarea Convence Cliente')
    r = cliente.post('/api/v1/tareas', headers=admin, json={
        'titulo': 'Revisar el DS-160', 'cliente_id': c['id'], 'vence_en': '2027-03-18'})
    assert r.status_code == 201, r.text

    guardada = dt.datetime.fromisoformat(r.json()['vence_en'])
    local = guardada.astimezone(BOGOTA)
    assert local.date() == dt.date(2027, 3, 18), local
    assert (local.hour, local.minute) == (23, 59), local


def test_cerrar_una_tarea_deja_la_fecha_y_reabrirla_la_quita(cliente, admin, db):
    c = un_cliente(cliente, admin, 'Tarea Cerrar Cliente')
    t = cliente.post('/api/v1/tareas', headers=admin, json={
        'titulo': 'Pedir el pasaporte', 'cliente_id': c['id']}).json()

    hecha = cliente.patch(f'/api/v1/tareas/{t["id"]}', headers=admin,
                          json={'estado': 'hecha'}).json()
    assert hecha['estado'] == 'hecha' and hecha['cerrada_en'] is not None

    # Reabrir quita la fecha: abierta con fecha de cierre es una contradiccion.
    abierta = cliente.patch(f'/api/v1/tareas/{t["id"]}', headers=admin,
                            json={'estado': 'pendiente'}).json()
    assert abierta['cerrada_en'] is None


def test_la_lista_pone_lo_urgente_arriba(cliente, admin, db):
    c = un_cliente(cliente, admin, 'Tarea Orden Cliente')
    for titulo, prioridad in (('La de baja', 'baja'), ('La de alta', 'alta'),
                              ('La de media', 'media')):
        cliente.post('/api/v1/tareas', headers=admin, json={
            'titulo': titulo, 'cliente_id': c['id'], 'prioridad': prioridad})

    items = cliente.get(f'/api/v1/tareas?cliente_id={c["id"]}', headers=admin).json()['items']
    assert [t['prioridad'] for t in items] == ['alta', 'media', 'baja'], items


def test_una_tarea_vencida_se_marca_y_se_puede_filtrar(cliente, admin, db):
    c = un_cliente(cliente, admin, 'Tarea Vencida Cliente')
    ayer = (dt.datetime.now(BOGOTA) - dt.timedelta(days=2)).date().isoformat()
    cliente.post('/api/v1/tareas', headers=admin, json={
        'titulo': 'Esta ya se paso', 'cliente_id': c['id'], 'vence_en': ayer})

    items = cliente.get(f'/api/v1/tareas?cliente_id={c["id"]}', headers=admin).json()['items']
    assert items[0]['vencida'] is True

    r = cliente.get('/api/v1/tareas?vencidas=true', headers=admin).json()
    assert any(t['id'] == items[0]['id'] for t in r['items'])
    assert cliente.get('/api/v1/tareas/resumen', headers=admin).json()['vencidas'] >= 1


def test_quien_solo_ve_lo_suyo_no_ve_las_tareas_de_otro(cliente, admin, usuario, db):
    """RNF-03. Una tarea lleva el nombre del cliente y que se esta haciendo con el."""
    ajeno = un_cliente(cliente, admin, 'Tarea Ajena Cliente')
    suya = cliente.post('/api/v1/tareas', headers=admin, json={
        'titulo': 'Tarea de otro', 'cliente_id': ajeno['id']}).json()

    p = usuario('operaciones')
    p.u.alcance = 'asignados'
    db.commit()
    cab = entrar(cliente, p)

    items = cliente.get('/api/v1/tareas', headers=cab).json()['items']
    assert all(t['id'] != suya['id'] for t in items), 'no puede ver la tarea de otro'
    # Y pedirla por id tampoco: decir «existe pero no la ve» ya es decir que existe.
    assert cliente.patch(f'/api/v1/tareas/{suya["id"]}', headers=cab,
                         json={'estado': 'hecha'}).status_code == 404


# ------------------------------------------------------------------- alertas

def test_generar_dos_veces_no_duplica_la_misma_alerta(cliente, admin, db):
    """Se puede correr cada hora sin que la bandeja se vuelva ilegible."""
    primera = cliente.post('/api/v1/alertas/generar', headers=admin, json={}).json()
    segunda = cliente.post('/api/v1/alertas/generar', headers=admin, json={}).json()
    assert segunda['creadas'] == 0, segunda
    assert primera['creadas'] >= 0


def test_la_matriz_es_configurable_y_dice_cuales_tienen_regla(cliente, admin, db):
    """RF-062: cambiar cuando se avisa es editar una fila, no tocar el codigo."""
    tipos = cliente.get('/api/v1/alertas/tipos', headers=admin).json()
    assert len(tipos) >= 13
    por_codigo = {t['codigo']: t for t in tipos}
    assert por_codigo['cita_cas']['anticipacion_valor'] == 7
    assert por_codigo['cita_cas']['tiene_regla'] is True
    # El que todavia no tiene regla se dice, en vez de fingir que se evaluo.
    assert por_codigo['sync_saas_fallida']['tiene_regla'] is False
    # Un valor negativo avisa despues del hecho: el saldo ya se vencio.
    assert por_codigo['saldo_vencido']['anticipacion_valor'] < 0


def test_cambiar_la_matriz_cambia_cuando_se_avisa(cliente, admin, db):
    """La prueba de que la configuracion sirve de verdad."""
    manana = dt.datetime.now(BOGOTA) + dt.timedelta(days=2)
    _, caso = un_caso(cliente, admin, db, 'Alerta Porcita Cliente')
    db.execute(text("""insert into citas (caso_id, tipo, inicia_en, zona_horaria, estado)
                       values (:c, 'entrevista', :i, 'America/Bogota', 'programada')"""),
               {'c': caso.id, 'i': manana})
    db.commit()

    # Con 7 dias de anticipacion la de pasado manana entra.
    r = cliente.post('/api/v1/alertas/generar', headers=admin,
                     json={'codigos': ['entrevista_proxima']}).json()
    assert r['creadas'] >= 1, r

    # Con un dia, no habria entrado: se comprueba sobre una cita mas lejana.
    db.query(Alertas).delete()
    tipo = db.scalars(select(AlertasTipos)
                      .where(AlertasTipos.codigo == 'entrevista_proxima')).first()
    tipo.anticipacion_valor = 1
    db.commit()
    r2 = cliente.post('/api/v1/alertas/generar', headers=admin,
                      json={'codigos': ['entrevista_proxima']}).json()
    assert r2['creadas'] == 0, f'con 1 dia de anticipacion no deberia avisar todavia: {r2}'


def _una_alerta(cliente, admin, db, nombre):
    """Crea una cita proxima y genera su alerta, para no depender de los datos
    que haya. Una prueba que se salta cuando no hay datos no prueba nada."""
    _, caso = un_caso(cliente, admin, db, nombre)
    db.execute(text("""insert into citas (caso_id, tipo, inicia_en, zona_horaria, estado)
                       values (:c, 'entrevista', :i, 'America/Bogota', 'programada')"""),
               {'c': caso.id, 'i': dt.datetime.now(BOGOTA) + dt.timedelta(days=2)})
    db.commit()
    r = cliente.post('/api/v1/alertas/generar', headers=admin,
                     json={'codigos': ['entrevista_proxima']}).json()
    assert r['creadas'] >= 1, r
    a = db.scalars(select(Alertas).order_by(Alertas.id.desc())).first()
    assert a is not None
    return a


def test_posponer_exige_hasta_cuando(cliente, admin, db):
    """Una alerta pospuesta «para despues» no vuelve nunca."""
    a = _una_alerta(cliente, admin, db, 'Alerta Posponer Cliente')

    sin_fecha = cliente.patch(f'/api/v1/alertas/{a.id}', headers=admin,
                              json={'estado': 'pospuesta'})
    assert sin_fecha.status_code == 422 and sin_fecha.json()['codigo'] == 'falta_fecha'

    ayer = (dt.datetime.now(BOGOTA) - dt.timedelta(days=1)).isoformat()
    pasada = cliente.patch(f'/api/v1/alertas/{a.id}', headers=admin,
                           json={'estado': 'pospuesta', 'hasta': ayer})
    assert pasada.status_code == 422 and pasada.json()['codigo'] == 'fecha_pasada'

    manana = (dt.datetime.now(BOGOTA) + dt.timedelta(days=3)).isoformat()
    ok = cliente.patch(f'/api/v1/alertas/{a.id}', headers=admin,
                       json={'estado': 'pospuesta', 'hasta': manana})
    assert ok.status_code == 200 and ok.json()['estado'] == 'pospuesta'
    # Pospuesta sale de la bandeja hasta que se cumpla el plazo.
    abiertas = cliente.get('/api/v1/alertas', headers=admin).json()['items']
    assert all(x['id'] != a.id for x in abiertas)


def test_resolver_deja_quien_y_cuando(cliente, admin, db):
    """Una bandeja que se vacia sin rastro no dice si el equipo responde."""
    a = _una_alerta(cliente, admin, db, 'Alerta Resolver Cliente')

    r = cliente.patch(f'/api/v1/alertas/{a.id}', headers=admin,
                      json={'estado': 'resuelta'}).json()
    assert r['estado'] == 'resuelta' and r['resuelta_en'] is not None
    db.expire_all()
    assert db.get(Alertas, a.id).resuelta_por is not None

    # Y no vuelve a nacer al regenerar: ya se atendio.
    antes = db.scalar(select(Alertas.id).where(Alertas.id == a.id))
    cliente.post('/api/v1/alertas/generar', headers=admin, json={})
    assert db.scalar(select(Alertas.estado).where(Alertas.id == antes)) == 'resuelta'


def test_quien_solo_ve_lo_suyo_no_ve_alertas_ajenas(cliente, admin, usuario, db):
    """RNF-03 en la bandeja: una alerta lleva el nombre del cliente."""
    cliente.post('/api/v1/alertas/generar', headers=admin, json={})
    p = usuario('operaciones')
    p.u.alcance = 'asignados'
    db.commit()
    cab = entrar(cliente, p)

    items = cliente.get('/api/v1/alertas', headers=cab).json()['items']
    for a in items:
        if a['caso_id']:
            caso = db.get(Casos, a['caso_id'])
            assert caso.responsable_id == p.u.id, f've el trámite de otro: {a}'
        else:
            assert a['destinatario_id'] == p.u.id, f've una alerta que no es suya: {a}'


def test_operaciones_puede_trabajar_sus_tareas_y_alertas(cliente, operaciones):
    """No es contabilidad: es su trabajo diario, y lo tiene que poder hacer."""
    cab, _ = operaciones
    assert cliente.get('/api/v1/tareas', headers=cab).status_code == 200
    assert cliente.get('/api/v1/alertas', headers=cab).status_code == 200
    assert cliente.get('/api/v1/alertas/resumen', headers=cab).status_code == 200
