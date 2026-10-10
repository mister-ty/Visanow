"""Conservar, anonimizar y eliminar datos personales (RNF-09).

La Ley 1581 le da a cualquiera el derecho a que le borren sus datos; el Codigo
de Comercio obliga a conservar la contabilidad. Las dos cosas son ciertas a la
vez, y lo que estas pruebas vigilan es que el sistema resuelva la tension de la
forma correcta: anonimizar cuando hay plata, eliminar cuando no.
"""
import datetime as dt

import pytest
from sqlalchemy import select, text

from app.core import seguridad as seg
from app.models.esquema import Auditoria, Casos, Clientes, Paises, Servicios, Solicitantes
from tests.conftest import entrar


@pytest.fixture
def admin(cliente, usuario):
    return entrar(cliente, usuario('administradora'))


@pytest.fixture
def vendedora(cliente, db, usuario):
    from app.models.esquema import ComisionesReglas
    p = usuario('comercial')
    p.u.nombre = 'Angie Lorena'
    regla = db.scalars(select(ComisionesReglas)
                       .where(ComisionesReglas.nombre.like('Angie%'))).first()
    regla.vendedor_id, regla.activo = p.u.id, True
    db.commit()
    return entrar(cliente, p), p


def servicio_id(db, codigo):
    return db.scalar(select(Servicios.id).where(Servicios.codigo == codigo))


def una_persona(cliente, cab, db, nombre, *, documento='1234567', pasaporte='AB999111'):
    c = cliente.post('/api/v1/clientes', headers=cab, json={
        'nombre': nombre, 'tipo_documento': 'CC', 'numero_documento': documento,
        'telefono': '3001234567', 'email': 'quien@ejemplo.com',
        'observaciones': 'Prefiere que la llamen por la tarde'}).json()
    s = cliente.post('/api/v1/solicitantes', headers=cab, json={
        'cliente_id': c['id'], 'nombre': nombre, 'pasaporte': pasaporte,
        'telefono': '3007654321'}).json()
    return c, s


def con_venta(cliente, cab, db, nombre):
    """Un cliente que ya pago: su contabilidad hay que conservarla."""
    c, s = una_persona(cliente, cab, db, nombre)
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    lead = cliente.post('/api/v1/oportunidades', headers=cab, json={
        'cliente_id': c['id'], 'servicio_id': servicio_id(db, 'asesoria_usa'),
        'pais_id': pais, 'proxima_accion': 'Cotizar'}).json()
    venta = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar',
                         headers=cab, json={}).json()
    return c, s, venta


# -------------------------------------------------------------- evaluar

def test_evaluar_dice_que_va_a_pasar_antes_de_tocar_nada(cliente, admin, vendedora, db):
    cab, _ = vendedora
    c, _, _ = con_venta(cliente, cab, db, 'Evaluar Conventa Cliente')

    e = cliente.get(f'/api/v1/datos-personales/{c["id"]}/evaluar', headers=admin).json()
    assert e['puede_eliminarse'] is False
    assert e['ventas'] >= 1
    assert 'contabilidad' in e['razon'].lower()

    # Y el cliente sigue intacto: evaluar no toca nada.
    db.expire_all()
    assert db.get(Clientes, c['id']).nombre == 'Evaluar Conventa Cliente'


def test_un_lead_sin_ventas_si_se_puede_eliminar(cliente, admin, db):
    c, _ = una_persona(cliente, admin, db, 'Lead Sincompra Persona')
    e = cliente.get(f'/api/v1/datos-personales/{c["id"]}/evaluar', headers=admin).json()
    assert e['puede_eliminarse'] is True
    assert e['ventas'] == 0 and e['pagos'] == 0


# ----------------------------------------------------------- anonimizar

def test_anonimizar_quita_lo_que_identifica_y_deja_la_contabilidad(cliente, admin,
                                                                   vendedora, db):
    cab, _ = vendedora
    c, s, venta = con_venta(cliente, cab, db, 'Anonima Conventa Cliente')
    valor = venta['valor_pactado']

    r = cliente.post(f'/api/v1/datos-personales/{c["id"]}/anonimizar', headers=admin,
                     json={'motivo': 'La titular pidio que borraran sus datos'})
    assert r.status_code == 200, r.text

    db.expire_all()
    cl = db.get(Clientes, c['id'])
    assert cl.nombre.startswith('ANONIMIZADO')
    assert cl.numero_documento is None and cl.telefono is None and cl.email is None
    assert cl.archivado is True

    so = db.get(Solicitantes, s['id'])
    assert so.nombre.startswith('ANONIMIZADO')
    assert so.pasaporte is None, 'el pasaporte es el dato mas sensible'
    assert so.pasaporte_indice is None, (
        'el indice ciego tambien: no guarda el dato pero deja confirmar que la '
        'persona estuvo, y eso tambien identifica')

    # La venta sigue en pie, con su valor: son los libros de la empresa.
    fila = db.execute(text('select valor_pactado from negocios where id = :n'),
                      {'n': venta['id']}).first()
    assert fila is not None and float(fila[0]) == valor


def test_anonimizar_borra_el_ds160(cliente, admin, vendedora, db):
    cab, _ = vendedora
    c, s, venta = con_venta(cliente, cab, db, 'Anonima Conds Cliente')
    caso = db.scalars(select(Casos).where(Casos.solicitante_id == s['id'])).first()
    caso.ds160_numero_cifrado = seg.cifrar('AA11BB22')
    caso.ds160_hash = seg.indice_ciego('AA11BB22')
    db.commit()

    cliente.post(f'/api/v1/datos-personales/{c["id"]}/anonimizar', headers=admin,
                 json={'motivo': 'Solicitud del titular por escrito'})
    db.expire_all()
    actualizado = db.get(Casos, caso.id)
    assert actualizado.ds160_numero_cifrado is None and actualizado.ds160_hash is None


def test_anonimizar_exige_motivo(cliente, admin, db):
    c, _ = una_persona(cliente, admin, db, 'Sinmotivo Anonima Cliente')
    r = cliente.post(f'/api/v1/datos-personales/{c["id"]}/anonimizar', headers=admin,
                     json={'motivo': 'no'})
    assert r.status_code == 422


def test_el_registro_no_repite_los_datos_que_acaba_de_quitar(cliente, admin, db):
    """Una auditoria de anonimizacion que incluya el nombre no anonimiza nada."""
    c, _ = una_persona(cliente, admin, db, 'Rastro Limpio Cliente')
    cliente.post(f'/api/v1/datos-personales/{c["id"]}/anonimizar', headers=admin,
                 json={'motivo': 'Plazo de conservacion cumplido'})

    reg = db.scalars(select(Auditoria).where(Auditoria.operacion == 'anonimizar')
                     .order_by(Auditoria.id.desc())).first()
    assert reg is not None and reg.entidad_id == c['id']
    assert 'Rastro Limpio' not in str(reg.despues), reg.despues
    assert reg.despues['motivo'] == 'Plazo de conservacion cumplido'


# ------------------------------------------------------------- eliminar

def test_no_se_puede_eliminar_a_quien_tiene_contabilidad(cliente, admin, vendedora, db):
    cab, _ = vendedora
    c, _, _ = con_venta(cliente, cab, db, 'Eliminar Conventa Cliente')
    r = cliente.post(f'/api/v1/datos-personales/{c["id"]}/eliminar', headers=admin,
                     json={'motivo': 'La titular pidio que borraran todo'})
    assert r.status_code == 409 and r.json()['codigo'] == 'tiene_contabilidad'
    assert 'anonimizar' in r.json()['detalle']

    db.expire_all()
    assert db.get(Clientes, c['id']) is not None, 'no se borro nada'


def test_eliminar_un_lead_sin_ventas_borra_todo_rastro(cliente, admin, db):
    c, s = una_persona(cliente, admin, db, 'Borrado Total Persona')
    r = cliente.post(f'/api/v1/datos-personales/{c["id"]}/eliminar', headers=admin,
                     json={'motivo': 'Solicitud del titular, nunca fue cliente'})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(Clientes, c['id']) is None
    assert db.get(Solicitantes, s['id']) is None
    # Pero queda constancia de que se hizo.
    reg = db.scalars(select(Auditoria).where(Auditoria.operacion == 'eliminar',
                                             Auditoria.entidad_id == c['id'])).first()
    assert reg is not None


# ------------------------------------------------------------- vencidos

def test_los_vencidos_se_listan_pero_no_se_borran_solos(cliente, admin, db):
    """Un automatismo que borra datos de personas es el que un dia se lleva lo
    que no debia, y aca lo que se pierde no se recupera."""
    c, _ = una_persona(cliente, admin, db, 'Antigua Olvidada Cliente')
    db.execute(text("update clientes set creado_en = now() - interval '7 years', "
                    "ultimo_contacto_en = null where id = :c"), {'c': c['id']})
    db.commit()

    v = cliente.get('/api/v1/datos-personales/vencidos?anios=5', headers=admin).json()
    assert any(x['id'] == c['id'] for x in v), v

    # Listar no borra.
    db.expire_all()
    assert db.get(Clientes, c['id']) is not None

    # Y con un plazo mas largo ya no aparece.
    v10 = cliente.get('/api/v1/datos-personales/vencidos?anios=10', headers=admin).json()
    assert not any(x['id'] == c['id'] for x in v10)


def test_quien_no_puede_borrar_clientes_no_puede_anonimizar(cliente, usuario, db, admin):
    c, _ = una_persona(cliente, admin, db, 'Permiso Anonimizar Cliente')
    cab = entrar(cliente, usuario('comercial'))
    r = cliente.post(f'/api/v1/datos-personales/{c["id"]}/anonimizar', headers=cab,
                     json={'motivo': 'Deberia dar 403'})
    assert r.status_code == 403


# ------------------------- la auditoria no puede sobrevivir a la anonimizacion

def test_la_auditoria_no_guarda_el_nombre_de_quien_despues_se_anonimice(cliente, admin, db):
    """Anonimizar le quita el nombre a la persona en sus tablas. Si la auditoria
    guardo el registro completo de cuando se creo, el nombre sigue ahi y la
    anonimizacion no anonimizo nada.

    Y la auditoria es inalterable a proposito (RNF-05): no se puede limpiar
    despues. O el dato no entra, o se queda para siempre.
    """
    c, s = una_persona(cliente, admin, db, 'Rastreable Enauditoria Persona',
                       documento='55443322', pasaporte='ZZ777111')

    registros = db.scalars(select(Auditoria).where(
        Auditoria.entidad.in_(('clientes', 'solicitantes')),
        Auditoria.entidad_id.in_((c['id'], s['id'])))).all()
    assert registros, 'crear un cliente si se audita'

    for reg in registros:
        texto = f'{reg.antes} {reg.despues}'
        assert 'Rastreable' not in texto, (reg.entidad, reg.operacion, texto[:200])
        assert '55443322' not in texto, 'ni el documento'
        assert 'ZZ777111' not in texto, 'ni el pasaporte'
        assert '3001234567' not in texto, 'ni el telefono'

    # Pero si queda que esos campos se tocaron: la auditoria sigue sirviendo.
    insercion = next(r for r in registros if r.operacion == 'insert')
    assert 'nombre' in (insercion.despues or {}), insercion.despues


def test_el_indice_ciego_tampoco_entra_a_la_auditoria(cliente, admin, db):
    """No guarda el pasaporte, pero deja confirmar que una persona estuvo."""
    from app.core import seguridad as seg
    huella = seg.indice_ciego('QQ333444')
    _, s = una_persona(cliente, admin, db, 'Indice Ciego Persona',
                       documento='77665544', pasaporte='QQ333444')
    regs = db.scalars(select(Auditoria).where(Auditoria.entidad == 'solicitantes',
                                              Auditoria.entidad_id == s['id'])).all()
    for reg in regs:
        assert huella not in f'{reg.antes} {reg.despues}', reg.despues


def test_el_catalogo_si_se_lee_entero_porque_no_es_un_dato_personal(cliente, admin, db):
    """Ocultar por nombre de campo y no por entidad dejaria sin poder leer quien
    renombro un servicio o un rol, que es justo para lo que sirve la auditoria."""
    from app.services.auditoria import sin_datos_personales
    assert sin_datos_personales('servicios', {'nombre': 'Asesoría USA'}) == {
        'nombre': 'Asesoría USA'}
    assert sin_datos_personales('clientes', {'nombre': 'Quien Sea'})['nombre'] != 'Quien Sea'
