"""Actividad 2.7 — ficha 360° del cliente y búsqueda global (RF-005, RF-029, RF-012).

Lo que se prueba es lo que hoy obliga a abrir tres archivos: que una sola
consulta traiga al cliente, su familia, sus trámites, sus citas y su historia;
y que una sola caja de búsqueda encuentre a la persona por lo que el asesor
tenga a mano en ese momento (un teléfono, una cédula, un pasaporte).
"""
import pytest
from sqlalchemy import select, text

from app.models.esquema import Paises
from tests.conftest import entrar


@pytest.fixture
def comercial(cliente, usuario):
    p = usuario('comercial')
    return entrar(cliente, p), p


@pytest.fixture
def familia(cliente, comercial):
    """Una mamá que contrata y dos hijos que viajan: el caso real de VisaNow."""
    cab, _ = comercial
    c = cliente.post('/api/v1/clientes', headers=cab, json={
        'nombre': 'Lucía Restrepo Ángel', 'telefono': '+57 310 555 8899',
        'tipo_documento': 'CC', 'numero_documento': '43876512',
        'email': 'Lucia.Restrepo@Correo.com'}).json()
    g = cliente.post('/api/v1/grupos', headers=cab,
                     json={'cliente_contacto_id': c['id'], 'nombre': 'Familia Restrepo'}).json()
    for nombre, pasaporte in (('Lucía Restrepo Ángel', 'AY7788990'),
                              ('Tomás Restrepo Gómez', 'AY7788991'),
                              ('Sara Restrepo Gómez', 'AY7788992')):
        r = cliente.post('/api/v1/solicitantes', headers=cab,
                         json={'grupo_id': g['id'], 'nombre': nombre, 'pasaporte': pasaporte})
        assert r.status_code == 201, r.text
    return c['id']


def ficha(cliente, cab, cliente_id):
    r = cliente.get(f'/api/v1/clientes/{cliente_id}/ficha', headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------- ficha 360°

def test_la_ficha_trae_al_cliente_su_familia_y_sus_tramites_en_una_sola_consulta(
        cliente, comercial, familia, db, usuario):
    """RF-005: una llamada, todo el panorama. Hoy son tres archivos."""
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    sols = cliente.get(f'/api/v1/solicitantes?cliente_id={familia}', headers=cab).json()
    assert len(sols) == 3      # cuelgan del grupo, pero se listan bajo el contacto
    assert all(s['grupo_id'] for s in sols) and not any(s['cliente_id'] for s in sols)

    f = ficha(cliente, cab, familia)
    assert f['cliente']['nombre'] == 'Lucía Restrepo Ángel'
    assert f['resumen']['personas'] == 3
    assert f['resumen']['tramites_total'] == 0
    assert [g['nombre'] for g in f['cliente']['grupos']] == ['Familia Restrepo']

    # Se abre un trámite para uno de los hijos
    hijo = next(s for g in f['cliente']['grupos'] for s in g['solicitantes']
                if s['nombre'].startswith('Tomás'))
    # La comercial vende pero no tramita: el trámite lo abre operaciones
    caso = cliente.post('/api/v1/casos', headers=entrar(cliente, usuario('operaciones')), json={
        'solicitante_id': hijo['id'], 'pais_id': pais, 'proxima_accion': 'Pedir documentos'})
    assert caso.status_code == 201, caso.text

    f = ficha(cliente, cab, familia)
    assert f['resumen']['tramites_total'] == 1 and f['resumen']['tramites_abiertos'] == 1
    assert f['tramites'][0]['solicitante'] == 'Tomás Restrepo Gómez'
    assert f['ve_tramites'] is True


def test_la_cronologia_mezcla_lo_del_sistema_con_lo_que_anota_la_gente(
        cliente, comercial, familia, db, usuario):
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    f = ficha(cliente, cab, familia)
    persona = f['cliente']['grupos'][0]['solicitantes'][0]

    cab_ops = entrar(cliente, usuario('operaciones'))
    caso = cliente.post('/api/v1/casos', headers=cab_ops,
                        json={'solicitante_id': persona['id'], 'pais_id': pais}).json()
    r = cliente.post(f'/api/v1/clientes/{familia}/notas', headers=cab, json={
        'tipo': 'llamada', 'asunto': 'Llamada de seguimiento',
        'cuerpo': 'Pregunta si ya puede comprar tiquetes. Se le explicó que espere la cita.'})
    assert r.status_code == 201, r.text
    assert cliente.post(f'/api/v1/casos/{caso["id"]}/notas', headers=cab_ops, json={
        'tipo': 'whatsapp', 'cuerpo': 'Envió foto del pasaporte por WhatsApp'}).status_code == 201

    f = ficha(cliente, cab, familia)
    titulos = [s['titulo'] for s in f['cronologia']]
    assert 'Trámite creado' in titulos                      # lo registró el sistema
    assert 'Llamada de seguimiento' in titulos              # lo anotó la comercial
    assert 'Whatsapp' in titulos                            # nota sin asunto: usa el tipo
    # Ordenada de lo más reciente a lo más viejo, sin importar de qué fuente venga
    assert f['cronologia'] == sorted(f['cronologia'], key=lambda s: s['cuando'], reverse=True)
    assert any(s['usuario'] for s in f['cronologia']), 'debe constar quién hizo cada cosa'


def test_una_nota_cuenta_como_contacto_con_el_cliente(cliente, comercial, familia):
    """RF-012: el «último contacto» no se digita, se deduce de lo que pasó."""
    cab, _ = comercial
    assert ficha(cliente, cab, familia)['resumen']['ultimo_contacto_en'] is None
    cliente.post(f'/api/v1/clientes/{familia}/notas', headers=cab,
                 json={'tipo': 'llamada', 'asunto': 'Primer contacto'})
    resumen = ficha(cliente, cab, familia)['resumen']
    assert resumen['ultimo_contacto_en'] is not None and resumen['dias_sin_contacto'] == 0


def test_una_llamada_sobre_el_tramite_tambien_cuenta_como_contacto(
        cliente, comercial, familia, db, usuario):
    """La llamada se anota sobre el trámite, pero se habló con el cliente: el
    «último contacto» de su ficha tiene que moverse igual, o el tablero de
    seguimiento lo va a reportar como abandonado sin serlo."""
    cab, _ = comercial
    ops = usuario('operaciones')
    cab_ops = entrar(cliente, ops)
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    persona = ficha(cliente, cab, familia)['cliente']['grupos'][0]['solicitantes'][0]
    caso = cliente.post('/api/v1/casos', headers=cab_ops,
                        json={'solicitante_id': persona['id'], 'pais_id': pais}).json()
    assert ficha(cliente, cab, familia)['resumen']['ultimo_contacto_en'] is None

    r = cliente.post(f'/api/v1/casos/{caso["id"]}/notas', headers=cab_ops,
                     json={'tipo': 'llamada', 'asunto': 'Le avisé que llegó la cita'})
    assert r.status_code == 201, r.text
    assert ficha(cliente, cab, familia)['resumen']['dias_sin_contacto'] == 0


def test_una_nota_interna_no_cuenta_como_contacto(cliente, comercial, familia):
    """Escribir una nota para uno mismo no es hablar con el cliente."""
    cab, _ = comercial
    cliente.post(f'/api/v1/clientes/{familia}/notas', headers=cab,
                 json={'tipo': 'nota', 'asunto': 'Revisar si el pasaporte vence antes del viaje'})
    f = ficha(cliente, cab, familia)
    assert f['resumen']['ultimo_contacto_en'] is None
    assert 'Revisar si el pasaporte vence antes del viaje' in [s['titulo'] for s in f['cronologia']]


def test_una_nota_vacia_se_rechaza(cliente, comercial, familia):
    cab, _ = comercial
    r = cliente.post(f'/api/v1/clientes/{familia}/notas', headers=cab, json={'tipo': 'nota'})
    assert r.status_code == 422 and 'asunto' in r.json()['detalle']


def test_la_proxima_cita_aparece_en_el_resumen(cliente, comercial, familia, db, usuario):
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    persona = ficha(cliente, cab, familia)['cliente']['grupos'][0]['solicitantes'][0]
    cab_ops = entrar(cliente, usuario('operaciones'))
    caso = cliente.post('/api/v1/casos', headers=cab_ops,
                        json={'solicitante_id': persona['id'], 'pais_id': pais}).json()
    r = cliente.post(f'/api/v1/casos/{caso["id"]}/citas', headers=cab_ops, json={
        'tipo': 'entrevista', 'inicia_en': '2027-03-04T08:30:00-05:00'})
    assert r.status_code == 201, r.text

    f = ficha(cliente, cab, familia)
    assert f['resumen']['proxima_cita'].startswith('2027-03-04')
    assert f['citas'][0]['solicitante'] == persona['nombre']
    assert f['citas'][0]['tipo'] == 'entrevista'


def test_una_cita_cancelada_ya_no_es_proxima(cliente, comercial, familia, db, usuario):
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    persona = ficha(cliente, cab, familia)['cliente']['grupos'][0]['solicitantes'][0]
    cab_ops = entrar(cliente, usuario('operaciones'))
    caso = cliente.post('/api/v1/casos', headers=cab_ops,
                        json={'solicitante_id': persona['id'], 'pais_id': pais}).json()
    cita = cliente.post(f'/api/v1/casos/{caso["id"]}/citas', headers=cab_ops, json={
        'tipo': 'cas', 'inicia_en': '2027-03-04T08:30:00-05:00'}).json()
    cliente.patch(f'/api/v1/citas/{cita["id"]}', headers=cab_ops, json={'estado': 'cancelada'})
    f = ficha(cliente, cab, familia)
    assert f['citas'] == [] and f['resumen']['proxima_cita'] is None


def test_quien_no_puede_ver_tramites_ve_la_ficha_sin_ellos(cliente, comercial, familia, db, usuario):
    """Los permisos son datos, no código: a un rol se le puede quitar «ver
    trámites» desde la administración. Cuando eso pasa, la ficha responde igual
    pero sin la parte operativa, y lo dice en `ve_tramites` para que la pantalla
    no muestre una sección vacía como si el cliente no tuviera trámites."""
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    persona = ficha(cliente, cab, familia)['cliente']['grupos'][0]['solicitantes'][0]
    cliente.post('/api/v1/casos', headers=entrar(cliente, usuario('operaciones')),
                 json={'solicitante_id': persona['id'], 'pais_id': pais})

    db.execute(text("""
        delete from roles_permisos
         where rol_id = (select id from roles where codigo = 'solo_lectura')
           and permiso_id in (select id from permisos where codigo = 'casos.ver')"""))
    db.commit()

    f = ficha(cliente, entrar(cliente, usuario('solo_lectura')), familia)
    assert f['ve_tramites'] is False and f['tramites'] == [] and f['citas'] == []
    assert f['cliente']['nombre'] == 'Lucía Restrepo Ángel'        # lo demás sí llega
    assert f['resumen']['personas'] == 3
    assert f['resumen']['tramites_total'] == 0, 'no puede filtrar por el contador'


# ------------------------------------------------------------ búsqueda global

def buscar(cliente, cab, q):
    r = cliente.get('/api/v1/buscar', headers=cab, params={'q': q})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize('consulta, por', [
    ('Restrepo', 'nombre'),
    ('restrepo angel', 'nombre'),        # sin tildes
    ('LUCÍA', 'nombre'),                 # en mayúsculas y con tilde
    ('43876512', 'documento'),
    ('3105558899', 'teléfono'),
    ('+57 310 555 8899', 'teléfono'),    # como está en el celular
    ('lucia.restrepo@correo.com', 'correo'),
])
def test_la_misma_caja_encuentra_por_lo_que_el_asesor_tenga_a_mano(
        cliente, comercial, familia, consulta, por):
    cab, _ = comercial
    encontrados = buscar(cliente, cab, consulta)
    mio = [x for x in encontrados if x['id'] == familia and x['tipo'] == 'cliente']
    assert mio, f'«{consulta}» no encontró al cliente: {encontrados}'
    assert mio[0]['coincidio_por'] == por
    assert mio[0]['ruta'] == f'/clientes/{familia}'


def test_el_pasaporte_se_encuentra_exacto_y_lleva_a_la_ficha_del_cliente(cliente, comercial, familia):
    """La columna está cifrada: se busca por su índice ciego, sin descifrarla."""
    cab, _ = comercial
    r = [x for x in buscar(cliente, cab, 'AY7788991') if x['tipo'] == 'solicitante']
    assert len(r) == 1 and r[0]['titulo'] == 'Tomás Restrepo Gómez'
    assert r[0]['coincidio_por'] == 'pasaporte'
    assert r[0]['ruta'] == f'/clientes/{familia}'          # el trámite se atiende desde el contacto
    assert buscar(cliente, cab, 'AY7788999') == []         # un pasaporte parecido no cuenta


def test_el_numero_de_solicitud_del_saas_encuentra_el_tramite(cliente, comercial, familia, db, usuario):
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    persona = ficha(cliente, cab, familia)['cliente']['grupos'][0]['solicitantes'][0]
    cliente.post('/api/v1/casos', headers=entrar(cliente, usuario('operaciones')),
                 json={'solicitante_id': persona['id'], 'pais_id': pais, 'id_externo': 'VN-2026-7781'})
    r = [x for x in buscar(cliente, cab, 'VN-2026-7781') if x['tipo'] == 'tramite']
    assert len(r) == 1 and r[0]['coincidio_por'] == 'n.º de solicitud'
    assert r[0]['ruta'].startswith('/casos/')


def test_la_busqueda_no_trae_a_quien_no_tiene_documento(cliente, comercial):
    """Buscar «12345» no puede devolver a todo el que tenga el documento vacío:
    en SQLAlchemy `columna == None` se traduce a IS NULL."""
    cab, _ = comercial
    cliente.post('/api/v1/clientes', headers=cab, json={'nombre': 'Persona Sin Documento'})
    assert all('Sin Documento' not in x['titulo'] for x in buscar(cliente, cab, '99999999'))


def test_una_ficha_fusionada_no_vuelve_a_aparecer(cliente, comercial, usuario):
    """Después de unir dos fichas, la absorbida deja de salir en la búsqueda."""
    cab, _ = comercial
    a = cliente.post('/api/v1/clientes', headers=cab,
                     json={'nombre': 'Hernán Zuluaga Pérez', 'telefono': '3001112233'}).json()
    b = cliente.post('/api/v1/clientes', headers=cab,
                     json={'nombre': 'Hernan Zuluaga', 'telefono': '3001112233'}).json()
    assert len(buscar(cliente, cab, 'Zuluaga')) == 2
    cab_admin = entrar(cliente, usuario('administradora'))
    r = cliente.post(f'/api/v1/clientes/{a["id"]}/fusionar', headers=cab_admin,
                     json={'absorbido_id': b['id'], 'criterio': 'manual'})
    assert r.status_code == 200, r.text
    quedan = buscar(cliente, cab, 'Zuluaga')
    assert [x['id'] for x in quedan] == [a['id']]


def test_una_sola_letra_no_dispara_la_busqueda(cliente, comercial):
    cab, _ = comercial
    assert cliente.get('/api/v1/buscar', headers=cab, params={'q': 'a'}).status_code == 422


def test_la_busqueda_exige_permiso(cliente, usuario):
    r = cliente.get('/api/v1/buscar', params={'q': 'Restrepo'})
    assert r.status_code == 401


# ------------------------------------------- el historial en idioma de la gente

def test_el_historial_no_muestra_codigos_ni_ids_crudos(cliente, comercial, familia, db, usuario):
    """La tabla guarda «estado: esperando_info → info_en_revision» y «sede_id: 2»,
    que sirve para auditar pero no dice nada en pantalla. Se traduce en el
    servidor, que es donde están los catálogos, y las dos fichas —la del cliente
    y la del trámite— cuentan lo mismo."""
    cab, _ = comercial
    ops = usuario('operaciones')
    cab_ops = entrar(cliente, ops)
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    persona = ficha(cliente, cab, familia)['cliente']['grupos'][0]['solicitantes'][0]
    # RN-04: sin responsable el trámite no se puede mover
    caso = cliente.post('/api/v1/casos', headers=cab_ops,
                        json={'solicitante_id': persona['id'], 'pais_id': pais,
                              'responsable_id': ops.u.id,
                              'proxima_accion': 'Pedir documentos al cliente'}).json()

    r = cliente.post(f'/api/v1/casos/{caso["id"]}/estado', headers=cab_ops,
                     json={'codigo_destino': 'esperando_info'})
    assert r.status_code == 200, r.text
    sede = db.scalar(text("select id, nombre from sedes order by id limit 1"))
    nombre_sede = db.scalar(text('select nombre from sedes where id = :i'), {'i': sede})
    assert cliente.post(f'/api/v1/casos/{caso["id"]}/citas', headers=cab_ops, json={
        'tipo': 'entrevista', 'inicia_en': '2027-05-06T10:00:00-05:00',
        'sede_id': sede}).status_code == 201

    titulos = [h['titulo'] for h in
               cliente.get(f'/api/v1/casos/{caso["id"]}/historial', headers=cab_ops).json()]
    nombre_estado = dict(db.execute(text('select codigo, nombre from estados_operativos')).all())
    assert 'Trámite creado' in titulos
    assert (f'Estado: {nombre_estado["registrado"]} → {nombre_estado["esperando_info"]}') in titulos
    assert 'Cita de entrevista agendada' in titulos
    assert f'Sede: — → {nombre_sede}' in titulos
    for t in titulos:
        assert 'esperando_info' not in t and 'sede_id' not in t, f'quedó un código crudo: {t}'

    # La ficha del cliente cuenta exactamente lo mismo
    en_la_ficha = [s['titulo'] for s in ficha(cliente, cab, familia)['cronologia']]
    assert set(titulos) <= set(en_la_ficha)


def test_el_documento_del_checklist_se_nombra_completo(cliente, comercial, familia, db, usuario):
    cab, _ = comercial
    cab_ops = entrar(cliente, usuario('operaciones'))
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    persona = ficha(cliente, cab, familia)['cliente']['grupos'][0]['solicitantes'][0]
    caso = cliente.post('/api/v1/casos', headers=cab_ops,
                        json={'solicitante_id': persona['id'], 'pais_id': pais}).json()
    detalle = cliente.get(f'/api/v1/casos/{caso["id"]}', headers=cab_ops).json()
    item = detalle['checklist'][0]
    assert cliente.post(f'/api/v1/casos/{caso["id"]}/checklist/{item["item_id"]}', headers=cab_ops,
                        json={'cumplido': True}).status_code == 204

    titulos = [h['titulo'] for h in
               cliente.get(f'/api/v1/casos/{caso["id"]}/historial', headers=cab_ops).json()]
    assert f'Documento «{item["nombre"]}»: entregado' in titulos


def test_quien_contrata_y_viaja_no_sale_dos_veces(cliente, comercial, familia):
    """Lucía es el contacto y además viaja. Sin cuidado saldría como cliente y
    como viajera, con el mismo nombre y llevando a la misma ficha."""
    cab, _ = comercial
    encontrados = buscar(cliente, cab, 'Lucía Restrepo Ángel')
    assert [r['tipo'] for r in encontrados] == ['cliente']
    # Sus hijos, que no son el contacto, sí tienen que aparecer
    assert [r['titulo'] for r in buscar(cliente, cab, 'Tomás Restrepo')] == ['Tomás Restrepo Gómez']
