"""Consultar la auditoria (RF-076).

La auditoria se escribia desde el primer dia y nadie podia leerla. Lo que estas
pruebas vigilan es que ahora se pueda, que solo la pueda leer quien debe, y que
leerla no sea la puerta de atras para ver datos de personas que ya se
anonimizaron: la tabla es inalterable, asi que lo que entre ahi se queda.
"""
import pytest
from sqlalchemy import select, text

from app.models.esquema import Auditoria
from tests.conftest import entrar


@pytest.fixture
def admin(cliente, usuario):
    return entrar(cliente, usuario('administradora'))


def un_cliente(cliente, cab, nombre, **extra):
    return cliente.post('/api/v1/clientes', headers=cab,
                        json={'nombre': nombre, **extra}).json()


# ------------------------------------------------------------- se puede leer

def test_la_auditoria_se_puede_consultar(cliente, admin, db):
    un_cliente(cliente, admin, 'Auditada Consulta Cliente')
    r = cliente.get('/api/v1/auditoria?entidad=clientes&operacion=insert', headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d['total'] >= 1
    uno = d['items'][0]
    assert uno['entidad'] == 'clientes' and uno['operacion'] == 'insert'
    assert uno['usuario'], 'tiene que decir quien, no solo el id'
    assert uno['campos'], 'y que campos toco'


def test_responde_que_le_paso_a_este_registro(cliente, admin, db):
    """La pregunta real no es «que paso ayer» sino «que le paso a este cliente»."""
    c = un_cliente(cliente, admin, 'Historia Suya Cliente')
    cliente.patch(f'/api/v1/clientes/{c["id"]}', headers=admin, json={'ciudad': 'Cali'})

    d = cliente.get(f'/api/v1/auditoria?entidad=clientes&entidad_id={c["id"]}',
                    headers=admin).json()
    assert d['total'] >= 2, d
    assert {x['operacion'] for x in d['items']} >= {'insert', 'update'}
    assert all(x['entidad_id'] == c['id'] for x in d['items'])


def test_el_mas_reciente_va_primero(cliente, admin, db):
    un_cliente(cliente, admin, 'Primera Enorden Cliente')
    un_cliente(cliente, admin, 'Segunda Enorden Cliente')
    items = cliente.get('/api/v1/auditoria?entidad=clientes', headers=admin).json()['items']
    assert [x['id'] for x in items] == sorted((x['id'] for x in items), reverse=True)


def test_los_filtros_salen_de_lo_que_hay_y_no_de_una_lista_escrita_a_mano(cliente, admin,
                                                                          db):
    un_cliente(cliente, admin, 'Filtros Reales Cliente')
    f = cliente.get('/api/v1/auditoria/filtros', headers=admin).json()
    assert 'clientes' in f['entidades']
    assert 'insert' in f['operaciones']
    reales = {r for (r,) in db.execute(select(Auditoria.entidad).distinct())}
    assert set(f['entidades']) == reales, 'nada de mas y nada de menos'


def test_pagina(cliente, admin, db):
    for i in range(4):
        un_cliente(cliente, admin, f'Paginada Numero{i} Cliente')
    d = cliente.get('/api/v1/auditoria?entidad=clientes&tamano=2&pagina=1',
                    headers=admin).json()
    assert len(d['items']) == 2 and d['total'] > 2
    dos = cliente.get('/api/v1/auditoria?entidad=clientes&tamano=2&pagina=2',
                      headers=admin).json()
    assert {x['id'] for x in d['items']}.isdisjoint({x['id'] for x in dos['items']})


# ----------------------------------------------------- pero no cualquiera

def test_quien_no_audita_no_lee_la_auditoria(cliente, usuario):
    for rol in ('comercial', 'operaciones'):
        cab = entrar(cliente, usuario(rol))
        assert cliente.get('/api/v1/auditoria', headers=cab).status_code == 403, rol
        assert cliente.get('/api/v1/auditoria/filtros', headers=cab).status_code == 403


def test_leer_la_auditoria_no_es_la_puerta_de_atras_a_los_datos_personales(cliente,
                                                                           admin, db):
    """Si la auditoria devolviera el registro completo de cuando se creo un
    cliente, bastaria con abrirla para recuperar a una persona anonimizada. Y la
    tabla es inalterable: no se puede limpiar despues."""
    un_cliente(cliente, admin, 'Noseve Enauditoria Cliente',
               telefono='3009998877', email='noseve@ejemplo.com')

    d = cliente.get('/api/v1/auditoria?entidad=clientes', headers=admin).json()
    texto = str(d)
    assert 'Noseve Enauditoria' not in texto
    assert '3009998877' not in texto and 'noseve@ejemplo.com' not in texto
    # Pero si se ve QUE se tocaron esos campos.
    uno = next(x for x in d['items'] if x['operacion'] == 'insert')
    assert 'nombre' in uno['campos'] and 'telefono' in uno['campos']


def test_la_auditoria_sigue_sin_poder_modificarse(cliente, admin, db):
    """RNF-05. El visor solo lee, pero la garantia no es que el visor se porte
    bien: es que la base no deja cambiarla ni aunque alguien lo intente."""
    import sqlalchemy.exc

    un_cliente(cliente, admin, 'Inalterable Prueba Cliente')
    fila = db.scalar(select(Auditoria.id).order_by(Auditoria.id.desc()))
    assert fila is not None, 'hace falta una fila para que el trigger -por fila- dispare'

    for sql in ('update auditoria set operacion = :v where id = :i',
                'delete from auditoria where id = :i'):
        with pytest.raises(sqlalchemy.exc.DBAPIError) as e:
            db.execute(text(sql), {'v': 'trucada', 'i': fila})
            db.flush()
        assert 'inalterable' in str(e.value).lower(), sql
        db.rollback()


def test_las_filas_viejas_tampoco_se_sirven_con_los_datos_adentro(cliente, admin, db):
    """Hasta hoy la auditoria guardaba el registro completo, y esas filas siguen
    ahi: la tabla es inalterable y no se pueden limpiar.

    Si el visor se fiara de que lo guardado ya viene limpio, abrirlo seria la
    forma de recuperar el nombre y el telefono de cualquiera -incluida una
    persona ya anonimizada-. Por eso oculta otra vez al servir.
    """
    db.execute(text("""insert into auditoria (usuario_id, operacion, entidad, entidad_id,
                                              despues, ocurrido_en)
                       values (null, 'insert', 'clientes', 999123,
                               '{"nombre": "Vieja Fila Conelnombre",
                                 "telefono": "3115554444",
                                 "ciudad": "Pereira"}'::jsonb, now())"""))
    db.commit()

    d = cliente.get('/api/v1/auditoria?entidad=clientes&entidad_id=999123',
                    headers=admin).json()
    assert d['total'] == 1, d
    fila = d['items'][0]
    assert 'Vieja Fila' not in str(fila), fila
    assert '3115554444' not in str(fila), fila
    # Lo que no identifica si se sigue viendo, que es de lo que sirve el registro.
    assert fila['despues']['ciudad'] == 'Pereira'
    assert 'nombre' in fila['campos'] and 'telefono' in fila['campos']
