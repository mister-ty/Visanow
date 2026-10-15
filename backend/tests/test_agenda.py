"""La agenda: las citas de todos los trámites, no las de uno (RF-024).

Una cita solo se veía abriendo el trámite al que pertenece. Eso contesta
«¿cuándo es la cita de Ana?» y no contesta la pregunta con la que se arma el
día: «¿qué hay mañana?». Saber si el jueves había tres entrevistas significaba
abrir los trámites de uno en uno, así que la agenda seguía viviendo en la
cabeza de alguien y el CRM no servía para eso.

Lo que estas pruebas vigilan, además de que la lista salga:

**El día es de Bogotá, no de UTC.** Es el error que no se ve: una cita a las 8
de la mañana acá son las 13:00 UTC, así que filtrar por el día UTC parece
funcionar —la mayoría de las citas caen en el mismo día— hasta la cita de las 7
de la noche, que en UTC ya es del día siguiente y desaparece de la agenda del
día en que de verdad es.

**El alcance.** La agenda cruza trámites, así que es justo donde se escaparía
alguien que no puede abrirlos.
"""
import pytest
from sqlalchemy import select

from app.models.esquema import Paises
from tests.conftest import entrar

AGENDA = '/api/v1/agenda'


@pytest.fixture
def operaciones(cliente, usuario):
    p = usuario('operaciones')
    return entrar(cliente, p), p


@pytest.fixture
def pais_usa(db):
    return db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))


def con_cita(cliente, cab, db, pais, *, nombre: str, cuando: str, responsable_id=None,
             tipo: str = 'entrevista'):
    """Un trámite con una cita, por el camino normal de la aplicación."""
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': nombre}).json()
    s = cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'cliente_id': c['id'], 'nombre': nombre}).json()
    cuerpo = {'solicitante_id': s['id'], 'pais_id': pais,
              'proxima_accion': 'Preparar la entrevista'}
    if responsable_id:
        cuerpo['responsable_id'] = responsable_id
    caso = cliente.post('/api/v1/casos', headers=cab, json=cuerpo)
    assert caso.status_code == 201, caso.text
    caso = caso.json()
    r = cliente.post(f"/api/v1/casos/{caso['id']}/citas", headers=cab,
                     json={'tipo': tipo, 'inicia_en': cuando})
    assert r.status_code == 201, r.text
    return caso, r.json()


def test_la_agenda_junta_las_citas_de_varios_tramites(cliente, db, operaciones, pais_usa):
    """La pregunta que no se podía hacer: «¿qué hay ese día?»."""
    cab, p = operaciones
    con_cita(cliente, cab, db, pais_usa, nombre='Aurora Gil Patiño',
             cuando='2026-11-20T08:30:00-05:00', responsable_id=p.u.id)
    con_cita(cliente, cab, db, pais_usa, nombre='Bruno Celis Arango',
             cuando='2026-11-20T14:00:00-05:00', responsable_id=p.u.id)
    con_cita(cliente, cab, db, pais_usa, nombre='Carla Duque Mesa',
             cuando='2026-11-25T09:00:00-05:00', responsable_id=p.u.id)

    r = cliente.get(AGENDA, headers=cab, params={'desde': '2026-11-20', 'hasta': '2026-11-20'})
    assert r.status_code == 200, r.text
    dia = r.json()

    assert [x['solicitante'] for x in dia] == ['Aurora Gil Patiño', 'Bruno Celis Arango'], (
        'la agenda del 20 tiene que traer las dos de ese día, en orden de hora, '
        'y no la del 25')
    # Y trae lo que hace falta para leerla sin abrir el trámite.
    assert dia[0]['caso_id'] and dia[0]['pais'] and dia[0]['estado_tramite']
    assert dia[0]['responsable'] == p.u.nombre


def test_una_cita_de_la_noche_no_se_va_al_dia_siguiente(cliente, db, operaciones, pais_usa):
    """El error que no se ve: el día de Bogotá no es el día de UTC.

    Las 7 de la noche del 20 en Bogotá son las 00:00 UTC del 21. Filtrando por
    el día UTC, esa cita desaparece de la agenda del 20 —que es el día en que de
    verdad es— y aparece en la del 21, donde nadie la espera. Con citas de la
    mañana no se nota nunca.
    """
    cab, p = operaciones
    con_cita(cliente, cab, db, pais_usa, nombre='Delia Franco Ruiz',
             cuando='2026-11-20T19:00:00-05:00', responsable_id=p.u.id)

    del_20 = cliente.get(AGENDA, headers=cab,
                         params={'desde': '2026-11-20', 'hasta': '2026-11-20'}).json()
    del_21 = cliente.get(AGENDA, headers=cab,
                         params={'desde': '2026-11-21', 'hasta': '2026-11-21'}).json()

    assert [x['solicitante'] for x in del_20] == ['Delia Franco Ruiz'], (
        'la cita de las 7 p.m. del 20 tiene que estar en la agenda del 20')
    assert del_21 == [], 'y no en la del 21'


def test_la_agenda_no_muestra_las_citas_de_tramites_ajenos(cliente, db, usuario, pais_usa):
    """RNF-03. La agenda cruza trámites: es donde se escaparía quien no los ve."""
    from app.services import usuarios as servicio_usuarios

    duena = usuario('operaciones')
    cab_duena = entrar(cliente, duena)
    con_cita(cliente, cab_duena, db, pais_usa, nombre='Elena Soto Vargas',
             cuando='2026-11-20T10:00:00-05:00', responsable_id=duena.u.id)

    ajena = usuario('operaciones')
    servicio_usuarios.editar(db, usuario('administradora').u, ajena.u.id, alcance='asignados')
    db.commit()

    suya = cliente.get(AGENDA, headers=cab_duena,
                       params={'desde': '2026-11-20', 'hasta': '2026-11-20'}).json()
    assert [x['solicitante'] for x in suya] == ['Elena Soto Vargas']

    de_la_otra = cliente.get(AGENDA, headers=entrar(cliente, ajena),
                             params={'desde': '2026-11-20', 'hasta': '2026-11-20'}).json()
    assert de_la_otra == [], (
        'quien tiene «solo lo asignado» no puede ver por la agenda las citas de '
        'trámites que no puede abrir')


def test_una_cita_cancelada_no_estorba_en_la_agenda_pero_no_se_pierde(
        cliente, db, operaciones, pais_usa):
    """Cancelar no es borrar: la cita queda para saber que se perdió el cupo."""
    cab, p = operaciones
    _, cita = con_cita(cliente, cab, db, pais_usa, nombre='Fabio Nieto Cano',
                       cuando='2026-11-20T11:00:00-05:00', responsable_id=p.u.id)
    r = cliente.patch(f"/api/v1/citas/{cita['id']}", headers=cab, json={'estado': 'cancelada'})
    assert r.status_code == 200, r.text

    normal = cliente.get(AGENDA, headers=cab,
                         params={'desde': '2026-11-20', 'hasta': '2026-11-20'}).json()
    assert normal == [], 'una cita cancelada no va en la agenda del día'

    con_todo = cliente.get(AGENDA, headers=cab, params={
        'desde': '2026-11-20', 'hasta': '2026-11-20', 'incluir_canceladas': True}).json()
    assert [x['solicitante'] for x in con_todo] == ['Fabio Nieto Cano'], (
        'pero sigue ahí cuando se pide: se perdió un cupo y eso se mira')


def test_la_agenda_se_puede_filtrar_por_responsable(cliente, db, usuario, operaciones, pais_usa):
    """Repartir el día empieza por «¿qué tengo yo?»."""
    cab, p = operaciones
    otra = usuario('operaciones')
    con_cita(cliente, cab, db, pais_usa, nombre='Gloria Pardo Lema',
             cuando='2026-11-20T08:00:00-05:00', responsable_id=p.u.id)
    con_cita(cliente, cab, db, pais_usa, nombre='Hugo Marin Tobon',
             cuando='2026-11-20T09:00:00-05:00', responsable_id=otra.u.id)

    mias = cliente.get(AGENDA, headers=cab, params={
        'desde': '2026-11-20', 'hasta': '2026-11-20', 'responsable_id': p.u.id}).json()
    assert [x['solicitante'] for x in mias] == ['Gloria Pardo Lema']
