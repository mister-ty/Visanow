"""Importación del consolidado del SaaS (RF-030 a RF-036, actividades 5.2 y 5.3).

El export real que mandó VisaNow trae 5 filas de un mes, todas en la misma
etapa. Con eso no se puede probar nada de lo que importa: que reimportar no
duplique, que un cambio de etapa se note, que un DS-160 distinto levante
conflicto. Esos casos se fabrican acá, que además es mejor que esperar a que un
archivo real los contenga por casualidad.
"""
import datetime as dt

import pytest
from sqlalchemy import select

from app.core import seguridad as seg
from app.models.esquema import Casos, EstadosOperativos, Paises
from tests.conftest import entrar


@pytest.fixture
def operador(cliente, usuario):
    """Operaciones es quien importa: tiene importacion.ver y .crear."""
    return entrar(cliente, usuario('operaciones'))


def un_caso(cliente, cab, db, nombre, *, id_externo=None, etapa='registrado'):
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': nombre}).json()
    s = cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'cliente_id': c['id'], 'nombre': nombre}).json()
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    estado = db.scalar(select(EstadosOperativos.id).where(EstadosOperativos.codigo == etapa))
    caso = Casos(solicitante_id=s['id'], pais_id=pais, estado_id=estado,
                 fuente='saas' if id_externo else 'manual', id_externo=id_externo,
                 responsable_id=None, proxima_accion='Pedir documentos',
                 ultima_actividad_en=dt.datetime.now(dt.timezone.utc))
    db.add(caso)
    db.commit()
    return caso


def fila(numero, **extra):
    base = {'numero_solicitud': numero, 'solicitante': 'Quien Sea', 'pasaporte': 'AB123456',
            'etapa': 'Recolectando información', 'fecha_creacion': '2026-09-03',
            'busqueda_citas': 'inactive'}
    base.update(extra)
    return base


def previsualizar(cliente, cab, filas, archivo='export.xlsx'):
    r = cliente.post('/api/v1/saas/previsualizar', headers=cab,
                     json={'filas': filas, 'archivo': archivo})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------- previsualización

def test_previsualizar_no_toca_ningun_tramite(cliente, operador, db):
    """RF-033: importar a ciegas sobre datos de clientes no se puede deshacer."""
    caso = un_caso(cliente, operador, db, 'Previsualiza Cliente', id_externo='AAA111')
    antes = caso.estado_id

    p = previsualizar(cliente, operador, [fila('AAA111', etapa='DS-160 listo')])
    assert p['estado'] == 'previsualizada'
    assert p['actualizados'] == 1 and p['filas'][0]['resultado'] == 'actualizado'

    db.expire_all()
    assert db.get(Casos, caso.id).estado_id == antes, 'previsualizar no puede cambiar nada'


def test_una_fila_sin_numero_de_solicitud_se_rechaza(cliente, operador, db):
    """Sin llave no hay con que reconocerla despues: crearia un tramite nuevo
    en cada importacion."""
    p = previsualizar(cliente, operador, [fila(None)])
    assert p['rechazados'] == 1
    assert 'número de solicitud' in p['filas'][0]['detalle']


def test_el_numero_repetido_en_el_archivo_se_rechaza(cliente, operador, db):
    un_caso(cliente, operador, db, 'Repetida Cliente', id_externo='BBB222')
    p = previsualizar(cliente, operador, [fila('BBB222'), fila('BBB222')])
    assert p['rechazados'] == 1, p
    assert 'repetido' in p['filas'][1]['detalle']


def test_una_solicitud_sin_tramite_queda_para_vincular_a_mano(cliente, operador, db):
    """El export no dice de forma confiable de que persona es: el nombre viene
    escrito distinto cada vez. Vincularlo es mas lento y no se equivoca."""
    p = previsualizar(cliente, operador, [fila('CCC333')])
    assert p['nuevos'] == 1
    assert p['filas'][0]['resultado'] == 'nuevo' and p['filas'][0]['caso_id'] is None


# ----------------------------------------------------------- idempotencia

def test_reimportar_el_mismo_archivo_no_cambia_nada(cliente, operador, db):
    """RF-032. Es lo que hace que el export se pueda bajar cada semana.

    Costó un defecto encontrarlo: `busqueda_citas` es una columna de texto, y
    guardar ahí un bool de Python lo volvia la cadena «false». Comparar el bool
    del export contra ese texto daba distinto SIEMPRE, asi que cada corrida
    decia «actualizado» sin que nada fallara.
    """
    un_caso(cliente, operador, db, 'Idempotente Cliente', id_externo='DDD444')
    filas = [fila('DDD444', etapa='DS-160 listo', busqueda_citas='active')]

    primera = previsualizar(cliente, operador, filas)
    assert primera['actualizados'] == 1
    cliente.post(f'/api/v1/saas/importaciones/{primera["id"]}/aplicar', headers=operador)

    for vuelta in (2, 3):
        otra = previsualizar(cliente, operador, filas, archivo=f'vuelta {vuelta}')
        assert otra['sin_cambios'] == 1, f'vuelta {vuelta}: {otra}'
        assert otra['actualizados'] == 0, f'vuelta {vuelta}: {otra}'


def test_aplicar_mueve_la_etapa_y_deja_la_fecha_de_sincronizacion(cliente, operador, db):
    caso = un_caso(cliente, operador, db, 'Avanza Cliente', id_externo='EEE555')
    p = previsualizar(cliente, operador, [fila('EEE555', etapa='DS-160 listo',
                                               busqueda_citas='active')])
    r = cliente.post(f'/api/v1/saas/importaciones/{p["id"]}/aplicar', headers=operador)
    assert r.status_code == 200, r.text
    assert r.json()['actualizados'] == 1

    db.expire_all()
    actualizado = db.get(Casos, caso.id)
    estado = db.get(EstadosOperativos, actualizado.estado_id)
    assert estado.codigo == 'formulario_enviado', estado.codigo
    assert actualizado.etapa_saas == 'DS-160 listo'
    assert actualizado.sincronizado_en is not None


def test_una_importacion_aplicada_no_se_aplica_dos_veces(cliente, operador, db):
    un_caso(cliente, operador, db, 'Doble Aplicada Cliente', id_externo='FFF666')
    p = previsualizar(cliente, operador, [fila('FFF666', etapa='DS-160 listo')])
    cliente.post(f'/api/v1/saas/importaciones/{p["id"]}/aplicar', headers=operador)
    otra = cliente.post(f'/api/v1/saas/importaciones/{p["id"]}/aplicar', headers=operador)
    assert otra.status_code == 409 and otra.json()['codigo'] == 'estado_invalido'


# ------------------------------------------------ propiedad de datos (RF-034)

def test_el_export_no_pisa_lo_que_gobierna_visanow(cliente, operador, db, usuario):
    """El SaaS manda en sus hitos; VisaNow en el responsable y la proxima accion.

    Un export jamas los toca, ni para rellenarlos: esa es la diferencia entre
    sincronizar y sobrescribir.
    """
    alguien = usuario('operaciones')
    caso = un_caso(cliente, operador, db, 'Propiedad Cliente', id_externo='GGG777')
    caso.responsable_id = alguien.u.id
    caso.proxima_accion = 'Llamar al cliente el viernes'
    db.commit()

    p = previsualizar(cliente, operador, [fila('GGG777', etapa='DS-160 listo')])
    cliente.post(f'/api/v1/saas/importaciones/{p["id"]}/aplicar', headers=operador)

    db.expire_all()
    despues = db.get(Casos, caso.id)
    assert despues.responsable_id == alguien.u.id, 'el export no puede cambiar el responsable'
    assert despues.proxima_accion == 'Llamar al cliente el viernes'


def test_un_ds160_distinto_levanta_conflicto_y_no_se_pisa(cliente, operador, db):
    """El numero guardado lo escribio alguien mirando el formulario."""
    caso = un_caso(cliente, operador, db, 'Conflicto Cliente', id_externo='HHH888')
    caso.ds160_numero_cifrado = seg.cifrar('AA00BB11')
    caso.ds160_hash = seg.indice_ciego('AA00BB11')
    db.commit()

    p = previsualizar(cliente, operador, [fila('HHH888', ds160_numero='ZZ99YY88')])
    assert p['conflictos'] == 1, p
    cliente.post(f'/api/v1/saas/importaciones/{p["id"]}/aplicar', headers=operador)

    db.expire_all()
    assert db.get(Casos, caso.id).ds160_hash == seg.indice_ciego('AA00BB11'), 'no se pisa'

    abiertos = cliente.get('/api/v1/saas/conflictos', headers=operador).json()
    mio = next(c for c in abiertos if c['caso_id'] == caso.id)
    assert mio['campo'] == 'ds160_numero' and mio['valor_saas'] == 'ZZ99YY88'

    # Si gana el SaaS, ahi si se escribe, y queda quien lo decidio.
    r = cliente.post(f'/api/v1/saas/conflictos/{mio["id"]}/resolver', headers=operador,
                     json={'decision': 'resuelto_saas'})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Casos, caso.id).ds160_hash == seg.indice_ciego('ZZ99YY88')


def test_el_ds160_que_falta_si_se_llena(cliente, operador, db):
    """Si VisaNow no lo tiene, no hay nada que proteger: el SaaS lo aporta."""
    caso = un_caso(cliente, operador, db, 'Dsvacio Cliente', id_externo='III999')
    p = previsualizar(cliente, operador, [fila('III999', ds160_numero='NN11MM22')])
    assert p['conflictos'] == 0 and p['actualizados'] == 1
    cliente.post(f'/api/v1/saas/importaciones/{p["id"]}/aplicar', headers=operador)

    db.expire_all()
    assert db.get(Casos, caso.id).ds160_hash == seg.indice_ciego('NN11MM22')


# ------------------------------------------------- vinculación manual (RF-036)

def test_vincular_un_tramite_existente_a_una_solicitud(cliente, operador, db):
    caso = un_caso(cliente, operador, db, 'Vincular Cliente')
    assert caso.id_externo is None

    r = cliente.post('/api/v1/saas/vincular', headers=operador,
                     json={'caso_id': caso.id, 'numero_solicitud': 'JJJ000'})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(Casos, caso.id).id_externo == 'JJJ000'

    # Y a partir de ahi la importacion lo reconoce sola.
    p = previsualizar(cliente, operador, [fila('JJJ000', etapa='DS-160 listo')])
    assert p['nuevos'] == 0 and p['actualizados'] == 1


def test_una_solicitud_no_puede_ser_de_dos_tramites(cliente, operador, db):
    uno = un_caso(cliente, operador, db, 'Primero Vinculado', id_externo='KKK111')
    otro = un_caso(cliente, operador, db, 'Segundo Vinculado')
    r = cliente.post('/api/v1/saas/vincular', headers=operador,
                     json={'caso_id': otro.id, 'numero_solicitud': 'KKK111'})
    assert r.status_code == 409 and r.json()['codigo'] == 'solicitud_ya_vinculada'
    assert str(uno.id) in r.json()['detalle']


def test_los_candidatos_sugieren_pero_no_deciden(cliente, operador, db):
    un_caso(cliente, operador, db, 'Candidata Buscable Persona')
    r = cliente.get('/api/v1/saas/candidatos?numero_solicitud=LLL222'
                    '&nombre=Candidata', headers=operador)
    assert r.status_code == 200, r.text
    assert any('Candidata' in c['solicitante'] for c in r.json())


# ------------------------------------------- registro de sincronización (RF-035)

def test_el_estado_dice_cuando_funciono_por_ultima_vez(cliente, operador, db):
    un_caso(cliente, operador, db, 'Registro Cliente', id_externo='MMM333')
    p = previsualizar(cliente, operador, [fila('MMM333', etapa='DS-160 listo')])
    cliente.post(f'/api/v1/saas/importaciones/{p["id"]}/aplicar', headers=operador)

    e = cliente.get('/api/v1/saas/estado', headers=operador).json()
    assert e['resultado'] == 'ok'
    assert e['ultima_exitosa'] is not None
    assert e['horas_desde_la_ultima_exitosa'] is not None
    assert 'actualizados' in (e['detalle'] or '')


def test_los_errores_repetidos_se_cuentan_como_intentos(cliente, operador, db):
    """Si el SaaS lleva tres dias fallando, interesa que sean tres intentos de lo
    mismo y no tres lineas sueltas que nadie relaciona."""
    from app.services import saas as serv
    for _ in range(3):
        serv.registrar(db, resultado='error', detalle='el archivo no se pudo leer')
    db.commit()
    e = cliente.get('/api/v1/saas/estado', headers=operador).json()
    assert e['resultado'] == 'error' and e['intentos'] == 3, e


def test_descartar_una_previsualizacion_la_deja_sin_efecto(cliente, operador, db):
    caso = un_caso(cliente, operador, db, 'Descartada Cliente', id_externo='NNN444')
    antes = caso.estado_id
    p = previsualizar(cliente, operador, [fila('NNN444', etapa='DS-160 listo')])
    r = cliente.post(f'/api/v1/saas/importaciones/{p["id"]}/descartar', headers=operador)
    assert r.status_code == 200 and r.json()['estado'] == 'descartada'

    assert cliente.post(f'/api/v1/saas/importaciones/{p["id"]}/aplicar',
                        headers=operador).status_code == 409
    db.expire_all()
    assert db.get(Casos, caso.id).estado_id == antes


def test_comercial_no_importa_del_saas(cliente, usuario):
    """Importar cambia trámites de todo el mundo: no es tarea de ventas."""
    cab = entrar(cliente, usuario('comercial'))
    assert cliente.post('/api/v1/saas/previsualizar', headers=cab,
                        json={'filas': [fila('XXX999')]}).status_code == 403


def test_una_etapa_desconocida_avisa_pero_no_tumba_la_fila(cliente, operador, db):
    """Si una etapa nueva del SaaS rechazara la fila entera, una palabra
    cambiada allá congelaría esos trámites acá sin que nada fallara.

    Se actualiza lo que sí se entiende —la búsqueda de citas, el DS-160— y se
    dice qué falta agregar al diccionario.
    """
    caso = un_caso(cliente, operador, db, 'Etapanueva Cliente', id_externo='OOO555')
    antes = caso.estado_id

    p = previsualizar(cliente, operador, [
        fila('OOO555', etapa='Etapa que nadie ha visto', busqueda_citas='active')])
    assert p['rechazados'] == 0, 'una etapa rara no rechaza la fila'
    assert p['actualizados'] == 1, p
    assert 'no está en el diccionario' in p['filas'][0]['detalle']

    cliente.post(f'/api/v1/saas/importaciones/{p["id"]}/aplicar', headers=operador)
    db.expire_all()
    despues = db.get(Casos, caso.id)
    assert despues.estado_id == antes, 'no se mueve de estado si no se entiende la etapa'
    assert despues.busqueda_citas == 'true', 'pero sí se actualiza lo que sí se entiende'
