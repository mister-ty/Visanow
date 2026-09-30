"""Actividades 2.5 y 2.6 — casos de visa, citas, transiciones, checklist e historial
(RF-020 a RF-028, RN-04, RN-05, RN-06)."""
import pytest
from sqlalchemy import select

from app.models.esquema import CasosHistorial, ChecklistItems, Paises, Solicitantes
from tests.conftest import entrar

CASOS = '/api/v1/casos'


@pytest.fixture
def operaciones(cliente, usuario):
    p = usuario('operaciones')
    return entrar(cliente, p), p


@pytest.fixture
def admin(cliente, usuario):
    return entrar(cliente, usuario('administradora'))


@pytest.fixture
def solicitante(cliente, db, usuario):
    """Un cliente con una persona lista para tramitar."""
    cab = entrar(cliente, usuario('comercial'))
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': 'Cliente de Trámite'}).json()
    s = cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'cliente_id': c['id'], 'nombre': 'Persona en Trámite',
                           'pasaporte': f'PA{c["id"]:07d}'}).json()
    return s['id']


@pytest.fixture
def pais_usa(db):
    return db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))


def crear_caso(cliente, cab, solicitante_id, pais_id, usuario_id, **extra):
    r = cliente.post(CASOS, headers=cab, json={
        'solicitante_id': solicitante_id, 'pais_id': pais_id, 'responsable_id': usuario_id,
        'proxima_accion': 'Pedir documentos al cliente', **extra})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------- alta

def test_crear_un_tramite_sin_venta_registrada(cliente, operaciones, solicitante, pais_usa, db):
    """Al migrar habrá trámites sin venta: la operación y el dinero viven hoy en
    archivos distintos. El sistema lo permite y lo deja ver."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    assert caso['estado'] == 'registrado' and caso['sin_venta'] is True
    assert caso['fuente'] == 'manual' and caso['riesgo'] == 'bajo'
    assert db.scalar(select(CasosHistorial).where(CasosHistorial.caso_id == caso['id'],
                                                  CasosHistorial.campo == 'creado'))


def test_el_tramite_del_saas_queda_marcado_con_su_numero(cliente, operaciones, solicitante, pais_usa):
    """Criterio 12: hay que poder distinguir lo que viene del SaaS de lo manual."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id, id_externo='0d9ccdd3')
    assert caso['fuente'] == 'saas' and caso['id_externo'] == '0d9ccdd3'


# ---------------------------------------------------------------- tablero

def test_el_tablero_filtra_por_estado_sin_asignar_y_sin_venta(cliente, operaciones, solicitante, pais_usa):
    cab, p = operaciones
    asignado = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    suelto = cliente.post(CASOS, headers=cab, json={'solicitante_id': solicitante, 'pais_id': pais_usa}).json()

    sin_asignar = cliente.get(CASOS, headers=cab, params={'sin_asignar': True}).json()
    assert suelto['id'] in [c['id'] for c in sin_asignar['items']]
    assert asignado['id'] not in [c['id'] for c in sin_asignar['items']]

    registrados = cliente.get(CASOS, headers=cab, params={'estado': 'registrado'}).json()
    assert registrados['total'] >= 2
    assert all(c['sin_venta'] for c in cliente.get(CASOS, headers=cab, params={'sin_venta': True}).json()['items'])

    resumen = cliente.get(f'{CASOS}/resumen', headers=cab).json()
    assert any(e['codigo'] == 'registrado' and e['total'] >= 2 for e in resumen)


def test_el_tablero_busca_por_nombre_y_por_numero_de_solicitud(cliente, operaciones, solicitante, pais_usa):
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id, id_externo='4c15f87a')
    assert caso['id'] in [c['id'] for c in cliente.get(CASOS, headers=cab,
                                                       params={'texto': 'persona en tramite'}).json()['items']]
    assert caso['id'] in [c['id'] for c in cliente.get(CASOS, headers=cab,
                                                       params={'texto': '4c15f87a'}).json()['items']]


# ------------------------------------------------- orden de los estados

def test_no_se_puede_saltar_el_orden_de_los_estados(cliente, operaciones, solicitante, pais_usa):
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab, json={'codigo_destino': 'finalizado'})
    assert r.status_code == 409 and r.json()['codigo'] == 'transicion_no_permitida'
    assert 'Esperando información del cliente' in r.json()['detalle'], 'debe decir a dónde sí se puede ir'


def test_un_tramite_abierto_exige_responsable_y_proxima_accion(cliente, operaciones, solicitante, pais_usa):
    """RN-04: ningún caso activo puede quedar sin dueño ni sin próximo paso."""
    cab, p = operaciones
    caso = cliente.post(CASOS, headers=cab, json={'solicitante_id': solicitante, 'pais_id': pais_usa}).json()
    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab, json={'codigo_destino': 'esperando_info'})
    assert r.status_code == 422 and r.json()['codigo'] == 'falta_responsable'

    cliente.patch(f"{CASOS}/{caso['id']}", headers=cab, json={'responsable_id': p.u.id})
    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab, json={'codigo_destino': 'esperando_info'})
    assert r.status_code == 422 and r.json()['codigo'] == 'falta_proxima_accion'

    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab,
                     json={'codigo_destino': 'esperando_info',
                           'cambios': {'proxima_accion': 'Llamar al cliente'}})
    assert r.status_code == 200 and r.json()['estado'] == 'esperando_info'


def test_la_cita_confirmada_exige_cita_agendada_y_sede(cliente, operaciones, solicitante, pais_usa, db):
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    for destino in ('esperando_info', 'info_en_revision', 'formulario_elaborando', 'formulario_enviado',
                    'pago_consular_pend', 'busqueda_cita'):
        r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab, json={'codigo_destino': destino})
        assert r.status_code == 200, f'{destino}: {r.text}'

    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab, json={'codigo_destino': 'cita_confirmada'})
    assert r.status_code == 422 and r.json()['codigo'] == 'faltan_campos'
    assert 'cita agendada' in r.json()['detalle'] and 'sede' in r.json()['detalle']

    cliente.post(f"{CASOS}/{caso['id']}/citas", headers=cab,
                 json={'tipo': 'entrevista', 'inicia_en': '2026-11-20T08:30:00-05:00'})
    from app.models.esquema import Sedes
    sede = db.scalar(select(Sedes.id).limit(1))
    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab,
                     json={'codigo_destino': 'cita_confirmada', 'cambios': {'sede_id': sede}})
    assert r.status_code == 200, r.text


def test_el_checklist_obligatorio_frena_el_paso_a_esperando_resultado(cliente, operaciones, solicitante,
                                                                     pais_usa, db):
    """RN-05: nadie llega a la entrevista sin los documentos marcados."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    from app.models.esquema import Sedes
    sede = db.scalar(select(Sedes.id).limit(1))
    for destino in ('esperando_info', 'info_en_revision', 'formulario_elaborando', 'formulario_enviado',
                    'pago_consular_pend', 'busqueda_cita'):
        cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab, json={'codigo_destino': destino})
    cliente.post(f"{CASOS}/{caso['id']}/citas", headers=cab,
                 json={'tipo': 'entrevista', 'inicia_en': '2026-11-20T08:30:00-05:00'})
    cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab,
                 json={'codigo_destino': 'cita_confirmada', 'cambios': {'sede_id': sede}})
    cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab, json={'codigo_destino': 'checklist'})

    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab,
                     json={'codigo_destino': 'esperando_resultado'})
    assert r.status_code == 422 and r.json()['codigo'] == 'checklist_incompleto'
    assert 'Pasaporte vigente' in r.json()['detalle']

    ficha = cliente.get(f"{CASOS}/{caso['id']}", headers=cab).json()
    for item in ficha['checklist']:
        if item['obligatorio']:
            cliente.post(f"{CASOS}/{caso['id']}/checklist/{item['item_id']}", headers=cab,
                         json={'cumplido': True})
    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab,
                     json={'codigo_destino': 'esperando_resultado'})
    assert r.status_code == 200, r.text


def test_finalizar_exige_resultado_y_una_negada_puede_quedar_finalizada(cliente, operaciones, solicitante,
                                                                       pais_usa, db):
    """RN-06: el resultado consular no es lo mismo que terminar el servicio."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab,
                     json={'codigo_destino': 'finalizado', 'forzar': True, 'motivo': 'prueba'})
    assert r.status_code == 403, 'operaciones no puede saltarse el orden del proceso'

    r = cliente.post(f"{CASOS}/{caso['id']}/resultado", headers=cab,
                     json={'resultado': 'negada', 'nota': 'No demostró vínculos'})
    assert r.status_code == 200 and r.json()['resultado'] == 'negada'
    assert r.json()['es_final'] is False, 'una visa negada no cierra el trámite por sí sola'


def test_la_administradora_puede_saltarse_el_orden_con_motivo(cliente, admin, operaciones, solicitante,
                                                             pais_usa, db):
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    cliente.post(f"{CASOS}/{caso['id']}/resultado", headers=cab, json={'resultado': 'cancelado'})
    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=admin,
                     json={'codigo_destino': 'finalizado', 'forzar': True,
                           'motivo': 'El cliente desistió y se cerró de acuerdo con la administradora'})
    assert r.status_code == 200 and r.json()['estado'] == 'finalizado'
    excepcion = db.scalar(select(CasosHistorial).where(CasosHistorial.caso_id == caso['id'],
                                                       CasosHistorial.campo == 'excepcion'))
    assert excepcion is not None and 'desistió' in excepcion.observacion


def test_forzar_sin_motivo_no_pasa(cliente, admin, operaciones, solicitante, pais_usa):
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    r = cliente.post(f"{CASOS}/{caso['id']}/estado", headers=admin,
                     json={'codigo_destino': 'entrega_documento', 'forzar': True})
    assert r.status_code == 422 and r.json()['codigo'] == 'falta_motivo'


# ------------------------------------------------------ citas e historial

def test_agendar_una_cita_queda_en_el_historial_con_su_zona_horaria(cliente, operaciones, solicitante,
                                                                    pais_usa):
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    r = cliente.post(f"{CASOS}/{caso['id']}/citas", headers=cab,
                     json={'tipo': 'cas', 'inicia_en': '2026-10-15T09:00:00-05:00',
                           'observaciones': 'Llevar pasaporte'})
    assert r.status_code == 201 and r.json()['zona_horaria'] == 'America/Bogota'
    cita_id = r.json()['id']

    cliente.patch(f'/api/v1/citas/{cita_id}', headers=cab, json={'estado': 'confirmada'})
    historial = cliente.get(f"{CASOS}/{caso['id']}/historial", headers=cab).json()
    campos = [h['campo'] for h in historial]
    assert 'cita_cas' in campos and 'cita_cas_estado' in campos
    assert all(h['usuario'] for h in historial if h['campo'] != 'creado')


def test_el_historial_guarda_valor_anterior_y_nuevo(cliente, operaciones, solicitante, pais_usa):
    """RF-028 y criterio 10: toda edición crítica deja usuario, fecha, valor
    anterior y valor nuevo."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    cliente.post(f"{CASOS}/{caso['id']}/estado", headers=cab, json={'codigo_destino': 'esperando_info'})
    historial = cliente.get(f"{CASOS}/{caso['id']}/historial", headers=cab).json()
    cambio = next(h for h in historial if h['campo'] == 'estado')
    assert cambio['valor_anterior'] == 'registrado' and cambio['valor_nuevo'] == 'esperando_info'
    assert cambio['usuario'] == p.u.nombre


def test_finanzas_ve_los_tramites_pero_no_los_mueve(cliente, usuario, solicitante, pais_usa, operaciones):
    """Finanzas necesita ver el trámite para entender un pago, pero no lo opera."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    finanzas = entrar(cliente, usuario('finanzas'))
    assert cliente.get(f"{CASOS}/{caso['id']}", headers=finanzas).status_code == 200
    assert cliente.post(f"{CASOS}/{caso['id']}/estado", headers=finanzas,
                        json={'codigo_destino': 'esperando_info'}).status_code == 403
    assert cliente.post(f"{CASOS}/{caso['id']}/citas", headers=finanzas,
                        json={'tipo': 'cas', 'inicia_en': '2026-10-15T09:00:00-05:00'}).status_code == 403


def test_solo_aplica_el_checklist_mas_especifico(cliente, operaciones, solicitante, pais_usa, db):
    """Al trámite de visa USA le encajan tres checklists (el de primera vez, el
    de renovación y el general). Si se acumularan, «Pasaporte vigente» saldría
    tres veces y nadie sabría cuál marcar."""
    from app.models.esquema import TiposVisa
    cab, p = operaciones
    tipo = db.scalar(select(TiposVisa.id).where(TiposVisa.codigo == 'B1B2'))
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id, tipo_visa_id=tipo)
    checklist = cliente.get(f"{CASOS}/{caso['id']}", headers=cab).json()['checklist']
    nombres = [i['nombre'] for i in checklist]
    assert len(nombres) == len(set(nombres)), f'documentos repetidos: {nombres}'
    assert 'Pasaporte vigente (mínimo 6 meses)' in nombres, 'debe ganar el checklist de primera vez'
    assert 'Formulario del consulado diligenciado' not in nombres, 'el general no debe acumularse'


def test_la_cita_le_pone_la_sede_al_tramite(cliente, operaciones, solicitante, pais_usa, db):
    """La sede se elige una vez, al agendar."""
    from app.models.esquema import Sedes
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    sede = db.scalar(select(Sedes.id).limit(1))
    assert cliente.get(f"{CASOS}/{caso['id']}", headers=cab).json()['sede_id'] is None
    cliente.post(f"{CASOS}/{caso['id']}/citas", headers=cab,
                 json={'tipo': 'entrevista', 'inicia_en': '2026-11-18T08:30:00-05:00', 'sede_id': sede})
    assert cliente.get(f"{CASOS}/{caso['id']}", headers=cab).json()['sede_id'] == sede


# ------------------------------------------------- alcance por casos asignados

def test_quien_solo_ve_lo_asignado_no_ve_los_tramites_de_los_demas(
        cliente, db, usuario, solicitante, pais_usa):
    """RNF-03. El alcance estaba guardado en el usuario desde el principio, pero
    ninguna consulta lo leía: bastaba con no enviar el filtro de responsable
    para ver todo. El filtro de la pantalla es una comodidad; esto es control de
    acceso y vive en el servicio."""
    from app.services import usuarios as servicio_usuarios

    admin = usuario('administradora')
    dueno = usuario('operaciones')
    otro = usuario('operaciones')
    servicio_usuarios.editar(db, admin.u, otro.u.id, alcance='asignados')
    db.commit()

    cab_dueno = entrar(cliente, dueno)
    mio = crear_caso(cliente, cab_dueno, solicitante, pais_usa, dueno.u.id)

    cab_otro = entrar(cliente, otro)
    vistos = cliente.get(CASOS, headers=cab_otro).json()
    assert mio['id'] not in [c['id'] for c in vistos['items']],         've un trámite que no es suyo'
    assert vistos['total'] == 0

    # Y tampoco puede abrirlo por la URL directa
    r = cliente.get(f'{CASOS}/{mio["id"]}', headers=cab_otro)
    assert r.status_code == 404, 'la URL directa se salta el alcance'
    # Responde 404 y no 403: decir «existe pero no es suyo» ya revela que esa
    # persona es cliente de VisaNow.
    assert 'no existe' in r.json()['detalle']

    # El dueño sí lo ve
    assert cliente.get(f'{CASOS}/{mio["id"]}', headers=cab_dueno).status_code == 200


def test_quien_ve_todo_sigue_viendo_todo(cliente, db, usuario, solicitante, pais_usa):
    dueno = usuario('operaciones')
    miron = usuario('operaciones')       # alcance 'todos' por defecto
    cab = entrar(cliente, dueno)
    mio = crear_caso(cliente, cab, solicitante, pais_usa, dueno.u.id)
    vistos = cliente.get(CASOS, headers=entrar(cliente, miron)).json()
    assert mio['id'] in [c['id'] for c in vistos['items']]
