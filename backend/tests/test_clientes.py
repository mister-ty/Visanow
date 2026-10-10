"""Actividades 2.3 y 2.4 — clientes, grupos, solicitantes y duplicados
(RF-001, RF-002, RF-003, RF-004, RF-029, RNF-04)."""
import pytest
from sqlalchemy import select, text

from app.core import seguridad as seg
from app.models.esquema import Auditoria, Clientes, Fusiones, Negocios, Solicitantes
from app.services import duplicados, personas
from tests.conftest import entrar

CLIENTES = '/api/v1/clientes'


@pytest.fixture
def comercial(cliente, usuario):
    return entrar(cliente, usuario('comercial'))


@pytest.fixture
def admin(cliente, usuario):
    return entrar(cliente, usuario('administradora'))


def crear_cliente(cliente, cab, **datos):
    r = cliente.post(CLIENTES, headers=cab, json={'nombre': 'Cliente de prueba', **datos})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ clientes

def test_crear_cliente_y_ver_su_ficha(cliente, comercial):
    creado = crear_cliente(cliente, comercial, nombre='Aura Isabel Basante',
                           tipo_documento='CC', numero_documento='1020304050',
                           telefono='+57 310 517 7800', email='aura@ejemplo.com', ciudad='Bogotá')
    assert creado['nombre'] == 'Aura Isabel Basante' and creado['archivado'] is False
    ficha = cliente.get(f"{CLIENTES}/{creado['id']}", headers=comercial).json()
    assert ficha['numero_documento'] == '1020304050' and ficha['grupos'] == []


def test_el_documento_repetido_se_rechaza(cliente, comercial):
    crear_cliente(cliente, comercial, nombre='Juan Pérez', tipo_documento='CC', numero_documento='999888777')
    r = cliente.post(CLIENTES, headers=comercial,
                     json={'nombre': 'Juan Perez', 'tipo_documento': 'CC', 'numero_documento': '999888777'})
    assert r.status_code == 409 and r.json()['codigo'] == 'documento_duplicado'


def test_busqueda_encuentra_sin_tildes_y_con_el_telefono_en_otro_formato(cliente, comercial):
    crear_cliente(cliente, comercial, nombre='María José Gómez', telefono='+57 310-777-8899',
                  numero_documento='55667788')
    for texto in ('maria jose', 'MARIA JOSE GOMEZ', 'gomez', '3107778899', '55667788'):
        encontrados = cliente.get(CLIENTES, headers=comercial, params={'texto': texto}).json()
        assert encontrados['total'] >= 1, f'no encontró con «{texto}»'
        assert any('Gómez' in c['nombre'] for c in encontrados['items'])


def test_archivar_saca_de_la_lista_pero_conserva_la_ficha(cliente, comercial):
    creado = crear_cliente(cliente, comercial, nombre='Cliente Archivable')
    cliente.post(f"{CLIENTES}/{creado['id']}/archivar", headers=comercial, params={'archivado': True})
    listado = cliente.get(CLIENTES, headers=comercial, params={'texto': 'Archivable'}).json()
    assert listado['total'] == 0
    con_archivados = cliente.get(CLIENTES, headers=comercial,
                                 params={'texto': 'Archivable', 'archivados': True}).json()
    assert con_archivados['total'] == 1
    assert cliente.get(f"{CLIENTES}/{creado['id']}", headers=comercial).status_code == 200


# --------------------------------------------------- grupos y solicitantes

def test_un_grupo_con_dos_solicitantes_sin_repetir_datos(cliente, comercial):
    """Criterio de aceptación 1: la familia se registra una vez, con el correo
    del contacto, y cada persona conserva su pasaporte."""
    contacto = crear_cliente(cliente, comercial, nombre='Aura Basante', email='aura@ejemplo.com',
                             telefono='3105177800')
    grupo = cliente.post('/api/v1/grupos', headers=comercial,
                         json={'nombre': 'Familia Basante Díaz', 'cliente_contacto_id': contacto['id']})
    assert grupo.status_code == 201
    grupo_id = grupo.json()['id']
    for nombre, pasaporte, relacion in [('Aura Isabel Basante', 'BH371978', 'titular'),
                                        ('Joan David Díaz Garzón', 'BA944508', 'hijo')]:
        r = cliente.post('/api/v1/solicitantes', headers=comercial,
                         json={'grupo_id': grupo_id, 'nombre': nombre, 'pasaporte': pasaporte,
                               'relacion_con_cliente': relacion})
        assert r.status_code == 201, r.text
        assert r.json()['pasaporte'] == '••••1978' if pasaporte.endswith('1978') else True

    ficha = cliente.get(f"{CLIENTES}/{contacto['id']}", headers=comercial).json()
    assert len(ficha['grupos']) == 1 and len(ficha['grupos'][0]['solicitantes']) == 2
    assert len(ficha['solicitantes']) == 2


def test_el_pasaporte_se_guarda_cifrado_y_se_puede_buscar(cliente, comercial, db):
    contacto = crear_cliente(cliente, comercial, nombre='Contacto Pasaporte')
    r = cliente.post('/api/v1/solicitantes', headers=comercial,
                     json={'cliente_id': contacto['id'], 'nombre': 'Persona Uno', 'pasaporte': 'AB1234567'})
    solicitante_id = r.json()['id']
    assert r.json()['pasaporte'] == '•••••4567', 'la API no debe devolver el pasaporte completo'

    guardado = db.get(Solicitantes, solicitante_id)
    assert guardado.pasaporte != 'AB1234567' and seg.descifrar(guardado.pasaporte) == 'AB1234567'

    # Se busca por el valor exacto aunque la columna esté cifrada (RF-029)
    hallados = cliente.get('/api/v1/solicitantes/buscar', headers=comercial,
                           params={'pasaporte': 'ab 1234567'}).json()
    assert [s['id'] for s in hallados] == [solicitante_id]


def test_ver_el_pasaporte_completo_queda_auditado(cliente, comercial, db, usuario):
    contacto = crear_cliente(cliente, comercial, nombre='Contacto Auditoría')
    s = cliente.post('/api/v1/solicitantes', headers=comercial,
                     json={'cliente_id': contacto['id'], 'nombre': 'Persona Dos',
                           'pasaporte': 'CD7654321'}).json()
    r = cliente.get(f"/api/v1/solicitantes/{s['id']}/pasaporte", headers=comercial)
    assert r.status_code == 200 and r.json()['pasaporte'] == 'CD7654321'
    assert db.scalar(select(Auditoria).where(Auditoria.entidad == 'solicitantes',
                                             Auditoria.entidad_id == s['id'],
                                             Auditoria.operacion == 'ver_pasaporte'))


def test_un_solicitante_no_puede_quedar_suelto(cliente, comercial):
    r = cliente.post('/api/v1/solicitantes', headers=comercial, json={'nombre': 'Sin dueño'})
    assert r.status_code == 422


# ----------------------------------------------------------------- duplicados

def test_el_documento_igual_es_duplicado_de_confianza_alta(cliente, comercial):
    crear_cliente(cliente, comercial, nombre='Pedro Ramírez', tipo_documento='CC',
                  numero_documento='11223344')
    r = cliente.post(f'{CLIENTES}/verificar-duplicados', headers=comercial,
                     json={'nombre': 'P. Ramirez', 'numero_documento': '11223344'})
    coincidencias = r.json()
    assert coincidencias and coincidencias[0]['confianza'] == 'alta'
    assert 'documento' in coincidencias[0]['criterios']


def test_el_nombre_casi_identico_se_detecta_aunque_cambien_tildes(cliente, comercial):
    crear_cliente(cliente, comercial, nombre='Andrés Felipe Restrepo Gil')
    r = cliente.post(f'{CLIENTES}/verificar-duplicados', headers=comercial,
                     json={'nombre': 'ANDRES FELIPE RESTREPO GIL'})
    assert r.json()[0]['confianza'] == 'alta'


def test_la_familia_que_comparte_correo_no_se_marca_como_duplicada(cliente, comercial):
    """La administradora confirmó que el grupo familiar se registra con un solo
    correo. Si el correo pesara como el documento, el sistema propondría fusionar
    a un padre con su hijo."""
    crear_cliente(cliente, comercial, nombre='Carlos Medina Ruiz', email='familia.medina@ejemplo.com')
    r = cliente.post(f'{CLIENTES}/verificar-duplicados', headers=comercial,
                     json={'nombre': 'Valentina Medina Ruiz', 'email': 'familia.medina@ejemplo.com'})
    coincidencias = r.json()
    assert coincidencias, 'debe avisar, pero con confianza baja'
    assert coincidencias[0]['confianza'] == 'baja'
    assert coincidencias[0]['posible_familiar'] is True
    assert 'puede ser un familiar' in coincidencias[0]['explicacion']


def test_el_telefono_pesa_segun_si_es_la_misma_persona(cliente, comercial):
    """Mismo teléfono con el mismo nombre de pila es un duplicado; con otro
    nombre de pila es, casi siempre, un familiar que usa el mismo número."""
    crear_cliente(cliente, comercial, nombre='Rodrigo Enrique Vidal', telefono='3173739259')

    mismo = cliente.post(f'{CLIENTES}/verificar-duplicados', headers=comercial,
                         json={'nombre': 'Rodrigo Vidal', 'telefono': '+57 317 373 9259'}).json()
    assert mismo[0]['confianza'] == 'alta' and 'telefono' in mismo[0]['criterios']

    pariente = cliente.post(f'{CLIENTES}/verificar-duplicados', headers=comercial,
                            json={'nombre': 'Daniela Vidal', 'telefono': '317 3739259'}).json()
    assert pariente[0]['confianza'] == 'baja' and pariente[0]['posible_familiar'] is True


def test_el_pasaporte_igual_delata_al_mismo_cliente(cliente, comercial):
    contacto = crear_cliente(cliente, comercial, nombre='Dueño del Pasaporte')
    cliente.post('/api/v1/solicitantes', headers=comercial,
                 json={'cliente_id': contacto['id'], 'nombre': 'Viajero', 'pasaporte': 'XY9999999'})
    r = cliente.post(f'{CLIENTES}/verificar-duplicados', headers=comercial,
                     json={'nombre': 'Nombre Totalmente Distinto', 'pasaporte': 'XY9999999'})
    assert r.json()[0]['cliente_id'] == contacto['id'] and r.json()[0]['confianza'] == 'alta'


# -------------------------------------------------------------------- fusión

def test_la_fusion_mueve_todo_y_deja_constancia(cliente, admin, comercial, db):
    conservado = crear_cliente(cliente, admin, nombre='Laura Gómez', telefono='3001112233')
    absorbido = crear_cliente(cliente, admin, nombre='Laura Gomez', tipo_documento='CC',
                              numero_documento='7778889', email='laura@ejemplo.com')
    grupo = cliente.post('/api/v1/grupos', headers=admin,
                         json={'nombre': 'Grupo de Laura', 'cliente_contacto_id': absorbido['id']}).json()
    cliente.post('/api/v1/solicitantes', headers=admin,
                 json={'grupo_id': grupo['id'], 'nombre': 'Laura Gomez'})

    r = cliente.post(f"{CLIENTES}/{conservado['id']}/fusionar", headers=admin,
                     json={'absorbido_id': absorbido['id'], 'criterio': 'nombre'})
    assert r.status_code == 200, r.text
    assert r.json()['movidos']['grupos'] == 1

    ficha = cliente.get(f"{CLIENTES}/{conservado['id']}", headers=admin).json()
    assert len(ficha['grupos']) == 1, 'el grupo debe quedar colgando de la ficha que sobrevive'
    # Los datos que la ficha conservada no tenía se completan
    assert ficha['numero_documento'] == '7778889' and ficha['email'] == 'laura@ejemplo.com'

    db.expire_all()
    absorbida = db.get(Clientes, absorbido['id'])
    assert absorbida.fusionado_en_id == conservado['id'] and absorbida.archivado
    assert absorbida.numero_documento is None, 'el documento se libera para no chocar con el índice único'
    registro = db.scalar(select(Fusiones).where(Fusiones.id_absorbido == absorbido['id']))
    assert registro.snapshot['numero_documento'] == '7778889' and registro.criterio == 'nombre'
    assert db.scalar(select(Auditoria).where(Auditoria.entidad == 'clientes',
                                             Auditoria.operacion == 'fusion',
                                             Auditoria.entidad_id == conservado['id']))
    # La ficha absorbida ya no se abre ni aparece en búsquedas
    assert cliente.get(f"{CLIENTES}/{absorbido['id']}", headers=admin).status_code == 409


def test_no_se_puede_fusionar_dos_veces_ni_consigo_misma(cliente, admin):
    a = crear_cliente(cliente, admin, nombre='Ficha A')
    b = crear_cliente(cliente, admin, nombre='Ficha B')
    cliente.post(f"{CLIENTES}/{a['id']}/fusionar", headers=admin, json={'absorbido_id': b['id']})
    assert cliente.post(f"{CLIENTES}/{a['id']}/fusionar", headers=admin,
                        json={'absorbido_id': b['id']}).status_code == 409
    assert cliente.post(f"{CLIENTES}/{a['id']}/fusionar", headers=admin,
                        json={'absorbido_id': a['id']}).status_code == 422


def test_comercial_no_puede_fusionar(cliente, comercial, admin):
    a = crear_cliente(cliente, admin, nombre='Ficha C')
    b = crear_cliente(cliente, admin, nombre='Ficha D')
    r = cliente.post(f"{CLIENTES}/{a['id']}/fusionar", headers=comercial, json={'absorbido_id': b['id']})
    assert r.status_code == 403 and r.json()['codigo'] == 'sin_permiso'


def test_la_fusion_conoce_todas_las_tablas_que_apuntan_a_un_cliente(db):
    """Si mañana alguien agrega una tabla con cliente_id y no la registra en
    duplicados.REFERENCIAS, la fusión dejaría filas apuntando a una ficha
    archivada. Esta prueba lo detecta comparando contra la base."""
    reales = {(t, c) for t, c in db.execute(text("""
        select c.conrelid::regclass::text, a.attname
        from pg_constraint c
        join unnest(c.conkey) with ordinality k(attnum, ord) on true
        join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k.attnum
        where c.contype = 'f' and c.confrelid = 'clientes'::regclass
          and not (c.conrelid = 'clientes'::regclass and a.attname = 'fusionado_en_id')
    """))}
    cubiertas = {(modelo.__tablename__, columna) for modelo, columna in duplicados.REFERENCIAS}
    assert reales == cubiertas, f'faltan por mover: {reales - cubiertas}'


def test_el_servicio_de_duplicados_ignora_las_fichas_ya_fusionadas(cliente, admin, db, usuario):
    a = crear_cliente(cliente, admin, nombre='Miriam Castillo Vega')
    b = crear_cliente(cliente, admin, nombre='Miriam Castillo Vega')
    cliente.post(f"{CLIENTES}/{a['id']}/fusionar", headers=admin, json={'absorbido_id': b['id']})
    encontradas = duplicados.buscar(db, nombre='Miriam Castillo Vega')
    assert [c.cliente_id for c in encontradas] == [a['id']]


def test_personas_listar_pagina(cliente, comercial, db, usuario):
    for i in range(7):
        personas.crear(db, usuario('comercial').u, {'nombre': f'Paginado {i:02d} Apellido'})
    total, primera = personas.listar(db, texto_busqueda='Paginado', pagina=1, tamano=5)
    _, segunda = personas.listar(db, texto_busqueda='Paginado', pagina=2, tamano=5)
    assert total == 7 and len(primera) == 5 and len(segunda) == 2


def test_el_pais_el_canal_y_el_consentimiento_se_guardan_y_se_leen(cliente, db, usuario):
    """RF-001 nombra identificación, contacto, ciudad, país, canal y consentimiento.
    De esos, país, canal y consentimiento no tenían ninguna prueba: el canal es
    con lo que se sabe qué publicidad trae clientes, y el consentimiento es dato
    de tratamiento de datos personales."""
    from sqlalchemy import select

    from app.models.esquema import Canales, Paises

    cab = entrar(cliente, usuario('comercial'))
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'CO'))
    canal = db.scalar(select(Canales.id).where(Canales.codigo == 'instagram'))

    r = cliente.post('/api/v1/clientes', headers=cab, json={
        'nombre': 'Camila Ospina Vélez', 'ciudad': 'Medellín',
        'pais_id': pais, 'canal_id': canal, 'consentimiento': True})
    assert r.status_code == 201, r.text
    ficha = r.json()
    assert ficha['pais_id'] == pais and ficha['canal_id'] == canal
    assert ficha['consentimiento'] is True and ficha['consentimiento_fecha'] is not None,         'autorizar el tratamiento tiene que dejar la fecha'

    # y se leen de vuelta en la ficha
    leida = cliente.get(f'/api/v1/clientes/{ficha["id"]}', headers=cab).json()
    assert (leida['pais_id'], leida['canal_id']) == (pais, canal)

    # el catálogo trae los canales para poder mostrar el nombre y no el número
    catalogos = cliente.get('/api/v1/catalogos', headers=cab).json()
    assert canal in [c['id'] for c in catalogos['canales']]
    assert any(c['codigo'] == 'instagram' for c in catalogos['canales'])


# ------------------------------- mover personas entre grupos y corregir grupos

def test_una_persona_se_puede_mover_a_un_grupo_sin_perder_su_tramite(cliente, usuario):
    """La familia casi nunca se conoce el primer día: el cliente llega solo y dos
    semanas después dice que viajan los tres. Sin poder mover a la persona habría
    que borrarla y volverla a crear, perdiendo su trámite."""
    cab = entrar(cliente, usuario('comercial'))
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': 'Marta Isaza Gil'}).json()
    s = cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'cliente_id': c['id'], 'nombre': 'Marta Isaza Gil'}).json()
    g = cliente.post('/api/v1/grupos', headers=cab,
                     json={'cliente_contacto_id': c['id'], 'nombre': 'Familia Isaza'}).json()

    r = cliente.patch(f'/api/v1/solicitantes/{s["id"]}', headers=cab, json={'grupo_id': g['id']})
    assert r.status_code == 200, r.text
    assert r.json()['grupo_id'] == g['id']
    assert r.json()['cliente_id'] is None, 'al entrar al grupo deja de colgar del cliente'

    # No aparece dos veces en la ficha
    ficha = cliente.get(f'/api/v1/clientes/{c["id"]}', headers=cab).json()
    sueltos = [x for x in ficha['solicitantes'] if not x['grupo_id']]
    assert sueltos == []
    assert [x['id'] for x in ficha['grupos'][0]['solicitantes']] == [s['id']]


def test_una_persona_se_puede_sacar_del_grupo_pero_no_quedar_suelta(cliente, usuario):
    cab = entrar(cliente, usuario('comercial'))
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': 'Hugo Arenas Mora'}).json()
    g = cliente.post('/api/v1/grupos', headers=cab,
                     json={'cliente_contacto_id': c['id'], 'nombre': 'Familia Arenas'}).json()
    s = cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'grupo_id': g['id'], 'nombre': 'Hugo Arenas Mora'}).json()

    # Sacarlo del grupo exige decir de qué cliente queda colgando
    r = cliente.patch(f'/api/v1/solicitantes/{s["id"]}', headers=cab,
                      json={'grupo_id': None, 'cliente_id': None})
    assert r.status_code == 422
    assert 'grupo o a un cliente' in r.json()['detalle']

    r = cliente.patch(f'/api/v1/solicitantes/{s["id"]}', headers=cab,
                      json={'grupo_id': None, 'cliente_id': c['id']})
    assert r.status_code == 200 and r.json()['cliente_id'] == c['id']


def test_un_grupo_mal_escrito_se_puede_corregir(cliente, usuario):
    """Hasta ahora el grupo era inmutable: un nombre mal escrito o un contacto
    equivocado solo se arreglaban con SQL."""
    cab = entrar(cliente, usuario('comercial'))
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': 'Rosa Mejía Tobón'}).json()
    otro = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': 'Jorge Mejía Tobón'}).json()
    g = cliente.post('/api/v1/grupos', headers=cab,
                     json={'cliente_contacto_id': c['id'], 'nombre': 'Familia Megia'}).json()

    r = cliente.patch(f'/api/v1/grupos/{g["id"]}', headers=cab,
                      json={'nombre': 'Familia Mejía', 'cliente_contacto_id': otro['id'],
                            'observaciones': 'Paga Jorge'})
    assert r.status_code == 200, r.text
    assert r.json()['nombre'] == 'Familia Mejía'
    assert r.json()['cliente_contacto_id'] == otro['id']

    # El grupo se mudó: ahora cuelga del otro cliente
    assert cliente.get(f'/api/v1/clientes/{otro["id"]}', headers=cab).json()['grupos'][0]['id'] == g['id']
    assert cliente.get(f'/api/v1/clientes/{c["id"]}', headers=cab).json()['grupos'] == []


def test_editar_un_grupo_queda_en_la_auditoria(cliente, db, usuario):
    from sqlalchemy import select

    from app.models.esquema import Auditoria

    cab = entrar(cliente, usuario('comercial'))
    c = cliente.post('/api/v1/clientes', headers=cab, json={'nombre': 'Elsa Prada Ruiz'}).json()
    g = cliente.post('/api/v1/grupos', headers=cab,
                     json={'cliente_contacto_id': c['id'], 'nombre': 'Familia Prada'}).json()
    cliente.patch(f'/api/v1/grupos/{g["id"]}', headers=cab, json={'nombre': 'Familia Prada Ruiz'})
    registro = db.scalar(select(Auditoria).where(Auditoria.entidad == 'grupos',
                                                 Auditoria.entidad_id == g['id'],
                                                 Auditoria.operacion == 'update'))
    assert registro is not None
    # Queda constancia de que cambio el nombre, pero no el nombre: el de un grupo
    # es el apellido de una familia, y la auditoria es inalterable -lo que entre
    # ahi sobrevive a cualquier anonimizacion posterior-.
    assert 'nombre' in registro.despues
    assert 'Prada' not in str(registro.despues), registro.despues
