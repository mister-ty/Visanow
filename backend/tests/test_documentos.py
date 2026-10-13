"""Documentos adjuntos a una ficha (RNF-04, RF-064).

La tabla existia desde el nucleo y nadie escribia en ella. Lo que vigilan estas
pruebas es lo que hace que subir archivos de personas sea aceptable y no un
problema nuevo: que lo que queda en el disco no se pueda leer, que no se guarde
donde se va a perder, que el alcance valga tambien por esta puerta, y que el
nombre que manda el navegador no decida donde se escribe.
"""
import hashlib

import pytest
from sqlalchemy import select

from app.models.esquema import Auditoria, Documentos
from tests.conftest import entrar

PDF = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n'
JPG = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * 40
EJECUTABLE = b'MZ\x90\x00\x03' + b'\x00' * 60
RUTA = '/api/v1/documentos'


@pytest.fixture
def admin(cliente, usuario):
    return entrar(cliente, usuario('administradora'))


@pytest.fixture
def con_disco(tmp_path, monkeypatch):
    """Un servidor que SI tiene donde guardar."""
    from app.core.config import ajustes
    monkeypatch.setattr(ajustes(), 'almacenamiento_ruta', str(tmp_path))
    return tmp_path


@pytest.fixture
def sin_disco(monkeypatch):
    """Un servidor efimero, como Render en el plan gratuito.

    Se declara a proposito en vez de confiar en que el .env de quien corre las
    pruebas lo tenga vacio: una prueba que pasa o falla segun la configuracion
    local de cada quien no esta probando el codigo.
    """
    from app.core.config import ajustes
    monkeypatch.setattr(ajustes(), 'almacenamiento_ruta', '')


def un_cliente(cliente, cab, nombre='Documentada Prueba Cliente'):
    return cliente.post('/api/v1/clientes', headers=cab, json={'nombre': nombre}).json()


def subir(cliente, cab, entidad, entidad_id, contenido=PDF, nombre='soporte.pdf', **extra):
    return cliente.post(RUTA, headers=cab,
                        files={'archivo': (nombre, contenido, 'application/pdf')},
                        data={'entidad': entidad, 'entidad_id': str(entidad_id), **extra})


def archivos_de(carpeta):
    return [p for p in carpeta.rglob('*') if p.is_file()]


# --------------------------------------------------- lo que queda en el disco

def test_lo_que_queda_en_el_disco_no_se_puede_leer(cliente, admin, db, con_disco):
    """RNF-04. Un soporte de pago trae el nombre y la cuenta de una persona; un
    pasaporte escaneado trae todo. Un disco dado de baja, o un respaldo que se
    pierde, no pueden ser una fuga.
    """
    c = un_cliente(cliente, admin)
    r = subir(cliente, admin, 'cliente', c['id'])
    assert r.status_code == 201, r.text

    escritos = archivos_de(con_disco)
    assert len(escritos) == 1, escritos
    crudo = escritos[0].read_bytes()
    assert crudo != PDF, 'quedo en claro en el disco'
    assert b'%PDF' not in crudo, 'se reconoce que es un PDF con solo mirarlo'
    assert crudo.startswith(b'gAAAAA'), 'tiene que estar cifrado'


def test_lo_que_se_baja_es_identico_a_lo_que_se_subio(cliente, admin, db, con_disco):
    c = un_cliente(cliente, admin)
    doc = subir(cliente, admin, 'cliente', c['id']).json()

    r = cliente.get(RUTA + '/' + str(doc['id']) + '/contenido', headers=admin)
    assert r.status_code == 200, r.text
    assert r.content == PDF
    assert 'attachment' in r.headers['content-disposition']
    assert r.headers['x-content-type-options'] == 'nosniff'


def test_si_el_archivo_del_disco_no_coincide_con_su_huella_no_se_entrega(
        cliente, admin, db, con_disco):
    """Que no coincida significa que ya no es el archivo que se subio.
    Entregarlo como si lo fuera seria lo peor que se puede hacer.
    """
    from app.core import seguridad as seg

    c = un_cliente(cliente, admin)
    doc = subir(cliente, admin, 'cliente', c['id']).json()
    archivos_de(con_disco)[0].write_bytes(seg.cifrar_bytes(PDF + b'algo mas'))

    r = cliente.get(RUTA + '/' + str(doc['id']) + '/contenido', headers=admin)
    assert r.status_code == 409, r.text
    assert r.json()['codigo'] == 'huella_distinta'


def test_la_huella_guardada_es_la_del_archivo(cliente, admin, db, con_disco):
    c = un_cliente(cliente, admin)
    doc = subir(cliente, admin, 'cliente', c['id']).json()
    db.expire_all()
    guardado = db.get(Documentos, doc['id'])
    assert guardado.sha256 == hashlib.sha256(PDF).hexdigest()
    assert guardado.tamano_bytes == len(PDF)
    assert guardado.mime == 'application/pdf'


# ------------------------------------ no se guarda donde se va a perder

def test_sin_disco_declarado_no_se_sube_y_se_dice_por_que(cliente, admin, db, sin_disco):
    """Render borra su disco en cada despliegue. Subir el pasaporte de alguien
    ahi es perderlo sin que nadie se entere hasta que haga falta.
    """
    c = un_cliente(cliente, admin)
    r = subir(cliente, admin, 'cliente', c['id'])
    assert r.status_code == 409, r.text
    assert r.json()['codigo'] == 'sin_almacenamiento'
    assert 'enlace' in r.json()['detalle'], 'tiene que decir cual es la salida'


def test_con_disco_el_estado_lo_dice(cliente, admin, con_disco):
    d = cliente.get(RUTA + '/estado', headers=admin).json()
    assert d['se_pueden_subir'] is True and d['motivo'] is None


def test_sin_disco_el_estado_lo_dice_con_el_motivo(cliente, admin, sin_disco):
    """Ofrecer «subir archivo» donde el archivo se va a perder es peor que no
    ofrecerlo: la persona cree que quedo guardado.
    """
    d = cliente.get(RUTA + '/estado', headers=admin).json()
    assert d['se_pueden_subir'] is False
    assert d['motivo'] and 'enlace' in d['motivo']
    assert d['max_mb'] == 25 and 'pdf' in d['tipos']


def test_el_enlace_sirve_aunque_no_haya_disco(cliente, admin, db, sin_disco):
    """Es la salida mientras tanto, y ademas sirve siempre: hay cosas que ya
    viven en una carpeta compartida y no tiene sentido duplicar.
    """
    c = un_cliente(cliente, admin)
    r = cliente.post(RUTA + '/enlace', headers=admin, json={
        'entidad': 'cliente', 'entidad_id': c['id'], 'nombre': 'Carpeta del cliente',
        'url': 'https://drive.google.com/drive/folders/abc'})
    assert r.status_code == 201, r.text
    assert r.json()['almacenamiento'] == 'enlace'


def test_un_enlace_que_no_es_una_direccion_se_rechaza(cliente, admin, db):
    c = un_cliente(cliente, admin)
    r = cliente.post(RUTA + '/enlace', headers=admin, json={
        'entidad': 'cliente', 'entidad_id': c['id'], 'nombre': 'raro',
        'url': 'javascript:alert(1)'})
    assert r.status_code == 422, r.text
    assert r.json()['codigo'] == 'enlace_invalido'


# ------------------------------------- lo que el archivo ES, no como se llama

def test_un_ejecutable_con_nombre_de_pdf_se_rechaza(cliente, admin, db, con_disco):
    """Cambiarle la extension a un ejecutable es lo primero que se intenta."""
    c = un_cliente(cliente, admin)
    r = subir(cliente, admin, 'cliente', c['id'], contenido=EJECUTABLE,
              nombre='pasaporte.pdf')
    assert r.status_code == 422, r.text
    assert r.json()['codigo'] == 'tipo_no_permitido'
    assert archivos_de(con_disco) == [], 'no puede quedar nada escrito'


def test_el_nombre_del_navegador_no_decide_donde_se_escribe(cliente, admin, db, con_disco):
    """Asi es como se cuela un «../../» y se escribe donde no se debe."""
    c = un_cliente(cliente, admin)
    r = subir(cliente, admin, 'cliente', c['id'], nombre='../../../etc/passwd.pdf')
    assert r.status_code == 201, r.text

    escritos = archivos_de(con_disco)
    assert len(escritos) == 1
    assert escritos[0].parent == con_disco / 'cliente', escritos[0]
    assert 'passwd' not in escritos[0].name
    assert '..' not in escritos[0].name


def test_el_nombre_raro_tampoco_parte_la_cabecera_al_bajarlo(cliente, admin, db,
                                                             con_disco):
    """El nombre sale a una cabecera HTTP. Una comilla o un salto de linea la
    parten en dos y lo que sigue se vuelve otra cabecera.
    """
    c = un_cliente(cliente, admin)
    doc = subir(cliente, admin, 'cliente', c['id'],
                nombre='comp"robante\r\nX-Malo: si.pdf').json()
    r = cliente.get(RUTA + '/' + str(doc['id']) + '/contenido', headers=admin)
    assert r.status_code == 200
    disposicion = r.headers['content-disposition']
    assert '"' not in disposicion.replace('filename="', '').rstrip('"')
    assert 'x-malo' not in {k.lower() for k in r.headers}


def test_un_archivo_vacio_se_rechaza(cliente, admin, db, con_disco):
    c = un_cliente(cliente, admin)
    r = subir(cliente, admin, 'cliente', c['id'], contenido=b'')
    assert r.status_code == 422, r.text
    assert r.json()['codigo'] == 'archivo_vacio'


# --------------------------------------- el alcance vale tambien por esta puerta

def _caso_ajeno(cliente, db, usuario):
    """Un tramite de otro, y alguien con alcance limitado que no deberia verlo.

    Se arma aqui y no con las fixtures de test_casos porque esas viven en ese
    archivo: importarlas por el nombre no las trae.
    """
    from sqlalchemy import select as _select

    from app.models.esquema import Paises
    from app.services import usuarios as servicio_usuarios

    admin = usuario('administradora')
    dueno, ajeno = usuario('operaciones'), usuario('operaciones')
    servicio_usuarios.editar(db, admin.u, ajeno.u.id, alcance='asignados')
    db.commit()

    cab_dueno = entrar(cliente, dueno)
    c = cliente.post('/api/v1/clientes', headers=cab_dueno,
                     json={'nombre': 'Ajena Deotro Cliente'}).json()
    p = cliente.post('/api/v1/solicitantes', headers=cab_dueno,
                     json={'cliente_id': c['id'], 'nombre': 'Ajena Deotro Persona'}).json()
    pais = db.scalar(_select(Paises.id).where(Paises.iso2 == 'US'))
    caso = cliente.post('/api/v1/casos', headers=cab_dueno, json={
        'solicitante_id': p['id'], 'pais_id': pais, 'responsable_id': dueno.u.id,
        'proxima_accion': 'Pedir documentos al cliente'}).json()
    return caso, entrar(cliente, ajeno)


def test_no_se_adjunta_a_un_tramite_que_no_se_puede_ver(cliente, db, usuario,
                                                        con_disco):
    """Si no, adjuntar documentos seria la puerta de atras para tocar los
    tramites ajenos: bastaria con poner un numero cualquiera.
    """
    caso, cab_ajeno = _caso_ajeno(cliente, db, usuario)
    r = subir(cliente, cab_ajeno, 'caso', caso['id'])
    assert r.status_code == 404, r.text
    assert archivos_de(con_disco) == []


def test_no_se_listan_los_documentos_de_un_tramite_ajeno(cliente, db, usuario,
                                                         con_disco):
    """Saber cuantos soportes tiene un tramite ya dice algo de el."""
    caso, cab_ajeno = _caso_ajeno(cliente, db, usuario)
    r = cliente.get(RUTA + '?entidad=caso&entidad_id=' + str(caso['id']), headers=cab_ajeno)
    assert r.status_code == 404, r.text


# ------------------------------------------------------------- los restringidos

def test_un_documento_restringido_no_lo_ve_cualquiera(cliente, admin, db, usuario,
                                                      con_disco):
    """Es para el pasaporte escaneado y cosas de ese orden."""
    c = un_cliente(cliente, admin)
    subir(cliente, admin, 'cliente', c['id'], nombre='normal.pdf')
    reservado = subir(cliente, admin, 'cliente', c['id'], contenido=JPG,
                      nombre='pasaporte.jpg', restringido='true').json()

    cab = entrar(cliente, usuario('comercial'))
    vistos = cliente.get(RUTA + '?entidad=cliente&entidad_id=' + str(c['id']),
                         headers=cab).json()
    assert [d['nombre'] for d in vistos] == ['normal.pdf'], vistos

    # Y por la URL directa responde como si no existiera: decir «existe pero no
    # es para usted» ya revela que hay algo reservado sobre esa persona.
    r = cliente.get(RUTA + '/' + str(reservado['id']) + '/contenido', headers=cab)
    assert r.status_code == 404, r.text


def test_quien_si_puede_los_ve_todos(cliente, admin, db, con_disco):
    c = un_cliente(cliente, admin)
    subir(cliente, admin, 'cliente', c['id'], nombre='normal.pdf')
    subir(cliente, admin, 'cliente', c['id'], contenido=JPG, nombre='pasaporte.jpg',
          restringido='true')
    vistos = cliente.get(RUTA + '?entidad=cliente&entidad_id=' + str(c['id']),
                         headers=admin).json()
    assert len(vistos) == 2


# ----------------------------------------------------------------- constancia

def test_cada_descarga_queda_registrada(cliente, admin, db, con_disco):
    """Un archivo deja de estar bajo el control del sistema en cuanto sale."""
    c = un_cliente(cliente, admin)
    doc = subir(cliente, admin, 'cliente', c['id']).json()
    cliente.get(RUTA + '/' + str(doc['id']) + '/contenido', headers=admin)

    reg = db.scalars(select(Auditoria).where(Auditoria.entidad == 'documentos',
                                             Auditoria.operacion == 'descargar')).all()
    assert len(reg) == 1, reg
    assert reg[0].entidad_id == doc['id']
    assert reg[0].usuario_id


def test_la_auditoria_no_repite_el_nombre_del_archivo(cliente, admin, db, con_disco):
    """El nombre de un soporte suele ser el de la persona."""
    c = un_cliente(cliente, admin)
    subir(cliente, admin, 'cliente', c['id'], nombre='Pasaporte Aura Isabel Basante.pdf')
    reg = db.scalars(select(Auditoria).where(Auditoria.entidad == 'documentos')).first()
    assert reg is not None
    assert 'Aura Isabel' not in str(reg.despues), reg.despues


def test_borrar_quita_el_archivo_del_disco(cliente, admin, db, con_disco):
    c = un_cliente(cliente, admin)
    doc = subir(cliente, admin, 'cliente', c['id']).json()
    assert len(archivos_de(con_disco)) == 1

    r = cliente.delete(RUTA + '/' + str(doc['id']), headers=admin)
    assert r.status_code == 204, r.text
    assert archivos_de(con_disco) == [], 'quedo el archivo huerfano en el disco'
    db.expire_all()
    assert db.get(Documentos, doc['id']) is None
