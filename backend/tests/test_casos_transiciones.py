"""El mapa de estados, la excepción autorizada, el checklist por modalidad, el
resultado y el por qué de cada cambio (RF-023, RF-025, RF-027, RF-028).

Lo que se prueba aquí es lo que ningún Excel puede hacer cumplir: que nadie
avance sin lo que el paso exige, que saltárselo deje huella con nombre y motivo
en la auditoría, que un trámite que se dañó pueda cerrarse y volver a abrirse, y
que el historial conteste «por qué».
"""
import pytest
from sqlalchemy import select

from app.models.esquema import (
    Auditoria,
    CasosHistorial,
    EstadosOperativos,
    Modalidades,
    Paises,
    Sedes,
    TiposVisa,
    TransicionesOperativas,
)
from tests.conftest import entrar

CASOS = '/api/v1/casos'

# Los estados en que el trámite ya está andando: hay formulario enviado, cita,
# documentos o resultado. Son los que de verdad se dañan —el cliente desiste, le
# niegan la cita, se le vence el pasaporte— y son los que no tenían salida.
TARDIOS = ('formulario_enviado', 'cita_confirmada', 'preparacion', 'checklist',
           'esperando_resultado', 'con_resultado', 'entrega_documento')


@pytest.fixture
def operaciones(cliente, usuario):
    p = usuario('operaciones')
    return entrar(cliente, p), p


@pytest.fixture
def administradora(cliente, usuario):
    p = usuario('administradora')
    return entrar(cliente, p), p


@pytest.fixture
def solicitante(cliente, usuario):
    """Un cliente con una persona lista para tramitar."""
    cab = entrar(cliente, usuario('comercial'))
    c = cliente.post('/api/v1/clientes', headers=cab,
                     json={'nombre': 'Cliente de Transiciones'}).json()
    s = cliente.post('/api/v1/solicitantes', headers=cab,
                     json={'cliente_id': c['id'], 'nombre': 'Persona de Transiciones',
                           'pasaporte': f'TR{c["id"]:07d}'}).json()
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


def mover(cliente, cab, caso_id, destino, **extra):
    return cliente.post(f'{CASOS}/{caso_id}/estado', headers=cab,
                        json={'codigo_destino': destino, **extra})


def hasta(cliente, cab, caso_id, *estados):
    """Avanza el trámite por los estados que se le pasen, uno tras otro."""
    for destino in estados:
        r = mover(cliente, cab, caso_id, destino)
        assert r.status_code == 200, f'{destino}: {r.text}'


def ficha(cliente, cab, caso_id) -> dict:
    r = cliente.get(f'{CASOS}/{caso_id}', headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------- RF-023 · la excepción

def test_la_administradora_se_salta_el_checklist_y_queda_en_la_auditoria(
        cliente, db, operaciones, administradora, solicitante, pais_usa):
    """RF-023. El cliente llega con la carta laboral el día de la entrevista:
    alguien tiene que poder decidir que pase, y eso tiene que quedar con nombre
    propio. El permiso casos.excepcion existe para esto (app/seed.py), pero la
    excepción solo abría el ORDEN de los estados: el checklist seguía frenando
    a la administradora, que es justo quien lo puede autorizar."""
    cab, p = operaciones
    cab_admin, admin = administradora
    sede = db.scalar(select(Sedes.id).limit(1))
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    hasta(cliente, cab, caso['id'], 'esperando_info', 'info_en_revision',
          'formulario_elaborando', 'formulario_enviado', 'pago_consular_pend', 'busqueda_cita')
    cliente.post(f"{CASOS}/{caso['id']}/citas", headers=cab,
                 json={'tipo': 'entrevista', 'inicia_en': '2026-11-20T08:30:00-05:00'})
    assert mover(cliente, cab, caso['id'], 'cita_confirmada',
                 cambios={'sede_id': sede}).status_code == 200
    hasta(cliente, cab, caso['id'], 'checklist')

    # Operaciones no pasa con el checklist incompleto, y tampoco lo puede forzar
    r = mover(cliente, cab, caso['id'], 'esperando_resultado')
    assert r.status_code == 422 and r.json()['codigo'] == 'checklist_incompleto'
    assert mover(cliente, cab, caso['id'], 'esperando_resultado', forzar=True,
                 motivo='Dice la administradora').status_code == 403

    motivo = 'El cliente trae la carta laboral a la entrevista; lo autorizo yo'
    r = mover(cliente, cab_admin, caso['id'], 'esperando_resultado', forzar=True, motivo=motivo)
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'esperando_resultado'

    excepcion = db.scalar(select(CasosHistorial).where(CasosHistorial.caso_id == caso['id'],
                                                       CasosHistorial.campo == 'excepcion'))
    assert excepcion is not None, 'saltarse el checklist tiene que quedar como excepción'
    assert excepcion.observacion == motivo and excepcion.usuario_id == admin.u.id

    # «Auditada» es la tabla de auditoría, que no se puede modificar ni borrar
    # (RNF-05), no el historial del trámite, que es otra cosa.
    movimientos = db.scalars(select(Auditoria).where(Auditoria.entidad == 'casos',
                                                     Auditoria.entidad_id == caso['id'],
                                                     Auditoria.operacion == 'update')).all()
    auditada = [a for a in movimientos if a.despues and a.despues.get('excepcion')]
    assert len(auditada) == 1, 'la excepción tiene que quedar en la auditoría, una sola vez'
    assert auditada[0].usuario_id == admin.u.id
    assert auditada[0].despues['motivo'] == motivo
    assert auditada[0].antes['estado'] == 'checklist'
    assert auditada[0].despues['estado'] == 'esperando_resultado'


def test_un_tramite_que_se_dana_tarde_se_puede_mandar_a_excepcion(
        cliente, db, operaciones, solicitante, pais_usa):
    """RF-023. Un trámite no se daña al principio: se daña cuando ya hay
    formulario enviado, cita o resultado. Sin salida desde esos estados la única
    forma de cerrarlo era pedirle a la administradora que se saltara el proceso,
    y lo más común del negocio quedaba registrado como algo extraordinario."""
    excepcion_id = db.scalar(select(EstadosOperativos.id)
                             .where(EstadosOperativos.codigo == 'excepcion'))
    con_salida = set(db.scalars(
        select(EstadosOperativos.codigo)
        .join(TransicionesOperativas,
              TransicionesOperativas.estado_origen_id == EstadosOperativos.id)
        .where(TransicionesOperativas.estado_destino_id == excepcion_id)))
    assert set(TARDIOS) <= con_salida, f'no se puede cancelar desde: {set(TARDIOS) - con_salida}'

    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    hasta(cliente, cab, caso['id'], 'esperando_info', 'info_en_revision',
          'formulario_elaborando', 'formulario_enviado')
    r = mover(cliente, cab, caso['id'], 'excepcion', resultado='no_continuo',
              motivo='Se fue de viaje sin avisar y no volvió a responder')
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'excepcion' and r.json()['es_final'] is True
    assert r.json()['resultado'] == 'no_continuo'
    assert r.json()['resultado_fecha'], 'un resultado sin fecha no se puede contar por mes'


def test_un_tramite_en_excepcion_se_puede_retomar(cliente, operaciones, solicitante, pais_usa):
    """RF-023. El cliente que aplazó en marzo vuelve en agosto. «Cancelado / no
    continuó / suspendido» es un estado final, pero no puede ser una tumba: sin
    ninguna salida había que crear otro trámite, y entonces la persona aparece
    dos veces y todo lo que ya se hizo se queda en el trámite enterrado."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    r = mover(cliente, cab, caso['id'], 'excepcion', resultado='cancelado',
              motivo='El cliente aplazó el viaje para el año entrante')
    assert r.status_code == 200, r.text
    assert r.json()['es_final'] is True

    salidas = {e['codigo'] for e in ficha(cliente, cab, caso['id'])['estados_posibles']}
    assert salidas, 'de la excepción tiene que salir algo: la pantalla esconde «Mover» sin salidas'
    assert 'esperando_info' in salidas, 'se retoma pidiendo otra vez la información'

    r = mover(cliente, cab, caso['id'], 'esperando_info',
              motivo='El cliente volvió; los documentos de marzo ya no sirven')
    assert r.status_code == 200, r.text
    assert r.json()['estado'] == 'esperando_info' and r.json()['es_final'] is False


def test_la_administradora_puede_abrir_una_transicion_desde_el_panel():
    """RF-023. El mapa de estados era la única configuración del proceso que no
    se podía tocar en ninguna parte: vivía en el seed, así que abrir una salida
    —el consulado pide documentos y el trámite vuelve atrás (221g)— necesitaba
    un despliegue. La operación cambia cuando cambia el consulado."""
    from app.db.session import SesionLocal
    from tests.test_admin import _entrar, _usuario_real

    with SesionLocal() as s:
        origen = s.scalar(select(EstadosOperativos.id)
                          .where(EstadosOperativos.codigo == 'esperando_resultado'))
        destino = s.scalar(select(EstadosOperativos.id)
                           .where(EstadosOperativos.codigo == 'esperando_info'))
        assert s.get(TransicionesOperativas, (origen, destino)) is None

    from fastapi.testclient import TestClient

    from app.main import app
    try:
        with TestClient(app) as panel:
            quien = _usuario_real('administradora')
            _entrar(panel, quien)
            r = panel.post('/admin/transiciones-operativas/create', data={
                'estado_origen': str(origen), 'estado_destino': str(destino),
                'campos_obligatorios': '["proxima_accion"]', 'save': 'Save'})
            assert r.status_code == 200, r.text[:500]

            with SesionLocal() as s:
                nueva = s.get(TransicionesOperativas, (origen, destino))
                assert nueva is not None, 'la transición nueva no quedó guardada'
                assert nueva.requiere_checklist is False
                assert nueva.campos_obligatorios == ['proxima_accion']
                # El panel audita solo (eventos de su sesión): sin esto, cambiar
                # el proceso sería el único cambio del sistema sin responsable.
                registro = s.scalar(select(Auditoria)
                                    .where(Auditoria.entidad == 'transiciones_operativas',
                                           Auditoria.usuario_id == quien.id)
                                    .order_by(Auditoria.id.desc()))
                assert registro is not None and registro.operacion == 'insert'

            # Y lo que exige se ajusta sin volver a crearla
            r = panel.post(f'/admin/transiciones-operativas/edit/{origen};{destino}',
                           data={'requiere_checklist': 'on', 'campos_obligatorios': '[]',
                                 'save': 'Save'})
            assert r.status_code == 200, r.text[:500]
            with SesionLocal() as s:
                assert s.get(TransicionesOperativas, (origen, destino)).requiere_checklist is True
    finally:
        # Se deja el mapa como estaba: es estado compartido por toda la suite.
        with SesionLocal() as s:
            fila = s.get(TransicionesOperativas, (origen, destino))
            if fila is not None:
                s.delete(fila)
                s.commit()


# ------------------------------------------- RF-027 · el resultado del trámite

def test_cerrar_por_excepcion_tambien_exige_decir_en_que_quedo(
        cliente, operaciones, solicitante, pais_usa):
    """RF-027 y RN-06. «Cancelado» y «no continuó» son dos de los cinco
    resultados, y son los del trámite que se manda a excepción: mientras no se
    pidieran al cerrar, no se registraban nunca y el informe por resultado no
    sumaba lo mismo que el tablero. Y se registran con el trámite todavía
    abierto: el resultado del consulado y el cierre del servicio son cosas
    distintas, una visa negada puede tener pendiente la entrega del pasaporte."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    r = mover(cliente, cab, caso['id'], 'excepcion', motivo='Dejó de contestar')
    assert r.status_code == 422 and r.json()['codigo'] == 'falta_resultado', r.text

    r = cliente.post(f"{CASOS}/{caso['id']}/resultado", headers=cab,
                     json={'resultado': 'no_continuo', 'nota': 'Dejó de contestar en septiembre'})
    assert r.status_code == 200 and r.json()['resultado'] == 'no_continuo'
    assert r.json()['es_final'] is False, 'registrar el resultado no cierra el trámite'
    assert r.json()['resultado_fecha'], 'el resultado se guarda con su fecha (en hora de Bogotá)'

    r = mover(cliente, cab, caso['id'], 'excepcion', motivo='Dejó de contestar')
    assert r.status_code == 200, r.text
    assert r.json()['resultado'] == 'no_continuo' and r.json()['es_final'] is True


# ----------------------------------------------- RF-025 · checklist por modalidad

def test_el_checklist_lo_decide_tambien_la_modalidad(
        cliente, db, operaciones, solicitante, pais_usa):
    """RF-025. La ficha del cliente dice que la modalidad «decide qué checklist
    de documentos se aplica» y ninguna consulta la leía: al que renueva se le
    pedían los soportes económicos de una primera vez, y al que va por primera
    vez sin tipo de visa registrado se le pedía la visa anterior que no tiene."""
    cab, p = operaciones
    b1b2 = db.scalar(select(TiposVisa.id).where(TiposVisa.codigo == 'B1B2'))
    renovacion = db.scalar(select(Modalidades.id).where(Modalidades.codigo == 'renovacion'))
    menores = db.scalar(select(Modalidades.id).where(Modalidades.codigo == 'menores'))

    def documentos(**extra) -> list[str]:
        caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id, **extra)
        nombres = [i['nombre'] for i in ficha(cliente, cab, caso['id'])['checklist']]
        assert nombres, 'todo trámite tiene al menos la lista básica'
        assert len(nombres) == len(set(nombres)), f'documentos repetidos: {nombres}'
        return nombres

    renueva = documentos(tipo_visa_id=b1b2, modalidad_id=renovacion)
    assert 'Visa anterior o pasaporte con la visa' in renueva, 'la modalidad manda sobre el tipo'
    assert 'Soportes económicos (extractos de 3 meses)' not in renueva, 'eso es de primera vez'

    menor = documentos(tipo_visa_id=b1b2, modalidad_id=menores)
    assert 'Autorización de los padres, autenticada en notaría' in menor

    sin_modalidad = documentos()
    assert 'Visa anterior o pasaporte con la visa' not in sin_modalidad, \
        'a un trámite sin modalidad no se le puede aplicar la lista de renovación'


def test_el_checklist_dice_quien_marco_cada_documento_y_con_que_nota(
        cliente, operaciones, solicitante, pais_usa):
    """RF-025. El servicio ya guardaba el quién, el cuándo y la nota de cada
    documento, pero no salían por ninguna parte: para saber quién había dicho
    que el soporte estaba había que leerse el historial completo."""
    cab, p = operaciones
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    primero = ficha(cliente, cab, caso['id'])['checklist'][0]
    assert primero['cumplido'] is False and primero['cumplido_por'] is None

    nota = 'El pasaporte vence en enero; alcanza para la cita'
    r = cliente.post(f"{CASOS}/{caso['id']}/checklist/{primero['item_id']}", headers=cab,
                     json={'cumplido': True, 'observacion': nota})
    assert r.status_code == 204, r.text
    marcado = next(i for i in ficha(cliente, cab, caso['id'])['checklist']
                   if i['item_id'] == primero['item_id'])
    assert marcado['cumplido'] is True and marcado['cumplido_en']
    assert marcado['cumplido_por'] == p.u.nombre
    assert marcado['observacion'] == nota

    # Desmarcar la casilla no se lleva por delante la nota que alguien escribió
    r = cliente.post(f"{CASOS}/{caso['id']}/checklist/{primero['item_id']}", headers=cab,
                     json={'cumplido': False})
    assert r.status_code == 204, r.text
    quitado = next(i for i in ficha(cliente, cab, caso['id'])['checklist']
                   if i['item_id'] == primero['item_id'])
    assert quitado['cumplido'] is False and quitado['cumplido_por'] is None
    assert quitado['observacion'] == nota


# -------------------------------------------------- RF-028 · el por qué

def test_el_cambio_de_responsable_puede_llevar_su_motivo(
        cliente, usuario, operaciones, solicitante, pais_usa):
    """RF-028. El historial ya decía qué cambió, de qué a qué, cuándo y quién.
    Lo que no se podía responder es «por qué le cambiaron el responsable a este
    trámite», que es justo lo que se pregunta cuando algo se quedó quieto: en el
    cambio de estado el motivo existía, en el de campos no había dónde."""
    cab, p = operaciones
    otra = usuario('operaciones')
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)

    motivo = 'La asesora salió a vacaciones; lo sigue la otra hasta el 30'
    r = cliente.patch(f"{CASOS}/{caso['id']}", headers=cab,
                      json={'responsable_id': otra.u.id, 'motivo': motivo})
    assert r.status_code == 200, r.text

    historial = cliente.get(f"{CASOS}/{caso['id']}/historial", headers=cab).json()
    linea = next(h for h in historial if h['campo'] == 'responsable_id')
    assert linea['valor_anterior'] == str(p.u.id) and linea['valor_nuevo'] == str(otra.u.id)
    assert linea['usuario'] == p.u.nombre
    assert linea['observacion'] == motivo, 'el por qué del cambio de campo no quedó guardado'


# ------------------- la fecha del consulado, que no es la de hoy (RF-027/028)

def test_mover_de_estado_no_le_pisa_la_fecha_del_consulado_con_la_de_hoy(
        cliente, db, operaciones, administradora, solicitante, pais_usa):
    """Una visa aprobada el 15 de marzo quedaba aprobada hoy.

    La pantalla manda siempre `resultado_fecha: datos.resultado_fecha || null`,
    así que mover de estado un trámite que ya tenía fecha —sin intención de
    tocarla— llegaba como «ponla en null»; el autollenado que va justo después
    veía el hueco y le ponía la de hoy. Sobre 501 ventas eso corre los conteos
    por mes, y el historial encima escribía «2026-03-15 → None», que no era ni
    lo que había antes ni lo que quedó guardado.
    """
    cab, p = operaciones
    cab_admin, _ = administradora
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)

    r = cliente.post(f"{CASOS}/{caso['id']}/resultado", headers=cab,
                     json={'resultado': 'aprobada', 'fecha': '2026-03-15',
                           'nota': 'Aprobada en la entrevista de marzo'})
    assert r.status_code == 200, r.text
    assert ficha(cliente, cab, caso['id'])['resultado_fecha'] == '2026-03-15'

    # El movimiento que la pantalla hace: manda el resultado y la fecha vacía
    # (`resultado_fecha: datos.resultado_fecha || null`).
    r = mover(cliente, cab_admin, caso['id'], 'excepcion',
              motivo='El cliente desiste y hay que cerrarlo',
              resultado='cancelado', resultado_fecha=None)
    assert r.status_code == 200, r.text

    despues = ficha(cliente, cab, caso['id'])
    assert despues['resultado_fecha'] == '2026-03-15', (
        'le pisó la fecha de la decisión consular con la de hoy')
    assert despues['resultado_nota'] == 'Aprobada en la entrevista de marzo', (
        'le borró la nota')

    borrados = db.scalars(select(CasosHistorial).where(
        CasosHistorial.caso_id == caso['id'],
        CasosHistorial.campo == 'resultado_fecha')).all()
    assert not borrados, (
        'escribió en el historial un cambio de fecha que no ocurrió: '
        f'{[(h.valor_anterior, h.valor_nuevo) for h in borrados]}')


def test_la_transicion_que_exige_la_fecha_del_resultado_la_sigue_exigiendo(
        cliente, db, operaciones, administradora, solicitante, pais_usa):
    """RF-023: `esperando_resultado → con_resultado` pide resultado Y fecha.

    El autollenado de la fecha corría ANTES de validar los campos obligatorios,
    así que el campo quedaba siempre puesto y la exigencia no podía fallar
    nunca. El efecto no es de formulario: de ahí en adelante el camino normal
    para registrar un resultado habría sellado el día en que alguien lo digitó,
    no el de la decisión del consulado.
    """
    exigidos = db.scalar(select(TransicionesOperativas.campos_obligatorios).where(
        TransicionesOperativas.estado_origen_id == select(EstadosOperativos.id).where(
            EstadosOperativos.codigo == 'esperando_resultado').scalar_subquery(),
        TransicionesOperativas.estado_destino_id == select(EstadosOperativos.id).where(
            EstadosOperativos.codigo == 'con_resultado').scalar_subquery()))
    assert 'resultado_fecha' in (exigidos or []), (
        'esta prueba se apoya en que el sembrado exija la fecha; si cambió, hay '
        'que revisarla en vez de borrarla')

    cab, p = operaciones
    cab_admin, _ = administradora
    sede = db.scalar(select(Sedes.id).limit(1))
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)
    hasta(cliente, cab, caso['id'], 'esperando_info', 'info_en_revision',
          'formulario_elaborando', 'formulario_enviado', 'pago_consular_pend',
          'busqueda_cita')
    cliente.post(f"{CASOS}/{caso['id']}/citas", headers=cab,
                 json={'tipo': 'entrevista', 'inicia_en': '2026-11-20T08:30:00-05:00'})
    assert mover(cliente, cab, caso['id'], 'cita_confirmada',
                 cambios={'sede_id': sede}).status_code == 200
    hasta(cliente, cab, caso['id'], 'preparacion', 'checklist')

    # El checklist no es lo que esta prueba mira, así que se pasa con la
    # excepción autorizada, igual que la prueba del checklist de más arriba.
    r = mover(cliente, cab_admin, caso['id'], 'esperando_resultado', forzar=True,
              motivo='Lo que se prueba acá es la fecha, no el checklist')
    assert r.status_code == 200, r.text

    # Con el resultado pero sin la fecha: tiene que rebotar, no autollenarse.
    r = mover(cliente, cab, caso['id'], 'con_resultado',
              resultado='aprobada', resultado_fecha=None)
    assert r.status_code == 422, r.text
    assert r.json()['codigo'] == 'faltan_campos', r.text

    # Y con la fecha, pasa y queda la que se mandó.
    r = mover(cliente, cab, caso['id'], 'con_resultado',
              resultado='aprobada', resultado_fecha='2026-04-02')
    assert r.status_code == 200, r.text
    assert ficha(cliente, cab, caso['id'])['resultado_fecha'] == '2026-04-02'


def test_un_tramite_retomado_suelta_el_resultado_que_tenia(
        cliente, db, operaciones, administradora, solicitante, pais_usa):
    """Cerrar sin decir en qué quedó y reabrir sin soltarlo son el mismo error.

    Un trámite que volvió a abrirse —el cliente desistió y volvió— se quedaba
    con el «cancelado» pegado: salía cancelado en la exportación estando en
    curso, y si el resultado era «aprobada» disparaba la alerta de visa aprobada
    sin cerrar. Es el espejo exacto de la regla que sí estaba.
    """
    cab, p = operaciones
    cab_admin, _ = administradora
    caso = crear_caso(cliente, cab, solicitante, pais_usa, p.u.id)

    r = mover(cliente, cab_admin, caso['id'], 'excepcion',
              motivo='El cliente desiste por ahora',
              resultado='cancelado', resultado_fecha='2026-05-10')
    assert r.status_code == 200, r.text
    cerrado = ficha(cliente, cab, caso['id'])
    assert cerrado['es_final'] is True and cerrado['resultado'] == 'cancelado'

    # Vuelve: la excepción tiene salida (RF-023) y el trámite se retoma.
    r = mover(cliente, cab, caso['id'], 'esperando_info',
              motivo='El cliente volvió y quiere seguir')
    assert r.status_code == 200, r.text

    retomado = ficha(cliente, cab, caso['id'])
    assert retomado['es_final'] is False
    assert retomado['resultado'] is None, (
        'quedó abierto y cancelado a la vez: así sale cancelado en la '
        'exportación estando en curso')
    assert retomado['resultado_fecha'] is None

    # Y no se perdió: quedó en el historial, que es donde se pregunta por qué.
    suelto = db.scalars(select(CasosHistorial).where(
        CasosHistorial.caso_id == caso['id'],
        CasosHistorial.campo == 'resultado')).all()
    assert any(h.valor_anterior == 'cancelado' and h.valor_nuevo is None
               for h in suelto), (
        'el resultado se dejó de afirmar pero tiene que quedar en el historial: '
        f'{[(h.valor_anterior, h.valor_nuevo) for h in suelto]}')
