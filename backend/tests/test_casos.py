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


def test_reprogramar_una_cita_no_tumba_la_peticion(cliente, operaciones, solicitante, pais_usa, db):
    """La auditoría recibía la fecha nueva como datetime crudo y la columna es
    jsonb: la petición entera moría con un 500. Registrar la auditoría no puede
    ser lo que tumbe la operación que audita."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    cita = cliente.post(f'{CASOS}/{caso["id"]}/citas', headers=cab, json={
        'tipo': 'entrevista', 'inicia_en': '2027-04-15T07:30:00-05:00'}).json()

    r = cliente.patch(f'/api/v1/citas/{cita["id"]}', headers=cab, json={
        'inicia_en': '2027-05-20T09:00:00-05:00', 'estado': 'reprogramada',
        'observaciones': 'El consulado la corrió dos semanas'})
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'reprogramada'
    assert r.json()['inicia_en'].startswith('2027-05-20')

    # y el cambio quedó contado en el historial del trámite
    titulos = [h['titulo'] for h in
               cliente.get(f'{CASOS}/{caso["id"]}/historial', headers=cab).json()]
    assert any('reprogramada' in t for t in titulos), titulos


def test_mover_una_cita_deja_una_sola_linea_en_el_historial(cliente, operaciones, solicitante,
                                                            pais_usa):
    """Reprogramar cambia fecha, estado y nota a la vez. Escribir una entrada por
    campo dejaba tres renglones casi iguales para algo que la persona vivió como
    un solo acto: «el consulado me corrió la cita»."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    cita = cliente.post(f'{CASOS}/{caso["id"]}/citas', headers=cab, json={
        'tipo': 'entrevista', 'inicia_en': '2027-04-15T07:30:00-05:00'}).json()
    antes = len(cliente.get(f'{CASOS}/{caso["id"]}/historial', headers=cab).json())

    cliente.patch(f'/api/v1/citas/{cita["id"]}', headers=cab, json={
        'inicia_en': '2027-05-20T09:00:00-05:00', 'estado': 'reprogramada',
        'observaciones': 'El consulado la corrió'})

    historial = cliente.get(f'{CASOS}/{caso["id"]}/historial', headers=cab).json()
    assert len(historial) == antes + 1, [h['titulo'] for h in historial]
    nueva = historial[0]
    assert 'reprogramada' in nueva['titulo']
    assert nueva['observacion'] == 'El consulado la corrió', 'la nota va en la misma línea'


# ------------------------------------------------------------ colaboradores

def _con_alcance_limitado(db, usuario, admin):
    from app.services import usuarios as servicio_usuarios
    u = usuario('operaciones')
    servicio_usuarios.editar(db, admin.u, u.u.id, alcance='asignados')
    db.commit()
    return u


def test_colaborar_en_un_tramite_deja_verlo_aunque_no_sea_suyo(
        cliente, db, usuario, solicitante, pais_usa):
    """RF-026. Hasta hoy solo existia el responsable: ayudar en un tramite ajeno
    obligaba a reasignarlo, y reasignar cambia quien responde por el, que no es
    lo mismo que ayudar.

    Lo que esta prueba vigila es que ser colaborador sirva de algo. Si el nombre
    quedara en la ficha pero el alcance siguiera mirando solo al responsable,
    el colaborador veria que lo pusieron y no podria abrir el tramite.
    """
    admin = usuario('administradora')
    dueno = usuario('operaciones')
    ayuda = _con_alcance_limitado(db, usuario, admin)

    cab_dueno = entrar(cliente, dueno)
    caso = crear_caso(cliente, cab_dueno, solicitante, pais_usa, dueno.u.id)

    cab_ayuda = entrar(cliente, ayuda)
    assert cliente.get(f'{CASOS}/{caso["id"]}', headers=cab_ayuda).status_code == 404

    r = cliente.post(f'{CASOS}/{caso["id"]}/colaboradores', headers=cab_dueno,
                     json={'usuario_id': ayuda.u.id})
    assert r.status_code == 201, r.text
    assert [c['usuario_id'] for c in r.json()] == [ayuda.u.id]

    assert cliente.get(f'{CASOS}/{caso["id"]}', headers=cab_ayuda).status_code == 200
    vistos = cliente.get(CASOS, headers=cab_ayuda).json()
    assert caso['id'] in [c['id'] for c in vistos['items']], 'y sale en su lista'


def test_quitarlo_le_quita_el_acceso(cliente, db, usuario, solicitante, pais_usa):
    admin = usuario('administradora')
    dueno = usuario('operaciones')
    ayuda = _con_alcance_limitado(db, usuario, admin)
    cab_dueno, cab_ayuda = entrar(cliente, dueno), entrar(cliente, ayuda)
    caso = crear_caso(cliente, cab_dueno, solicitante, pais_usa, dueno.u.id)

    cliente.post(f'{CASOS}/{caso["id"]}/colaboradores', headers=cab_dueno,
                 json={'usuario_id': ayuda.u.id})
    assert cliente.get(f'{CASOS}/{caso["id"]}', headers=cab_ayuda).status_code == 200

    r = cliente.delete(f'{CASOS}/{caso["id"]}/colaboradores/{ayuda.u.id}', headers=cab_dueno)
    assert r.status_code == 200 and r.json() == []
    assert cliente.get(f'{CASOS}/{caso["id"]}', headers=cab_ayuda).status_code == 404


def test_colaborar_no_abre_los_demas_tramites(cliente, db, usuario, solicitante, pais_usa):
    """Es acceso a ESE tramite, no un ascenso de alcance."""
    admin = usuario('administradora')
    dueno = usuario('operaciones')
    ayuda = _con_alcance_limitado(db, usuario, admin)
    cab_dueno, cab_ayuda = entrar(cliente, dueno), entrar(cliente, ayuda)

    uno = crear_caso(cliente, cab_dueno, solicitante, pais_usa, dueno.u.id)
    otro = crear_caso(cliente, cab_dueno, solicitante, pais_usa, dueno.u.id)
    cliente.post(f'{CASOS}/{uno["id"]}/colaboradores', headers=cab_dueno,
                 json={'usuario_id': ayuda.u.id})

    assert cliente.get(f'{CASOS}/{uno["id"]}', headers=cab_ayuda).status_code == 200
    assert cliente.get(f'{CASOS}/{otro["id"]}', headers=cab_ayuda).status_code == 404


def test_el_responsable_no_se_agrega_como_colaborador_de_lo_suyo(
        cliente, db, usuario, solicitante, pais_usa):
    dueno = usuario('operaciones')
    cab = entrar(cliente, dueno)
    caso = crear_caso(cliente, cab, solicitante, pais_usa, dueno.u.id)
    r = cliente.post(f'{CASOS}/{caso["id"]}/colaboradores', headers=cab,
                     json={'usuario_id': dueno.u.id})
    assert r.status_code == 409 and r.json()['codigo'] == 'ya_es_responsable'


def test_no_se_agrega_dos_veces(cliente, db, usuario, solicitante, pais_usa):
    dueno, ayuda = usuario('operaciones'), usuario('operaciones')
    cab = entrar(cliente, dueno)
    caso = crear_caso(cliente, cab, solicitante, pais_usa, dueno.u.id)
    cliente.post(f'{CASOS}/{caso["id"]}/colaboradores', headers=cab,
                 json={'usuario_id': ayuda.u.id})
    r = cliente.post(f'{CASOS}/{caso["id"]}/colaboradores', headers=cab,
                     json={'usuario_id': ayuda.u.id})
    assert r.status_code == 409 and r.json()['codigo'] == 'ya_colabora'


def test_no_se_agrega_a_alguien_inactivo(cliente, db, usuario, solicitante, pais_usa):
    """Dar acceso a una cuenta desactivada es volver a abrirla por la ventana."""
    from app.services import usuarios as servicio_usuarios
    admin = usuario('administradora')
    dueno, ido = usuario('operaciones'), usuario('operaciones')
    servicio_usuarios.editar(db, admin.u, ido.u.id, activo=False)
    db.commit()

    cab = entrar(cliente, dueno)
    caso = crear_caso(cliente, cab, solicitante, pais_usa, dueno.u.id)
    r = cliente.post(f'{CASOS}/{caso["id"]}/colaboradores', headers=cab,
                     json={'usuario_id': ido.u.id})
    assert r.status_code == 422 and r.json()['codigo'] == 'usuario_invalido'


def test_entrar_y_salir_queda_en_el_historial_del_tramite(
        cliente, db, usuario, solicitante, pais_usa):
    """RN-08: el historial solo crece. Quien entro a ver un tramite ajeno y
    cuando dejo de poder es justo lo que hay que poder reconstruir."""
    dueno, ayuda = usuario('operaciones'), usuario('operaciones')
    cab = entrar(cliente, dueno)
    caso = crear_caso(cliente, cab, solicitante, pais_usa, dueno.u.id)
    cliente.post(f'{CASOS}/{caso["id"]}/colaboradores', headers=cab,
                 json={'usuario_id': ayuda.u.id})
    cliente.delete(f'{CASOS}/{caso["id"]}/colaboradores/{ayuda.u.id}', headers=cab)

    from app.models.esquema import CasosHistorial
    filas = db.scalars(select(CasosHistorial).where(
        CasosHistorial.caso_id == caso['id'],
        CasosHistorial.campo == 'colaborador')).all()
    assert len(filas) == 2, filas
    assert {f.observacion for f in filas} == {'Entra a colaborar en el trámite.',
                                              'Deja de colaborar en el trámite.'}


def test_quien_no_ve_el_tramite_no_puede_meter_gente_en_el(
        cliente, db, usuario, solicitante, pais_usa):
    admin = usuario('administradora')
    dueno = usuario('operaciones')
    ajeno = _con_alcance_limitado(db, usuario, admin)
    cab_dueno = entrar(cliente, dueno)
    caso = crear_caso(cliente, cab_dueno, solicitante, pais_usa, dueno.u.id)

    r = cliente.post(f'{CASOS}/{caso["id"]}/colaboradores', headers=entrar(cliente, ajeno),
                     json={'usuario_id': ajeno.u.id})
    assert r.status_code == 404, 'ni siquiera para meterse a si mismo'


# ------------------------------- el alcance tambien tiene que valer al ESCRIBIR

def test_quien_solo_ve_lo_suyo_tampoco_puede_tocar_lo_ajeno(
        cliente, db, usuario, solicitante, pais_usa):
    """RNF-03, la mitad que faltaba.

    El alcance se aplicaba al LEER: quien tiene «solo asignados» no ve los
    tramites ajenos en la lista y recibe 404 si entra por la URL. Pero las cinco
    rutas de ESCRITURA llamaban a obtener(db, caso_id) sin el actor, asi que con
    solo saber el numero del tramite se podia editarlo, moverlo de estado,
    registrarle el resultado, agendarle una cita y marcarle el checklist.

    Peor que ver lo ajeno: cambiarlo. Y como el responsable no se entera, el
    historial dice que alguien lo movio sin que nadie entienda por que.
    """
    from app.services import usuarios as servicio_usuarios

    admin = usuario('administradora')
    dueno = usuario('operaciones')
    ajeno = usuario('operaciones')
    servicio_usuarios.editar(db, admin.u, ajeno.u.id, alcance='asignados')
    db.commit()

    cab_dueno = entrar(cliente, dueno)
    caso = crear_caso(cliente, cab_dueno, solicitante, pais_usa, dueno.u.id)
    cab_ajeno = entrar(cliente, ajeno)

    # Primero, lo que ya funcionaba: no lo ve.
    assert cliente.get(f'{CASOS}/{caso["id"]}', headers=cab_ajeno).status_code == 404

    # Y ahora lo que no: tampoco puede tocarlo por ninguna de las cinco puertas.
    escrituras = [
        ('editar', lambda: cliente.patch(f'{CASOS}/{caso["id"]}', headers=cab_ajeno,
                                         json={'proxima_accion': 'Me lo apropio'})),
        ('mover', lambda: cliente.post(f'{CASOS}/{caso["id"]}/mover', headers=cab_ajeno,
                                       json={'estado': 'documentos'})),
        ('resultado', lambda: cliente.post(f'{CASOS}/{caso["id"]}/resultado',
                                           headers=cab_ajeno,
                                           json={'resultado': 'aprobada'})),
        ('cita', lambda: cliente.post(f'{CASOS}/{caso["id"]}/citas', headers=cab_ajeno,
                                      json={'tipo': 'cas', 'inicia_en': '2026-12-01T09:00:00'})),
        ('checklist', lambda: cliente.post(f'{CASOS}/{caso["id"]}/checklist/1',
                                           headers=cab_ajeno, json={'cumplido': True})),
    ]
    # Se revisan las cinco y se reportan todas: parar en la primera esconde las
    # demas, y lo que hace falta saber es cuantas puertas quedaron abiertas.
    coladas = [(n, llamar().status_code) for n, llamar in escrituras]
    coladas = [(n, c) for n, c in coladas if c != 404]
    assert not coladas, (
        f'dejaron escribir en un tramite ajeno: {coladas}. '
        f'No ver algo y no poder cambiarlo tienen que ser la misma cosa.')

    # Y el tramite quedo igual.
    db.expire_all()
    from app.models.esquema import Casos as M
    assert db.get(M, caso['id']).proxima_accion != 'Me lo apropio'


def test_el_404_al_editar_lo_ajeno_no_puede_ser_cosmetico(
        cliente, db, usuario, solicitante, pais_usa):
    """La ruta escribia y DESPUES devolvia el detalle, que es quien da el 404.

        servicio.editar(db, actor, caso_id, ...)   # ya escribio
        return detalle(caso_id, actor, db)         # el 404 sale aca

    Asi que quien no tiene alcance recibia un 404, creia que no habia pasado
    nada, y el tramite ajeno quedaba cambiado. Un error que miente sobre lo que
    acaba de ocurrir es peor que no tener control: nadie va a ir a revisar.
    """
    from app.services import usuarios as servicio_usuarios
    from app.models.esquema import Casos as M

    admin = usuario('administradora')
    dueno = usuario('operaciones')
    ajeno = usuario('operaciones')
    servicio_usuarios.editar(db, admin.u, ajeno.u.id, alcance='asignados')
    db.commit()

    cab_dueno = entrar(cliente, dueno)
    caso = crear_caso(cliente, cab_dueno, solicitante, pais_usa, dueno.u.id)
    antes = db.get(M, caso['id']).proxima_accion

    r = cliente.patch(f'{CASOS}/{caso["id"]}', headers=entrar(cliente, ajeno),
                      json={'proxima_accion': 'Fantasma'})
    assert r.status_code == 404

    db.expire_all()
    assert db.get(M, caso['id']).proxima_accion == antes, (
        'el 404 mintio: el tramite ajeno quedo cambiado de todas formas')


# --------------------------------- la fecha del resultado es la de Bogota (RF-027)

def test_una_visa_resuelta_de_noche_no_queda_con_la_fecha_de_manana():
    """El contenedor corre con TZ=UTC (Dockerfile:7) y el servicio usaba
    date.today(), que ahi devuelve el dia UTC. Colombia esta en UTC-5: desde las
    siete de la noche de Bogota, para el servidor ya es manana. La agencia
    atiende de noche, asi que una visa aprobada el jueves a las ocho quedaba
    registrada el viernes.

    No es un detalle de presentacion: resultado_fecha es la fecha en que el
    consulado resolvio, y de ella salen los conteos por dia y por mes.

    Se prueba con un instante EXPLICITO a proposito: este equipo esta en Bogota,
    asi que comparar contra date.today() pasaria sin comprobar nada.
    """
    import datetime as dt
    from app.services.casos import _hoy

    # 11 de octubre 02:30 UTC == 10 de octubre 21:30 en Bogota
    de_noche = dt.datetime(2026, 10, 11, 2, 30, tzinfo=dt.timezone.utc)
    assert _hoy(de_noche) == dt.date(2026, 10, 10), 'se adelanto un dia'
    assert de_noche.date() == dt.date(2026, 10, 11), 'asi es como estaba mal'

    # Y de dia, cuando las dos zonas coinciden, no cambia nada.
    de_dia = dt.datetime(2026, 10, 10, 15, 0, tzinfo=dt.timezone.utc)
    assert _hoy(de_dia) == dt.date(2026, 10, 10)

    # Al filo: 04:59 UTC sigue siendo el dia anterior en Bogota; 05:00 ya no.
    assert _hoy(dt.datetime(2026, 10, 11, 4, 59, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 10)
    assert _hoy(dt.datetime(2026, 10, 11, 5, 0, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 11)


def test_el_resultado_se_guarda_con_la_fecha_de_bogota(cliente, db, usuario,
                                                       solicitante, pais_usa):
    import datetime as dt
    from zoneinfo import ZoneInfo
    from app.models.esquema import Casos as M

    dueno = usuario('operaciones')
    cab = entrar(cliente, dueno)
    caso = crear_caso(cliente, cab, solicitante, pais_usa, dueno.u.id)
    r = cliente.post(f'{CASOS}/{caso["id"]}/resultado', headers=cab,
                     json={'resultado': 'aprobada'})
    assert r.status_code == 200, r.text

    db.expire_all()
    guardada = db.get(M, caso['id']).resultado_fecha
    assert guardada == dt.datetime.now(ZoneInfo('America/Bogota')).date()
