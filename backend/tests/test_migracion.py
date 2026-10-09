"""Actividad 6.1 — lectura, normalización y unificación para la migración.

Se prueban las reglas que se rompen sin hacer ruido: las que producen un dato
plausible pero equivocado. Un teléfono con un dígito de más, una cita cinco
horas antes, dos hermanos convertidos en una sola persona. Nada de eso lanza un
error: entra a la base y se descubre meses después.
"""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from app.core import homologacion as hom
from app.migracion import lectura
from app.migracion.identidad import Resolvedor
from app.migracion.normalizacion import (es_nombre_de_persona, limpiar_anotaciones,
                                         nombres_compatibles, normalizar_telefono,
                                         partir_personas)

BOGOTA = ZoneInfo('America/Bogota')


# ------------------------------------------------------------------- lectura

def test_un_numero_entero_no_gana_un_decimal_falso():
    """Excel guarda el celular como número. `str(3001234567.0)` produce
    «3001234567.0» y ese «.0» se vuelve un dígito que nadie marcó."""
    assert lectura.texto(3001234567.0).valor == '3001234567'
    assert lectura.texto(2.5).valor == '2.5'


@pytest.mark.parametrize('error', ['#VALUE!', '#REF!', '#N/A', '#DIV/0!'])
def test_un_error_de_excel_no_se_lee_como_texto(error):
    """`data_only=True` devuelve el error de la fórmula como la cadena
    «#VALUE!». Sin esto, un cliente se llamaría «#VALUE!»."""
    c = lectura.texto(error)
    assert c.valor is None and 'error de Excel' in c.problema


def test_una_fecha_sin_zona_queda_en_hora_de_colombia():
    """El servidor PostgreSQL corre en UTC. Una cita de las 8:30 a. m. leída sin
    zona se guarda cinco horas antes: a las 3:30 de la madrugada."""
    c = lectura.fecha(dt.datetime(2027, 2, 11, 8, 30))
    assert c.valor.tzinfo is not None
    assert c.valor.utcoffset() == dt.timedelta(hours=-5)
    assert c.valor.astimezone(dt.timezone.utc).hour == 13


def test_un_serial_imposible_no_se_convierte_en_fecha():
    """Diez celdas de los archivos traen números de serie astronómicos. Sin este
    freno se cargarían como fechas del año 8000."""
    c = lectura.fecha(3012719766.0)
    assert c.valor is None and c.problema


def test_una_fecha_fuera_del_periodo_del_negocio_se_marca():
    c = lectura.fecha(dt.datetime(2006, 5, 4))
    assert c.valor is None and 'fuera del periodo' in c.problema


@pytest.mark.parametrize('bruto, esperado', [
    (1250000, 1250000.0),
    ('$ 1.250.000', 1250000.0),
    ('1.250.000', 1250000.0),
    ('1250000', 1250000.0),
    ('1.250,50', 1250.5),
    ('  850000  ', 850000.0),
])
def test_los_montos_se_leen_con_separadores_colombianos(bruto, esperado):
    assert lectura.numero(bruto).valor == esperado


def test_un_monto_que_no_es_numero_se_reporta_en_vez_de_valer_cero():
    c = lectura.numero('por definir')
    assert c.valor is None and 'no es un número' in c.problema


# ------------------------------------------------------------------ teléfonos

@pytest.mark.parametrize('bruto, e164', [
    ('3105558899', '+573105558899'),
    ('+57 310 555 8899', '+573105558899'),
    ('57 310 555 8899', '+573105558899'),
    ('310-555-8899', '+573105558899'),
    ('+971 50 123 4567', '+971501234567'),
    ('+34 612 345 678', '+34612345678'),
])
def test_el_mismo_telefono_escrito_de_seis_formas_es_uno_solo(bruto, e164):
    """Si el asesor guarda «+57 310 555 8899» y la contabilidad «3105558899»,
    tienen que colapsar en el mismo número o el cliente queda partido en dos."""
    assert normalizar_telefono(bruto).e164 == e164


def test_un_numero_extranjero_no_se_descarta_por_no_tener_diez_digitos():
    """Hay clientes que atienden desde Dubái y Madrid. La regla colombiana de
    diez dígitos los borraría a todos."""
    t = normalizar_telefono('+971501234567')
    assert t.e164 and t.pais == 'AE'


def test_una_celda_con_dos_telefonos_toma_el_primero_y_lo_dice():
    t = normalizar_telefono('3105558899 / 3201112233')
    assert t.e164 == '+573105558899' and 'más de un número' in t.problema


def test_lo_que_no_es_un_telefono_se_reporta():
    assert normalizar_telefono('no tiene').problema
    assert normalizar_telefono('3105558899').problema is None


# --------------------------------------------------------------- los nombres

def test_las_anotaciones_no_son_parte_del_nombre():
    """Las hojas anotan el parentesco en la misma celda. Si se deja, la misma
    persona con y sin anotación queda como dos clientes."""
    nombre, nota = limpiar_anotaciones('MAXIMILIANO MINDIOLA (HIJO DE ALEJANDRA)')
    assert nombre == 'MAXIMILIANO MINDIOLA' and nota == 'HIJO DE ALEJANDRA'


def test_el_mismo_nombre_con_y_sin_segundo_apellido_es_la_misma_persona():
    assert nombres_compatibles('Ana María Gómez Ruiz', 'ana maria gomez')
    assert nombres_compatibles('ANA MARIA GOMEZ', 'Ana María Gómez')


def test_dos_hermanos_no_son_la_misma_persona():
    """Comparten apellido, teléfono y correo. Lo único que los distingue es el
    nombre de pila, y por eso es el nombre de pila el que decide."""
    assert not nombres_compatibles('Tomás Restrepo Gómez', 'Sara Restrepo Gómez')
    assert not nombres_compatibles('Restrepo Gómez', 'Sara Restrepo Gómez')


def test_un_error_de_tipeo_sigue_siendo_la_misma_persona():
    assert nombres_compatibles('Angie Lorena Lima', 'Amgie Lorena Lima')


def test_una_celda_con_dos_personas_se_parte_solo_si_las_dos_tienen_apellido():
    assert partir_personas('Ana Gómez y Luis Gómez') == ['Ana Gómez', 'Luis Gómez']
    assert partir_personas('María Pérez y familia') == ['María Pérez y familia']
    assert partir_personas('Pedro Ruiz y esposa') == ['Pedro Ruiz y esposa']


def test_lo_que_no_es_una_persona_no_entra_como_cliente():
    assert not es_nombre_de_persona('3054416203')
    assert not es_nombre_de_persona('N/A')
    assert not es_nombre_de_persona('')
    assert es_nombre_de_persona('Ana Gómez')


# ------------------------------------------------------------------ identidad

def test_el_telefono_compartido_no_convierte_a_una_familia_en_una_persona():
    """El caso más caro de equivocarse: la mamá contrata para los tres hijos con
    su celular. Fusionar por teléfono los volvería una sola ficha y mezclaría
    tres trámites."""
    r = Resolvedor()
    for nombre in ('Lucía Restrepo Ángel', 'Tomás Restrepo Gómez', 'Sara Restrepo Gómez'):
        r.agregar(nombre, telefono='3105558899')
    personas = r.resolver()
    assert len(personas) == 3
    assert all(p.conflictos for p in personas[:1]), 'debe quedar anotado que comparten teléfono'


def test_el_mismo_cliente_escrito_distinto_en_dos_hojas_es_uno_solo():
    r = Resolvedor()
    r.agregar('ANA MARIA GOMEZ RUIZ', telefono='3105558899', origen=('a.xlsx', 'PAGOS', 5))
    r.agregar('Ana María Gómez', telefono='+57 310 555 8899', origen=('b.xlsx', '2026', 9))
    personas = r.resolver()
    assert len(personas) == 1
    assert personas[0].nombre == 'ANA MARIA GOMEZ RUIZ'   # se conserva la más completa
    assert len(personas[0].menciones) == 2


def test_un_correo_compartido_por_muchos_no_identifica_a_nadie():
    """Hay correos que aparecen en diez filas con nombres distintos: son buzones
    de la agencia, no de un cliente. Usarlos como ancla crearía un cliente con
    diez trámites de gente distinta."""
    r = Resolvedor()
    for i in range(6):
        r.agregar(f'Cliente Numero{i} Apellido{i}', correo='visas@agencia.com')
    personas = r.resolver()
    assert len(personas) == 6


def test_dos_personas_sin_nada_en_comun_no_se_fusionan():
    r = Resolvedor()
    r.agregar('Ana Gómez', telefono='3105558899')
    r.agregar('Luis Pérez', telefono='3201112233')
    assert len(r.resolver()) == 2


# --------------------------------------------------------------- homologación

@pytest.mark.parametrize('bruto, codigo', [
    ('Listo', 'finalizado'), ('ZZfinalizado', 'finalizado'), ('f16-finalizado', 'finalizado'),
    ('Espera cliente', 'esperando_info'), ('3-espera info cliente', 'esperando_info'),
    ('cita confirmada', 'cita_confirmada'), ('9-cita confirmada', 'cita_confirmada'),
])
def test_las_escrituras_sucias_del_estado_llegan_al_mismo_codigo(bruto, codigo):
    assert hom.estado(bruto) == (codigo, None)


def test_un_estado_que_el_diccionario_no_conoce_no_se_inventa():
    codigo, problema = hom.estado('algo que nadie escribió nunca')
    assert codigo is None and 'no está en el diccionario' in problema


def test_lo_que_parece_resultado_pero_es_una_nota_comercial_se_separa():
    """La columna «Resultado» de ADELANTOS mezcla el resultado consular con
    notas del embudo. «POSIBLES INTERESADOS» no es un resultado de visa."""
    assert hom.resultado('APROBADA') == ('aprobada', None)
    assert hom.resultado('VISA NEGADA') == ('negada', None)
    assert hom.resultado('POSIBLES INTERESADOS') == (None, 'nota')


def test_las_variantes_del_mismo_servicio_llegan_al_mismo_codigo():
    for bruto in ('ASESORIA Y ADELANTO', 'ASESORIA + ADELANTO', 'asesoria - adelanto', 'PREMIUM'):
        assert hom.servicio(bruto)[0] == 'asesoria_adelanto'


def test_los_catorce_apodos_de_la_vendedora_son_la_misma_persona():
    for bruto in ('Angie', 'ANGY', 'Angie lorena', 'Amgisita', 'Angisita la más linda'):
        assert hom.vendedor(bruto)[0] == 'angie'


# La carga completa NO se prueba aquí. `aplicar()` hace commits de verdad y esta
# suite corre cada prueba dentro de un savepoint que se deshace al terminar: las
# dos cosas se pelean y la conexión se cae. Además, lo que hay que comprobar de
# la carga —que el saldo lo calcule la vista, que las citas queden en hora de
# Colombia, que correrla dos veces no duplique— hay que poder correrlo el día de
# la migración contra la base real, no solo contra una de pruebas.
#
# Por eso vive en la propia herramienta:  python -m app.migracion verificar
