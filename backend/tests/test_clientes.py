"""Actividades 2.3 y 2.4 — clientes, grupos, solicitantes y duplicados
(RF-001, RF-002, RF-003, RF-004, RF-029, RNF-04)."""
import pytest
from sqlalchemy import select, text

from app.core import seguridad as seg
from app.models.esquema import Auditoria, Clientes, Fusiones, Solicitantes
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
        # El assert de antes era `== '••••1978' if ... else True`, que para la
        # segunda persona comprobaba que True fuera verdad. Enmascarado desde
        # que se guarda: la API nunca devuelve el pasaporte entero.
        assert r.json()['pasaporte'] == '•' * (len(pasaporte) - 4) + pasaporte[-4:]

    ficha = cliente.get(f"{CLIENTES}/{contacto['id']}", headers=comercial).json()
    assert len(ficha['grupos']) == 1 and len(ficha['grupos'][0]['solicitantes']) == 2
    assert len(ficha['solicitantes']) == 2
    # La «relación» de cada integrante es parte de RF-003 y se enviaba desde
    # acá, pero nadie comprobaba que volviera: un PATCH que la descartara habría
    # pasado desapercibido.
    assert {s['nombre']: s['relacion_con_cliente']
            for s in ficha['grupos'][0]['solicitantes']} == {
        'Aura Isabel Basante': 'titular', 'Joan David Díaz Garzón': 'hijo'}


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


# ------------------------------------------- editar un cliente de verdad (RF-001)

def test_editar_un_cliente_guarda_lo_que_se_cambio(cliente, db, usuario):
    """No habia ninguna prueba de editar un cliente. La unica que tocaba un
    PATCH comprobaba el renglon de auditoria y nunca volvia a leer la ficha, asi
    que un PATCH que no guardara nada habria pasado desapercibido."""
    cab = entrar(cliente, usuario('administradora'))
    c = cliente.post('/api/v1/clientes', headers=cab,
                     json={'nombre': 'Editable Prueba Cliente'}).json()

    r = cliente.patch(f'/api/v1/clientes/{c["id"]}', headers=cab, json={
        'ciudad': 'Barranquilla', 'telefono': '3012223344',
        'email': 'editable@ejemplo.com',
        'observaciones': 'Prefiere que la llamen después de las 6'})
    assert r.status_code == 200, r.text

    leido = cliente.get(f'/api/v1/clientes/{c["id"]}', headers=cab).json()
    assert leido['ciudad'] == 'Barranquilla'
    assert leido['email'] == 'editable@ejemplo.com'
    assert leido['observaciones'] == 'Prefiere que la llamen después de las 6'


def test_las_observaciones_se_pueden_escribir_al_crear(cliente, db, usuario):
    """La pantalla de «Nuevo cliente» no tenia el campo, aunque la API si lo
    acepta: habia que guardar la ficha y volver a abrirla en Editar para poder
    escribir una nota. Era un formulario copiado que se separo de su copia.
    """
    cab = entrar(cliente, usuario('administradora'))
    r = cliente.post('/api/v1/clientes', headers=cab, json={
        'nombre': 'Conobservacion Alcrear Cliente',
        'observaciones': 'Llega por recomendación de Angie'})
    assert r.status_code == 201, r.text

    leido = cliente.get(f'/api/v1/clientes/{r.json()["id"]}', headers=cab).json()
    assert leido['observaciones'] == 'Llega por recomendación de Angie'


def test_revocar_el_consentimiento_borra_su_fecha(cliente, db, usuario):
    """Si no, queda la fecha de una autorizacion que ya no esta vigente, y
    cualquiera que mire la ficha creeria que el cliente sigue autorizando."""
    cab = entrar(cliente, usuario('administradora'))
    c = cliente.post('/api/v1/clientes', headers=cab, json={
        'nombre': 'Revocada Consentimiento Cliente', 'consentimiento': True}).json()
    assert c['consentimiento_fecha'] is not None, 'al autorizar se guarda la fecha'

    cliente.patch(f'/api/v1/clientes/{c["id"]}', headers=cab, json={'consentimiento': False})
    leido = cliente.get(f'/api/v1/clientes/{c["id"]}', headers=cab).json()
    assert leido['consentimiento'] is False
    assert leido['consentimiento_fecha'] is None, (
        'quedo la fecha de una autorizacion revocada')


# ===========================================================================
# RF-002 · el pasaporte al registrar, y unir dos personas repetidas
# ===========================================================================

def _persona(cliente, cab, **datos):
    r = cliente.post('/api/v1/solicitantes', headers=cab, json=datos)
    assert r.status_code == 201, r.text
    return r.json()


def test_la_ficha_ofrece_sus_parecidos_para_fusionar(cliente, comercial):
    """La ruta de la que cuelga la única pantalla donde se fusiona no tenía
    ninguna prueba. Si se rompiera, la ficha dejaría de ofrecer la unión y nadie
    se enteraría hasta ver el saldo de un cliente repartido entre dos fichas.

    Fija también que una ficha no se propone a sí misma: el pasaporte que se
    compara es el de SUS propias personas, y sin excluirla cada ficha con
    pasaporte aparecería como su propio duplicado.
    """
    primera = crear_cliente(cliente, comercial, nombre='Noelia Serrano Pabón',
                            telefono='3156660011')
    _persona(cliente, comercial, cliente_id=primera['id'], nombre='Noelia Serrano Pabón',
             pasaporte='NS1100220')
    segunda = crear_cliente(cliente, comercial, nombre='Noelia Serrano', telefono='315 666 0011')

    r = cliente.get(f"{CLIENTES}/{segunda['id']}/duplicados", headers=comercial)
    assert r.status_code == 200, r.text
    hallados = r.json()
    assert [c['cliente_id'] for c in hallados] == [primera['id']]
    assert hallados[0]['confianza'] == 'alta' and 'telefono' in hallados[0]['criterios']

    propios = cliente.get(f"{CLIENTES}/{primera['id']}/duplicados", headers=comercial).json()
    assert primera['id'] not in [c['cliente_id'] for c in propios]


def test_unir_dos_personas_repetidas_mueve_sus_tramites_y_deja_constancia(cliente, admin, db):
    """RF-002 pide fusión y hasta ahora solo se podían unir CLIENTES.

    La misma persona entra dos veces al mismo grupo —una al cotizar, de memoria,
    y otra cuando llega el pasaporte— y cada copia se queda con un pedazo de la
    historia: el trámite en una y los documentos en la otra. Sin poder unirlas,
    la única salida era borrar una, que es perder lo que llevaba.
    """
    from app.models.esquema import Paises

    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    c = crear_cliente(cliente, admin, nombre='Elena Pardo Nieto')
    g = cliente.post('/api/v1/grupos', headers=admin,
                     json={'cliente_contacto_id': c['id'], 'nombre': 'Familia Pardo'}).json()
    queda = _persona(cliente, admin, grupo_id=g['id'], nombre='Elena Pardo Nieto')
    repetida = _persona(cliente, admin, grupo_id=g['id'], nombre='Elena Pardo N.',
                        tipo_documento='CC', numero_documento='43778899',
                        telefono='3182223344', relacion_con_cliente='titular')
    caso = cliente.post('/api/v1/casos', headers=admin, json={
        'solicitante_id': repetida['id'], 'pais_id': pais,
        'proxima_accion': 'Pedir documentos al cliente'})
    assert caso.status_code == 201, caso.text
    caso = caso.json()

    r = cliente.post(f"/api/v1/solicitantes/{queda['id']}/fusionar", headers=admin,
                     json={'absorbido_id': repetida['id'], 'criterio': 'nombre'})
    assert r.status_code == 200, r.text
    assert r.json()['movidos']['casos'] == 1

    # El trámite quedó colgando de la persona que sobrevive
    assert cliente.get(f"/api/v1/casos/{caso['id']}",
                       headers=admin).json()['solicitante_id'] == queda['id']

    # Y los datos que solo tenía la repetida se completan en la que queda
    ficha = cliente.get(f"{CLIENTES}/{c['id']}", headers=admin).json()
    assert [s['id'] for s in ficha['grupos'][0]['solicitantes']] == [queda['id']], \
        'la absorbida sale de la ficha'
    sobrevive = ficha['grupos'][0]['solicitantes'][0]
    assert sobrevive['numero_documento'] == '43778899'
    assert sobrevive['telefono'] == '3182223344'
    assert sobrevive['relacion_con_cliente'] == 'titular'

    db.expire_all()
    absorbida = db.get(Solicitantes, repetida['id'])
    assert absorbida.fusionado_en_id == queda['id']
    registro = db.scalar(select(Fusiones).where(Fusiones.entidad == 'solicitante',
                                                Fusiones.id_absorbido == repetida['id']))
    assert registro is not None and registro.criterio == 'nombre'
    assert registro.snapshot['numero_documento'] == '43778899', 'queda la copia íntegra'
    assert db.scalar(select(Auditoria).where(Auditoria.entidad == 'solicitantes',
                                             Auditoria.operacion == 'fusion',
                                             Auditoria.entidad_id == queda['id']))


def test_solo_la_administradora_puede_unir_dos_personas(cliente, admin, comercial):
    """Unir dos personas mueve trámites e historial de una a otra: RF-002 pide
    que la fusión sea autorizada. Comercial crea y corrige personas todos los
    días, y eso no incluye unirlas."""
    c = crear_cliente(cliente, admin, nombre='Hernán Quiroga Lemus')
    a = _persona(cliente, admin, cliente_id=c['id'], nombre='Hernán Quiroga Lemus')
    b = _persona(cliente, admin, cliente_id=c['id'], nombre='Hernán Quiroga L.')

    r = cliente.post(f"/api/v1/solicitantes/{a['id']}/fusionar", headers=comercial,
                     json={'absorbido_id': b['id']})
    assert r.status_code == 403, r.text
    assert r.json()['codigo'] == 'sin_permiso'


def test_unir_personas_no_mueve_tramites_que_no_se_pueden_ver(cliente, db, usuario, admin):
    """El alcance (RNF-03) otra vez, pero al ESCRIBIR: unir dos personas mueve
    sus trámites de una a otra, así que quien tiene «solo lo asignado» no puede
    unirlas si con eso arrastra un trámite que no le dejan ni mirar. La
    comprobación vive en el servicio: puesta en la ruta, se saltaría llamando la
    API directo."""
    from app.models.esquema import Paises
    from app.services import usuarios as servicio_usuarios

    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    jefa = usuario('administradora')
    servicio_usuarios.editar(db, usuario('administradora').u, jefa.u.id, alcance='asignados')
    db.commit()

    c = crear_cliente(cliente, admin, nombre='Celina Mosquera Pino')
    queda = _persona(cliente, admin, cliente_id=c['id'], nombre='Celina Mosquera Pino')
    sale = _persona(cliente, admin, cliente_id=c['id'], nombre='Celina Mosquera P.')
    otra = usuario('operaciones')
    abierto = cliente.post('/api/v1/casos', headers=entrar(cliente, otra), json={
        'solicitante_id': sale['id'], 'pais_id': pais, 'responsable_id': otra.u.id,
        'proxima_accion': 'Pedir documentos al cliente'})
    assert abierto.status_code == 201, abierto.text

    r = cliente.post(f"/api/v1/solicitantes/{queda['id']}/fusionar",
                     headers=entrar(cliente, jefa), json={'absorbido_id': sale['id']})
    assert r.status_code == 403, r.text
    assert r.json()['codigo'] == 'sin_alcance'


def test_al_unir_dos_personas_el_pasaporte_pasa_a_la_que_queda(cliente, admin, db):
    """El pasaporte tiene índice único: mientras la ficha absorbida lo conserve,
    ese número sigue ocupado y el sistema lo rechaza sin poder explicar dónde
    está. Por eso la unión lo traslada y lo libera en la que se archiva, igual
    que el documento del cliente. El valor completo queda en la copia íntegra.
    """
    c = crear_cliente(cliente, admin, nombre='Bruno Salcedo Agudelo')
    queda = _persona(cliente, admin, cliente_id=c['id'], nombre='Bruno Salcedo Agudelo')
    sale = _persona(cliente, admin, cliente_id=c['id'], nombre='Bruno Salcedo A.',
                    pasaporte='BS9080706')

    r = cliente.post(f"/api/v1/solicitantes/{queda['id']}/fusionar", headers=admin,
                     json={'absorbido_id': sale['id'], 'criterio': 'pasaporte'})
    assert r.status_code == 200, r.text

    ficha = cliente.get(f"{CLIENTES}/{c['id']}", headers=admin).json()
    assert [s['pasaporte'] for s in ficha['solicitantes']] == ['•••••0706']

    # Buscar ese pasaporte lleva a la persona viva, no a la archivada
    hallados = cliente.get('/api/v1/solicitantes/buscar', headers=admin,
                           params={'pasaporte': 'BS9080706'}).json()
    assert [s['id'] for s in hallados] == [queda['id']]

    db.expire_all()
    absorbida = db.get(Solicitantes, sale['id'])
    assert absorbida.pasaporte is None and absorbida.pasaporte_indice is None, \
        'el índice único se libera, o ese número queda ocupado para siempre'
    registro = db.scalar(select(Fusiones).where(Fusiones.entidad == 'solicitante',
                                                Fusiones.id_absorbido == sale['id']))
    assert seg.descifrar(registro.snapshot['pasaporte']) == 'BS9080706'


def test_no_se_unen_dos_personas_de_clientes_distintos(cliente, admin):
    """Unirlas movería los trámites de un cliente al otro y la ficha del primero
    se quedaría sin ellos sin que nadie lo hubiera pedido. Si de verdad es el
    mismo cliente, primero se unen las dos fichas de cliente —que para eso está
    la otra fusión— y las personas quedan ya bajo el mismo dueño."""
    uno = crear_cliente(cliente, admin, nombre='Rafael Ocampo Cano')
    otro = crear_cliente(cliente, admin, nombre='Rafaela Ocampo Cano')
    a = _persona(cliente, admin, cliente_id=uno['id'], nombre='Rafael Ocampo Cano')
    b = _persona(cliente, admin, cliente_id=otro['id'], nombre='Rafael Ocampo C.')

    r = cliente.post(f"/api/v1/solicitantes/{a['id']}/fusionar", headers=admin,
                     json={'absorbido_id': b['id']})
    assert r.status_code == 409, r.text
    assert r.json()['codigo'] == 'otro_cliente'


def test_la_union_de_personas_conoce_todas_las_tablas_que_apuntan_a_un_solicitante(db):
    """La hermana de la prueba de clientes: si mañana alguien agrega una tabla
    con solicitante_id y no la registra, la unión dejaría filas apuntando a una
    persona archivada y su trámite se perdería de vista."""
    reales = {(t, c) for t, c in db.execute(text("""
        select c.conrelid::regclass::text, a.attname
        from pg_constraint c
        join unnest(c.conkey) with ordinality k(attnum, ord) on true
        join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k.attnum
        where c.contype = 'f' and c.confrelid = 'solicitantes'::regclass
          and not (c.conrelid = 'solicitantes'::regclass and a.attname = 'fusionado_en_id')
    """))}
    cubiertas = {(modelo.__tablename__, columna)
                 for modelo, columna in duplicados.REFERENCIAS_SOLICITANTE}
    assert reales == cubiertas, f'faltan por mover: {reales - cubiertas}'


# ===========================================================================
# RF-003 · grupos familiares o de viaje, con su contacto principal
# ===========================================================================

def test_un_grupo_dice_si_es_familiar_o_de_viaje(cliente, comercial):
    """RF-003 habla de grupos «familiares o de viaje» y la tabla no tenía con
    qué distinguirlos: el tipo quedaba en el nombre que alguien escribiera. Sin
    el dato no se puede saber cuánto de la operación es familia —que viaja con
    menores y renueva junta— y cuánto son grupos de viaje.
    """
    c = crear_cliente(cliente, comercial, nombre='Tatiana Bedoya Ríos')
    r = cliente.post('/api/v1/grupos', headers=comercial, json={
        'nombre': 'Promoción 2026', 'cliente_contacto_id': c['id'], 'tipo': 'viaje'})
    assert r.status_code == 201, r.text
    assert r.json()['tipo'] == 'viaje'

    # El que no lo diga es familiar: es el caso de siempre en VisaNow
    otro = cliente.post('/api/v1/grupos', headers=comercial, json={
        'nombre': 'Familia Bedoya', 'cliente_contacto_id': c['id']}).json()
    assert otro['tipo'] == 'familiar'

    corregido = cliente.patch(f"/api/v1/grupos/{otro['id']}", headers=comercial,
                              json={'tipo': 'viaje'})
    assert corregido.status_code == 200, corregido.text
    assert corregido.json()['tipo'] == 'viaje'

    ficha = cliente.get(f"{CLIENTES}/{c['id']}", headers=comercial).json()
    assert {g['nombre']: g['tipo'] for g in ficha['grupos']} == {
        'Promoción 2026': 'viaje', 'Familia Bedoya': 'viaje'}


def test_el_grupo_no_acepta_un_tipo_inventado(cliente, comercial):
    """Si el tipo entrara escrito a mano, mañana habría «Familiar», «fam» y
    «familia», y el conteo por tipo no se podría hacer."""
    c = crear_cliente(cliente, comercial, nombre='Ignacio Valbuena Soto')
    r = cliente.post('/api/v1/grupos', headers=comercial, json={
        'nombre': 'Grupo Raro', 'cliente_contacto_id': c['id'], 'tipo': 'corporativo'})
    assert r.status_code == 422, r.text


def test_la_tarjeta_del_grupo_dice_quien_contrata(cliente, comercial):
    """RF-003 pide «contacto principal» y la pantalla no tenía con qué decirlo:
    el grupo traía el id del contacto, y un número no le dice a nadie quién
    paga. Con dos grupos en una ficha era imposible saber a nombre de quién va
    cada uno."""
    c = crear_cliente(cliente, comercial, nombre='Gloria Estupiñán Vera')
    otro = crear_cliente(cliente, comercial, nombre='Mauricio Estupiñán Vera')
    g = cliente.post('/api/v1/grupos', headers=comercial, json={
        'nombre': 'Familia Estupiñán', 'cliente_contacto_id': c['id']}).json()
    assert g['contacto_nombre'] == 'Gloria Estupiñán Vera'

    r = cliente.patch(f"/api/v1/grupos/{g['id']}", headers=comercial,
                      json={'cliente_contacto_id': otro['id']})
    assert r.status_code == 200, r.text
    assert r.json()['cliente_contacto_id'] == otro['id']
    assert r.json()['contacto_nombre'] == 'Mauricio Estupiñán Vera'

    ficha = cliente.get(f"{CLIENTES}/{otro['id']}", headers=comercial).json()
    assert ficha['grupos'][0]['contacto_nombre'] == 'Mauricio Estupiñán Vera'


# ===========================================================================
# RF-004 · el historial de trámites de cada persona, aun con pago grupal
# ===========================================================================

def test_los_tramites_se_pueden_pedir_por_persona(cliente, admin, db):
    """RF-004 pide «su historial de trámites» por solicitante y el tablero solo
    sabía filtrar por estado, responsable, país y origen. En una familia de tres
    que compró junta, los tres trámites se veían revueltos y para saber cuál era
    de quién había que abrirlos uno por uno."""
    from app.models.esquema import Paises

    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    c = crear_cliente(cliente, admin, nombre='Olga Zapata Mejía')
    g = cliente.post('/api/v1/grupos', headers=admin,
                     json={'cliente_contacto_id': c['id'], 'nombre': 'Familia Zapata'}).json()
    madre = _persona(cliente, admin, grupo_id=g['id'], nombre='Olga Zapata Mejía')
    hijo = _persona(cliente, admin, grupo_id=g['id'], nombre='Julián Zapata Mejía')
    for persona in (madre, hijo):
        r = cliente.post('/api/v1/casos', headers=admin, json={
            'solicitante_id': persona['id'], 'pais_id': pais,
            'proxima_accion': 'Pedir documentos al cliente'})
        assert r.status_code == 201, r.text

    solo_del_hijo = cliente.get('/api/v1/casos', headers=admin,
                                params={'solicitante_id': hijo['id']})
    assert solo_del_hijo.status_code == 200, solo_del_hijo.text
    vistos = solo_del_hijo.json()
    assert vistos['total'] == 1, 'el filtro por persona trajo trámites de otra gente'
    assert [t['solicitante_id'] for t in vistos['items']] == [hijo['id']]


def test_el_historial_por_persona_respeta_el_alcance(cliente, db, usuario, admin):
    """El alcance es control de acceso y vive en el servicio (RNF-03). Si el
    filtro por persona se hubiera puesto en la ruta, quien tiene «solo lo
    asignado» habría podido pedir los trámites de cualquier persona por su id y
    la API se los habría entregado."""
    from app.models.esquema import Paises
    from app.services import usuarios as servicio_usuarios

    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    ajeno = usuario('operaciones')
    limitado = usuario('operaciones')
    servicio_usuarios.editar(db, usuario('administradora').u, limitado.u.id, alcance='asignados')
    db.commit()

    c = crear_cliente(cliente, admin, nombre='Sixto Carmona Vélez')
    de_otro = _persona(cliente, admin, cliente_id=c['id'], nombre='Sixto Carmona Vélez')
    mia = _persona(cliente, admin, cliente_id=c['id'], nombre='Amparo Carmona Vélez')
    cab_ajeno = entrar(cliente, ajeno)
    cliente.post('/api/v1/casos', headers=cab_ajeno, json={
        'solicitante_id': de_otro['id'], 'pais_id': pais, 'responsable_id': ajeno.u.id,
        'proxima_accion': 'Pedir documentos al cliente'})

    cab_limitado = entrar(cliente, limitado)
    r = cliente.post('/api/v1/casos', headers=cab_limitado, json={
        'solicitante_id': mia['id'], 'pais_id': pais, 'responsable_id': limitado.u.id,
        'proxima_accion': 'Pedir documentos al cliente'})
    assert r.status_code == 201, r.text

    ajenos = cliente.get('/api/v1/casos', headers=cab_limitado,
                         params={'solicitante_id': de_otro['id']}).json()
    assert ajenos['total'] == 0, 'pidiendo por id se saltó el alcance'

    propios = cliente.get('/api/v1/casos', headers=cab_limitado,
                          params={'solicitante_id': mia['id']}).json()
    assert [t['solicitante_id'] for t in propios['items']] == [mia['id']]


def test_en_una_venta_grupal_cada_persona_conserva_su_tramite_y_su_historial(cliente, admin, db):
    """La frase exacta de RF-004: «aun con pago grupal».

    La familia paga una sola vez y el recibo es uno, pero el consulado resuelve
    persona por persona. Si el trámite colgara de la venta no habría dónde
    anotar que a la hija le negaron la visa y al padre se la dieron.
    """
    from app.models.esquema import Paises, Servicios

    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    servicio = db.scalar(select(Servicios.id).where(Servicios.codigo == 'adelantos'))
    c = crear_cliente(cliente, admin, nombre='Ramiro Lizarazo Pinto')
    g = cliente.post('/api/v1/grupos', headers=admin, json={
        'cliente_contacto_id': c['id'], 'nombre': 'Familia Lizarazo'}).json()
    viajan = [_persona(cliente, admin, grupo_id=g['id'], nombre=nombre)
              for nombre in ('Ramiro Lizarazo Pinto', 'Delia Lizarazo Pinto',
                             'Camila Lizarazo Pinto')]

    oportunidad = cliente.post('/api/v1/oportunidades', headers=admin, json={
        'cliente_id': c['id'], 'servicio_id': servicio, 'pais_id': pais,
        'proxima_accion': 'Enviar cotización'})
    assert oportunidad.status_code == 201, oportunidad.text
    venta = cliente.post(f"/api/v1/oportunidades/{oportunidad.json()['id']}/ganar", headers=admin,
                         json={'solicitantes_ids': [s['id'] for s in viajan], 'personas': 3})
    assert venta.status_code == 201, venta.text
    venta = venta.json()
    assert len(venta['casos']) == 3, 'un trámite por persona que viaja'

    # Un solo pago, del grupo entero
    pago = cliente.post('/api/v1/pagos', headers=admin, json={
        'negocio_id': venta['id'], 'monto_bruto': venta['valor_pactado']})
    assert pago.status_code == 201, pago.text
    financiero = cliente.get(f"/api/v1/ventas/{venta['id']}/estado-financiero",
                             headers=admin).json()
    assert financiero['saldo'] == 0 and financiero['total_pagado'] == venta['valor_pactado']

    # Y aun así cada persona conserva SU trámite y SU historial
    for persona in viajan:
        suyos = cliente.get('/api/v1/casos', headers=admin,
                            params={'solicitante_id': persona['id']}).json()
        assert suyos['total'] == 1, f"{persona['nombre']} no tiene su propio trámite"
        tramite = suyos['items'][0]
        assert tramite['solicitante_id'] == persona['id']
        historial = cliente.get(f"/api/v1/casos/{tramite['id']}/historial", headers=admin).json()
        assert [h['campo'] for h in historial] == ['creado'], 'cada trámite con su propia historia'

    # El pago quedó en la venta del grupo, no repartido entre los tres trámites
    detalle_venta = cliente.get(f"/api/v1/ventas/{venta['id']}", headers=admin).json()
    assert {x['solicitante_id'] for x in detalle_venta['casos']} == {s['id'] for s in viajan}
