"""Volver a cargar el Excel cuando VisaNow lo cambia.

La migracion no se corre una vez y ya: Laura manda el libro corregido cada
tanto. Lo que vigilan estas pruebas son las dos cosas que descubrimos al cargar
el libro del 13 de octubre, y que no fallaban en ningun lado hasta que se
intentaba de verdad.
"""
import datetime as dt

import pytest
from sqlalchemy import text

from tests.conftest import entrar


# --------------------------------------- una hoja que ya no esta en el libro

def test_una_hoja_que_desaparecio_no_deja_inservible_la_carga_entera(tmp_path,
                                                                     monkeypatch):
    """VisaNow reorganiza su Excel: hojas que se renombran, que se parten, que
    se borran. La hoja ADELANTOS desaparecio entre un libro y el siguiente, y la
    carga entera reventaba con un KeyError.

    Que no reviente no significa pasarla por alto: puede ser un borrado por
    error, y serian tramites o plata que no entran. Por eso se avisa.
    """
    import openpyxl

    from app.migracion import fuentes

    libro = openpyxl.Workbook()
    libro.active.title = 'SOLO ESTA'
    ruta = tmp_path / 'CUENTAS VISANOW.xlsx'
    libro.save(ruta)
    monkeypatch.setattr(fuentes, 'FUENTE', tmp_path)

    presentes = [h for h in fuentes.CATALOGO if fuentes.existe(h)]
    ausentes = [h for h in fuentes.CATALOGO if not fuentes.existe(h)]
    assert ausentes, 'con un libro vacio tendrian que faltar hojas'
    assert not presentes, 'y ninguna deberia estar'


def test_existe_reconoce_la_hoja_que_si_esta(tmp_path, monkeypatch):
    """Si `existe` dijera que no siempre, la carga se saltaria todo en silencio,
    que es peor que reventar."""
    import openpyxl

    from app.migracion import fuentes

    alguna = fuentes.CATALOGO[0]
    libro = openpyxl.Workbook()
    libro.active.title = alguna.nombre
    libro.save(tmp_path / alguna.archivo)
    monkeypatch.setattr(fuentes, 'FUENTE', tmp_path)

    assert fuentes.existe(alguna) is True


# ------------------------- borrar lo migrado cuando ya hay cosas colgando

@pytest.fixture
def una_venta_migrada(cliente, db, usuario):
    """Una venta y un pago que parecen venir del Excel, como los de verdad."""
    cab = entrar(cliente, usuario('administradora'))
    c = cliente.post('/api/v1/clientes', headers=cab,
                     json={'nombre': 'Recargada Prueba Cliente'}).json()
    db.execute(text("""
        insert into negocios (cliente_id, servicio_id, fecha_venta, cantidad_solicitantes,
                              valor_lista, valor_pactado, moneda,
                              origen_archivo, origen_hoja, origen_fila)
        values (:c, (select id from servicios limit 1), current_date, 1, 1000000, 1000000,
                'COP', 'CUENTAS VISANOW.xlsx', 'PAGOS', 9999)"""), {'c': c['id']})
    db.execute(text("""
        insert into pagos (negocio_id, fecha, monto_bruto, costo_medio,
                           moneda, estado, medio_pago_id,
                           origen_archivo, origen_hoja, origen_fila)
        select n.id, current_date, 400000, 0, 'COP', 'confirmado',
               (select id from medios_pago limit 1),
               'CUENTAS VISANOW.xlsx', 'PAGOS', 9999
          from negocios n where n.origen_fila = 9999"""))
    db.commit()
    return db.execute(text('select id from pagos where origen_fila = 9999')).scalar()


def test_borrar_lo_migrado_suelta_el_extracto_del_banco_en_vez_de_tirarlo(
        db, una_venta_migrada):
    """El extracto existe por su cuenta: son las filas que mando el banco, no
    algo que VisaNow haya escrito. Si volver a cargar el Excel se las llevara,
    habria que volver a importar el extracto cada vez.

    Lo que si tiene que pasar es que el movimiento vuelva a «sin conciliar»:
    el pago con el que estaba cruzado ya no existe.
    """
    from app.migracion.carga import limpiar

    db.execute(text("""
        insert into movimientos_banco (banco, fecha, valor, descripcion, huella,
                                       estado, pago_id)
        values ('BANCOLOMBIA', current_date, 400000, 'ABONO DE PRUEBA',
                'huella-de-prueba-recarga', 'conciliado', :p)"""),
        {'p': una_venta_migrada})
    db.commit()

    limpiar(db)
    db.expire_all()

    fila = db.execute(text("""select estado, pago_id from movimientos_banco
                              where huella = 'huella-de-prueba-recarga'""")).first()
    assert fila is not None, 'el movimiento del banco no se puede borrar'
    assert fila[0] == 'sin_conciliar', 'tiene que volver a estar pendiente'
    assert fila[1] is None, 'y sin apuntar a un pago que ya no existe'

    # Y lo migrado si se fue.
    assert db.execute(text('select count(*) from pagos where origen_fila = 9999')).scalar() == 0
    assert db.execute(text('select count(*) from negocios where origen_fila = 9999')).scalar() == 0


def test_borrar_lo_migrado_no_toca_lo_que_se_cargo_a_mano(cliente, db, usuario):
    """Es la garantia que hace que `limpiar` se pueda correr sin miedo: lo que
    el equipo escribio desde la aplicacion no lleva `origen_archivo`."""
    from app.migracion.carga import limpiar

    cab = entrar(cliente, usuario('administradora'))
    c = cliente.post('/api/v1/clientes', headers=cab,
                     json={'nombre': 'Amano Nosetoca Cliente'}).json()
    db.commit()

    limpiar(db)
    db.expire_all()

    quedan = db.execute(text('select count(*) from clientes where id = :c'),
                        {'c': c['id']}).scalar()
    assert quedan == 1, 'se borro un cliente que nadie migro'
