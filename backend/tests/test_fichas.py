"""Actividad 2.7 — ficha 360° del cliente y búsqueda global (RF-005, RF-029, RF-012).

Lo que se prueba es lo que hoy obliga a abrir tres archivos: que una sola
consulta traiga al cliente, su familia, sus trámites, sus citas y su historia;
y que una sola caja de búsqueda encuentre a la persona por lo que el asesor
tenga a mano en ese momento (un teléfono, una cédula, un pasaporte).
"""
import pytest
from sqlalchemy import select, text

from app.core import seguridad as seg
from app.models.esquema import Casos, Paises, Servicios
from tests.conftest import entrar


@pytest.fixture
def comercial(cliente, usuario):
    p = usuario('comercial')
    return entrar(cliente, p), p


@pytest.fixture
def finanzas(cliente, usuario):
    return entrar(cliente, usuario('finanzas'))


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


# ------------------------------------------------------------ el DS-160 (RF-029)

def _marcar_ds160(db, caso_id: int, numero: str) -> None:
    """Pone el DS-160 como lo pone la importación del SaaS, que es la única
    parte del sistema que lo escribe: el número cifrado y su índice ciego al
    lado (ver `services/saas.py`). El número en claro no se guarda nunca."""
    caso = db.get(Casos, caso_id)
    caso.ds160_numero_cifrado = seg.cifrar(numero)
    caso.ds160_hash = seg.indice_ciego(numero)
    db.commit()


def _tramite_con_ds160(cliente, db, usuario, familia, cab_comercial, *,
                       id_externo='VN-2026-9001', ds160='AA0099887766', responsable=None):
    """Un trámite con n.º de solicitud del SaaS y DS-160, que son las dos cosas
    por las que RF-029 pide encontrarlo. Lo abre operaciones, que es quien
    tramita; la comercial vende."""
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    persona = ficha(cliente, cab_comercial, familia)['cliente']['grupos'][0]['solicitantes'][0]
    cuerpo = {'solicitante_id': persona['id'], 'pais_id': pais, 'id_externo': id_externo}
    if responsable is not None:
        cuerpo['responsable_id'] = responsable
    r = cliente.post('/api/v1/casos', headers=entrar(cliente, usuario('operaciones')), json=cuerpo)
    assert r.status_code == 201, r.text
    _marcar_ds160(db, r.json()['id'], ds160)
    return r.json()


@pytest.mark.parametrize('consulta', [
    'AA0099887766',
    'aa0099887766',          # en minúsculas, como sale de copiar y pegar
    'AA 0099 887766',        # con los espacios con que lo lee la gente
])
def test_el_ds160_encuentra_el_tramite_aunque_se_escriba_distinto(
        cliente, comercial, familia, db, usuario, consulta):
    """El DS-160 está cifrado: se busca por su índice ciego, que normaliza el
    valor en mayúsculas y sin espacios. Así el asesor lo escribe como le quede
    cómodo y encuentra lo mismo.

    Esta parte de RF-029 estaba en el código sin una sola prueba que la
    sostuviera: funcionaba, pero nada avisaba si se rompía.
    """
    cab, _ = comercial
    caso = _tramite_con_ds160(cliente, db, usuario, familia, cab)
    hallado = [x for x in buscar(cliente, cab, consulta) if x['tipo'] == 'tramite']
    assert [x['id'] for x in hallado] == [caso['id']], f'«{consulta}» no lo encontró: {hallado}'
    assert hallado[0]['coincidio_por'] == 'DS-160'
    assert hallado[0]['ruta'] == f'/casos/{caso["id"]}'


def test_un_ds160_parecido_no_cuenta(cliente, comercial, familia, db, usuario):
    """El índice ciego solo permite la búsqueda exacta, y eso acá es lo correcto:
    un dígito de diferencia es otro formulario, de otra persona."""
    cab, _ = comercial
    _tramite_con_ds160(cliente, db, usuario, familia, cab)
    assert [x for x in buscar(cliente, cab, 'AA0099887767') if x['tipo'] == 'tramite'] == []


# --------------------------------------------- el alcance en el buscador (RNF-03)

def test_el_buscador_no_entrega_tramites_ajenos_a_quien_solo_ve_los_suyos(
        cliente, comercial, familia, db, usuario):
    """RNF-03, por la puerta del buscador.

    El alcance ya se respetaba en el tablero y al abrir un trámite por su URL,
    pero el buscador no recibía ni quién estaba buscando: quien tiene «solo los
    trámites asignados» escribía el n.º de solicitud o el DS-160 y encontraba
    trámites de otros, con el nombre del viajero en el resultado, y desde ahí
    los abría. El control de acceso vale en todas las puertas o no vale.
    """
    from app.services import usuarios as servicio_usuarios

    cab, _ = comercial
    admin = usuario('administradora')
    dueno = usuario('operaciones')
    ajeno = usuario('operaciones')
    servicio_usuarios.editar(db, admin.u, ajeno.u.id, alcance='asignados')
    db.commit()

    caso = _tramite_con_ds160(cliente, db, usuario, familia, cab, responsable=dueno.u.id)
    # El trámite se crea con el dueño como responsable; el ajeno no tiene nada
    cab_ajeno = entrar(cliente, ajeno)
    for consulta in ('VN-2026-9001', 'AA0099887766'):
        hallado = [x for x in buscar(cliente, cab_ajeno, consulta) if x['tipo'] == 'tramite']
        assert hallado == [], f'«{consulta}» le entregó un trámite ajeno: {hallado}'

    # Y no es que el buscador se haya quedado mudo: el responsable sí los encuentra
    cab_dueno = entrar(cliente, dueno)
    for consulta, por in (('VN-2026-9001', 'n.º de solicitud'), ('AA0099887766', 'DS-160')):
        hallado = [x for x in buscar(cliente, cab_dueno, consulta) if x['tipo'] == 'tramite']
        assert [x['id'] for x in hallado] == [caso['id']], f'«{consulta}»: {hallado}'
        assert hallado[0]['coincidio_por'] == por


def test_a_quien_le_quitaron_ver_tramites_el_buscador_no_se_los_entrega(
        cliente, comercial, familia, db, usuario):
    """Los permisos son datos: a un rol se le puede quitar «ver trámites» desde
    la administración, y la ficha del cliente ya lo respeta —responde sin la
    parte operativa—. El buscador tenía que respetarlo igual, o sería la rendija
    que deja sin efecto a lo otro: se escribe el n.º de solicitud y aparece el
    trámite con el nombre del viajero.
    """
    cab, _ = comercial
    _tramite_con_ds160(cliente, db, usuario, familia, cab)

    db.execute(text("""
        delete from roles_permisos
         where rol_id = (select id from roles where codigo = 'solo_lectura')
           and permiso_id in (select id from permisos where codigo = 'casos.ver')"""))
    db.commit()

    cab_lectura = entrar(cliente, usuario('solo_lectura'))
    for consulta in ('VN-2026-9001', 'AA0099887766'):
        hallado = [x for x in buscar(cliente, cab_lectura, consulta) if x['tipo'] == 'tramite']
        assert hallado == [], f'«{consulta}» entregó un trámite sin permiso: {hallado}'
    # Lo demás del buscador le sigue sirviendo: el cliente sí lo puede ver
    assert [x['id'] for x in buscar(cliente, cab_lectura, 'Restrepo')
            if x['tipo'] == 'cliente'] == [familia]


def test_colaborar_en_un_tramite_tambien_deja_encontrarlo_en_el_buscador(
        cliente, comercial, familia, db, usuario):
    """Ser colaborador tiene que servir también acá (RF-026). Si el alcance del
    buscador mirara solo al responsable, a quien lo pusieron a ayudar le diría
    que ese trámite no existe mientras lo ve en su propia lista de trabajo."""
    from app.services import usuarios as servicio_usuarios

    cab, _ = comercial
    admin = usuario('administradora')
    dueno = usuario('operaciones')
    ayuda = usuario('operaciones')
    servicio_usuarios.editar(db, admin.u, ayuda.u.id, alcance='asignados')
    db.commit()

    caso = _tramite_con_ds160(cliente, db, usuario, familia, cab, responsable=dueno.u.id)
    cab_ayuda = entrar(cliente, ayuda)
    assert [x for x in buscar(cliente, cab_ayuda, 'VN-2026-9001') if x['tipo'] == 'tramite'] == []

    r = cliente.post(f'/api/v1/casos/{caso["id"]}/colaboradores', headers=entrar(cliente, dueno),
                     json={'usuario_id': ayuda.u.id})
    assert r.status_code == 201, r.text
    hallado = [x for x in buscar(cliente, cab_ayuda, 'VN-2026-9001') if x['tipo'] == 'tramite']
    assert [x['id'] for x in hallado] == [caso['id']]


# ------------------------------------------- la referencia de pago (RF-029)

@pytest.fixture
def pago_con_referencia(cliente, comercial, familia, finanzas, db):
    """Una venta de la familia con un pago encima, como entra de verdad: el
    comprobante que el cliente manda por WhatsApp trae una referencia, y es lo
    único de ese comprobante que se puede buscar."""
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    servicio = db.scalar(select(Servicios.id).where(Servicios.codigo == 'asesoria_usa'))
    lead = cliente.post('/api/v1/oportunidades', headers=cab, json={
        'cliente_id': familia, 'servicio_id': servicio, 'pais_id': pais,
        'proxima_accion': 'Cotizar'}).json()
    venta = cliente.post(f'/api/v1/oportunidades/{lead["id"]}/ganar', headers=cab, json={})
    assert venta.status_code == 201, venta.text
    r = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'negocio_id': venta.json()['id'], 'monto_bruto': 350000, 'fecha': '2026-10-05',
        'referencia': 'BC-00123456789'})
    assert r.status_code == 201, r.text
    return r.json()


def test_el_pago_se_encuentra_por_la_referencia_del_comprobante(
        cliente, finanzas, pago_con_referencia):
    """RF-029: «ya pagué, el comprobante dice BC-00123456789».

    Era la última parte del requisito que no existía en ninguna capa: la caja de
    búsqueda la nombraba en su texto de ayuda y no la buscaba.
    """
    hallado = [x for x in buscar(cliente, finanzas, 'BC-00123456789') if x['tipo'] == 'pago']
    assert len(hallado) == 1, f'no encontró el pago: {hallado}'
    assert hallado[0]['id'] == pago_con_referencia['id']
    assert hallado[0]['coincidio_por'] == 'referencia de pago'
    assert 'Lucía Restrepo Ángel' in hallado[0]['titulo'], 'tiene que decir de quién es'
    assert 'BC-00123456789' in hallado[0]['detalle']
    assert hallado[0]['ruta'].startswith('/pagos?referencia=')


@pytest.mark.parametrize('consulta', [
    '00123456789',           # solo los dígitos del comprobante
    'bc-0012',               # en minúsculas
    '123456',                # un pedazo de la mitad
])
def test_la_referencia_se_encuentra_por_un_pedazo_y_sin_distinguir_mayusculas(
        cliente, finanzas, pago_con_referencia, consulta):
    """Nadie copia la referencia completa: se acuerda de los últimos dígitos, o
    pega un trozo del mensaje del banco."""
    hallado = [x for x in buscar(cliente, finanzas, consulta) if x['tipo'] == 'pago']
    assert [x['id'] for x in hallado] == [pago_con_referencia['id']], f'«{consulta}»: {hallado}'


def test_el_pago_sin_dueno_tambien_se_encuentra_por_su_referencia(cliente, finanzas):
    """Es el que más importa. Un pago que llegó suelto está en la bandeja de no
    identificados sin nombre de cliente, así que la referencia es lo único por
    donde agarrarlo: encontrarlo es lo que permite asignárselo al cliente que
    está llamando (RF-043)."""
    r = cliente.post('/api/v1/pagos', headers=finanzas, json={
        'monto_bruto': 200000, 'fecha': '2026-10-06', 'referencia': 'NEQUI-778899'})
    assert r.status_code == 201, r.text
    hallado = [x for x in buscar(cliente, finanzas, 'NEQUI-778899') if x['tipo'] == 'pago']
    assert [x['id'] for x in hallado] == [r.json()['id']], hallado
    assert 'sin identificar' in hallado[0]['titulo']


def test_quien_no_ve_la_contabilidad_no_encuentra_pagos_por_el_buscador(
        cliente, usuario, pago_con_referencia):
    """Ver plata es un permiso, no un alcance: los pagos no cuelgan de un
    responsable. A operaciones se le oculta la contabilidad a propósito
    (respuesta de la administradora del 29/09), y el buscador no puede ser la
    rendija por donde empiece a ver montos y nombres de pagadores."""
    cab = entrar(cliente, usuario('operaciones'))
    assert cliente.get('/api/v1/pagos', headers=cab).status_code == 403
    assert [x for x in buscar(cliente, cab, 'BC-00123456789') if x['tipo'] == 'pago'] == []


def test_el_comodin_de_sql_no_se_cuela_por_la_caja_de_busqueda(
        cliente, finanzas, pago_con_referencia):
    """El `%` y el `_` son comodines en SQL. Sin escaparlos, escribir «%» en el
    buscador pediría los pagos de todo el mundo, y es lo primero que alguien
    escribe por accidente al buscar «50% del anticipo»."""
    assert [x for x in buscar(cliente, finanzas, '%%') if x['tipo'] == 'pago'] == []
    assert [x for x in buscar(cliente, finanzas, 'BC-%') if x['tipo'] == 'pago'] == []
    assert [x for x in buscar(cliente, finanzas, 'BC_0') if x['tipo'] == 'pago'] == []


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


# ------------------------------- el teléfono de quien viaja (RF-029)

@pytest.fixture
def hijo_con_celular(cliente, comercial, familia):
    """Un hijo que viaja y tiene su propio celular.

    Es lo normal en VisaNow: la mamá contrata y pone su número en la ficha del
    cliente, pero el que contesta cuando se llama por la cita es el muchacho.
    """
    cab, _ = comercial
    r = cliente.post('/api/v1/solicitantes', headers=cab, json={
        'cliente_id': familia, 'nombre': 'Mateo Restrepo Gómez',
        'telefono': '+57 320 444 1122'})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize('consulta', [
    '3204441122',            # como lo dicta el cliente
    '+57 320 444 1122',      # como está guardado en el celular
    '320-444-1122',          # con guiones
])
def test_el_celular_de_quien_viaja_tambien_encuentra(
        cliente, comercial, familia, hijo_con_celular, consulta):
    """RF-029 pide buscar por teléfono, y el teléfono no es solo el de quien
    contrata: quien viaja tiene su propia columna y hasta ahora no se miraba,
    así que escribir el celular del hijo no encontraba absolutamente nada.
    """
    cab, _ = comercial
    hallado = [x for x in buscar(cliente, cab, consulta) if x['tipo'] == 'solicitante']
    assert [x['titulo'] for x in hallado] == ['Mateo Restrepo Gómez'], (
        f'«{consulta}» no encontró a quien viaja: {hallado}')
    assert hallado[0]['coincidio_por'] == 'teléfono'
    # Se atiende desde la ficha de quien contrata, igual que el pasaporte
    assert hallado[0]['ruta'] == f'/clientes/{familia}'


# ---------------------------- los adjuntos de la cronología (RF-064)
#
# RF-064 enumera cinco cosas —cronología, comunicaciones, eventos, autor y
# adjuntos— y la quinta no existía: `actividades.documento_id` estaba en el
# esquema desde el núcleo y nadie la escribía. El módulo de documentos ya sabe
# subir cifrado, enlazar y cerrar los reservados; lo que faltaba era poder
# colgar uno de un suceso y verlo ahí.


@pytest.fixture
def operaciones(cliente, usuario):
    """Quien hace el trámite: es el rol que sí ve los documentos reservados."""
    return entrar(cliente, usuario('operaciones'))


def enlazar(cliente, cab, *, entidad, entidad_id, nombre, reservado=False):
    r = cliente.post('/api/v1/documentos/enlace', headers=cab, json={
        'entidad': entidad, 'entidad_id': entidad_id, 'nombre': nombre,
        'url': f'https://drive.google.com/{entidad}/{entidad_id}',
        'restringido': reservado})
    assert r.status_code == 201, r.text
    return r.json()


def suceso(cliente, cab, cliente_id, titulo):
    sucesos = ficha(cliente, cab, cliente_id)['cronologia']
    hallado = [s for s in sucesos if s['titulo'] == titulo]
    assert hallado, f'«{titulo}» no está en la cronología: {[s["titulo"] for s in sucesos]}'
    return hallado[0]


def test_una_nota_puede_llevar_el_documento_del_que_habla(cliente, comercial, familia):
    """«Mandó el comprobante por WhatsApp» y el comprobante, en el mismo renglón.

    Hasta ahora el documento quedaba en la pantalla de documentos y la nota en
    la cronología, y quien leía la historia después no tenía cómo saber cuál de
    los archivos era el que llegó ese día.
    """
    cab, _ = comercial
    doc = enlazar(cliente, cab, entidad='cliente', entidad_id=familia,
                  nombre='Comprobante del anticipo')
    r = cliente.post(f'/api/v1/clientes/{familia}/notas', headers=cab, json={
        'tipo': 'whatsapp', 'asunto': 'Mandó el comprobante', 'documento_id': doc['id']})
    assert r.status_code == 201, r.text

    s = suceso(cliente, cab, familia, 'Mandó el comprobante')
    assert s['adjunto'], 'el suceso tiene que traer su adjunto'
    assert s['adjunto']['id'] == doc['id']
    assert s['adjunto']['nombre'] == 'Comprobante del anticipo'
    assert s['adjunto']['almacenamiento'] == 'enlace'
    assert s['adjunto']['url'] == doc['url']


def test_la_nota_del_tramite_tambien_lleva_su_soporte(
        cliente, comercial, operaciones, familia, db):
    """El soporte se adjunta donde se trabaja —el trámite— y la cronología del
    cliente lo muestra igual: es una sola historia (RF-064)."""
    cab, _ = comercial
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    persona = ficha(cliente, cab, familia)['cliente']['grupos'][0]['solicitantes'][0]
    caso = cliente.post('/api/v1/casos', headers=operaciones,
                        json={'solicitante_id': persona['id'], 'pais_id': pais}).json()
    doc = enlazar(cliente, operaciones, entidad='caso', entidad_id=caso['id'],
                  nombre='Carta laboral')
    r = cliente.post(f'/api/v1/casos/{caso["id"]}/notas', headers=operaciones, json={
        'tipo': 'correo', 'asunto': 'Mandó la carta laboral', 'documento_id': doc['id']})
    assert r.status_code == 201, r.text

    s = suceso(cliente, cab, familia, 'Mandó la carta laboral')
    assert s['adjunto']['nombre'] == 'Carta laboral'
    assert s['caso_id'] == caso['id']


def test_un_adjunto_reservado_no_asoma_por_la_cronologia(
        cliente, comercial, operaciones, familia):
    """La cronología se le muestra a cualquiera que pueda abrir la ficha, y el
    pasaporte escaneado no lo ve cualquiera: para eso está
    `solicitantes.reservado`. Si el adjunto reservado apareciera acá, la
    cronología abriría por detrás lo que la pantalla de documentos cierra.
    """
    doc = enlazar(cliente, operaciones, entidad='cliente', entidad_id=familia,
                  nombre='Pasaporte escaneado', reservado=True)
    r = cliente.post(f'/api/v1/clientes/{familia}/notas', headers=operaciones, json={
        'tipo': 'correo', 'asunto': 'Llegó el pasaporte escaneado',
        'documento_id': doc['id']})
    assert r.status_code == 201, r.text

    de_ops = suceso(cliente, operaciones, familia, 'Llegó el pasaporte escaneado')
    assert de_ops['adjunto']['nombre'] == 'Pasaporte escaneado', 'quien tramita sí lo ve'

    cab, _ = comercial
    del_comercial = suceso(cliente, cab, familia, 'Llegó el pasaporte escaneado')
    assert del_comercial['adjunto'] is None, (
        'el comercial lee el suceso, pero el documento reservado no es para él')


def test_no_se_puede_adjuntar_un_documento_reservado_sin_el_permiso(
        cliente, comercial, operaciones, familia):
    """Y no basta con esconderlo al leer: si se pudiera adjuntar a ciegas, el
    comercial pondría en la cronología un documento que ni él puede abrir."""
    doc = enlazar(cliente, operaciones, entidad='cliente', entidad_id=familia,
                  nombre='DS-160 impreso', reservado=True)
    cab, _ = comercial
    r = cliente.post(f'/api/v1/clientes/{familia}/notas', headers=cab, json={
        'tipo': 'nota', 'asunto': 'Lo vi de refilón', 'documento_id': doc['id']})
    # 404 y no 403: decir «existe pero no es para usted» ya revela que hay algo
    # reservado sobre esa persona. Es la misma respuesta de la pantalla.
    assert r.status_code == 404, r.text


def test_no_se_puede_colgar_en_una_ficha_el_documento_de_otro_cliente(
        cliente, comercial, familia):
    """El id llega en el cuerpo de la petición, así que no se puede dar por
    bueno. Sin esta comprobación, la cronología de Lucía le mostraría el nombre
    de un documento de otro cliente a cualquiera que pueda abrir su ficha."""
    cab, _ = comercial
    otro = cliente.post('/api/v1/clientes', headers=cab,
                        json={'nombre': 'Ajeno Pérez Pérez'}).json()
    doc = enlazar(cliente, cab, entidad='cliente', entidad_id=otro['id'],
                  nombre='Carpeta del ajeno')
    r = cliente.post(f'/api/v1/clientes/{familia}/notas', headers=cab, json={
        'tipo': 'nota', 'asunto': 'Nota con adjunto ajeno', 'documento_id': doc['id']})
    assert r.status_code == 422, r.text
    assert 'no es de este cliente' in r.json()['detalle'].lower(), r.text


def test_borrar_el_documento_adjunto_no_se_lleva_el_suceso(cliente, operaciones, familia):
    """La llamada ocurrió: el suceso se queda aunque el archivo se quite.

    Y al revés también importa: si la base no dejara borrar un documento que
    está nombrado en la cronología, adjuntar uno habría dejado inservible el
    botón de eliminar de la pantalla de documentos.
    """
    doc = enlazar(cliente, operaciones, entidad='cliente', entidad_id=familia,
                  nombre='Soporte provisional')
    r = cliente.post(f'/api/v1/clientes/{familia}/notas', headers=operaciones, json={
        'tipo': 'llamada', 'asunto': 'Repasamos el soporte', 'documento_id': doc['id']})
    assert r.status_code == 201, r.text

    assert cliente.delete(f'/api/v1/documentos/{doc["id"]}',
                          headers=operaciones).status_code == 204
    s = suceso(cliente, operaciones, familia, 'Repasamos el soporte')
    assert s['adjunto'] is None, 'el adjunto se fue con el documento'


def test_los_documentos_de_una_persona_del_grupo_salen_en_la_ficha(
        cliente, comercial, familia):
    """En VisaNow el que contrata casi nunca viaja solo: la familia cuelga de un
    grupo. «Los documentos de la ficha» son también los de esas personas —así lo
    dice el bloque de documentos— y los que colgaban del grupo no aparecían, así
    que tampoco se podían adjuntar a la cronología.
    """
    cab, _ = comercial
    persona = ficha(cliente, cab, familia)['cliente']['grupos'][0]['solicitantes'][0]
    doc = enlazar(cliente, cab, entidad='solicitante', entidad_id=persona['id'],
                  nombre='Cédula del hijo')
    nombres = {d['nombre'] for d in ficha(cliente, cab, familia)['documentos']}
    assert 'Cédula del hijo' in nombres, nombres

    r = cliente.post(f'/api/v1/clientes/{familia}/notas', headers=cab, json={
        'tipo': 'whatsapp', 'asunto': 'Mandó la cédula', 'documento_id': doc['id']})
    assert r.status_code == 201, r.text
