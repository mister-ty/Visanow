"""Qué hoja aporta qué, y cómo se lee cada fila.

Los tres libros tienen 27 hojas. Diecisiete traen personas, seis traen dinero y
el resto son tableros calculados, listas de validación o restos. Aquí está
declarado, hoja por hoja, qué se lee y qué se deja fuera —y por qué—, porque
«no migrar» también es una decisión que hay que tomar a propósito y poder
defender después.

Dos decisiones que cambian los totales y conviene tener a la vista:

- **REV PAGOS no se lee.** Es la misma venta que PAGOS en la casi totalidad de
  sus filas, cortada en junio mientras PAGOS llega a septiembre. Migrarla
  duplicaría las ventas e inflaría la cartera con deuda que PAGOS ya registra
  como pagada.
- **EXTRACTO no se lee como pagos.** Es el extracto bancario: los mismos
  ingresos que ya están en PAGOS, más movimientos que no son de clientes.
  Sirve para cuadrar, no para cargar.
"""
from __future__ import annotations

import datetime as dt
import pathlib
from dataclasses import dataclass, field
from typing import Callable, Literal

from app.core import homologacion as hom
from app.migracion.lectura import Fila, leer_hoja
from app.migracion.normalizacion import es_nombre_de_persona, limpiar_anotaciones, partir_personas

FUENTE = pathlib.Path(__file__).resolve().parents[4] / '02_Datos_Fuente'

# Columnas que no se leen nunca: son credenciales de portales consulares en
# texto plano. La decisión D-09 las excluye de la migración y RNF-10 dice que el
# sistema nuevo no tiene dónde guardarlas.
COLUMNAS_PROHIBIDAS = {'CONTRASEÑA', 'CONTRASENA', 'CLAVE', 'PASSWORD'}


@dataclass
class Aporte:
    """Lo que una fila aporta. Todo es opcional: una fila de [PAGOS] aporta
    venta y pagos pero no trámite, y una de [2026] al revés."""
    persona: str | None = None
    telefono: str | None = None
    correo: str | None = None
    anotacion: str | None = None
    acompanantes: list[str] = field(default_factory=list)

    # operación
    estado: str | None = None
    resultado: str | None = None
    resultado_nota: str | None = None
    pais_cita: str | None = None
    citas: list[tuple[str, dt.datetime]] = field(default_factory=list)
    pasaporte: str | None = None
    ds160: str | None = None
    id_externo: str | None = None

    # dinero
    servicio: str | None = None
    cantidad: float | None = None
    valor_cobrado: float | None = None
    fecha_venta: dt.datetime | None = None
    abonos: list[tuple[dt.datetime | None, float]] = field(default_factory=list)
    canal: str | None = None
    vendedor: str | None = None
    banco: str | None = None
    nota: str | None = None

    problemas: list[str] = field(default_factory=list)

    def aporta_algo(self) -> bool:
        return bool(self.persona)


@dataclass
class Hoja:
    archivo: str
    nombre: str
    trae: Literal['operacion', 'dinero', 'ambos', 'leads', 'saas']
    extraer: Callable[[Fila], Aporte]
    fila_encabezado: int = 1
    por_que: str = ''


# ---------------------------------------------------------------- utilidades

def _persona_de(fila: Fila, columna: str) -> tuple[str | None, str | None, list[str]]:
    """Devuelve (nombre, anotación, acompañantes)."""
    bruto = fila.texto(columna)
    if not es_nombre_de_persona(bruto):
        if bruto:
            fila.problemas.append(f'{columna}: «{bruto[:40]}» no parece el nombre de una persona')
        return None, None, []
    personas = partir_personas(bruto)
    nombre, anotacion = limpiar_anotaciones(personas[0])
    otros = [limpiar_anotaciones(p)[0] for p in personas[1:]]
    return nombre, anotacion, otros


def _cita(fila: Fila, columna: str, tipo: str, destino: list) -> None:
    cuando = fila.fecha(columna)
    if cuando:
        destino.append((tipo, cuando))


def _estado_y_resultado(fila: Fila, a: Aporte, col_estado: str | None, col_resultado: str | None) -> None:
    if col_estado:
        codigo, problema = hom.estado(fila.texto(col_estado))
        a.estado = codigo
        if problema:
            a.problemas.append(f'estado: {problema}')
    if col_resultado:
        bruto = fila.texto(col_resultado)
        codigo, problema = hom.resultado(bruto)
        if problema == 'nota':
            # La columna «Resultado» de algunas hojas mezcla el resultado
            # consular con notas del embudo. Lo que no es resultado va a la
            # cronología, no al trámite (RN-06).
            a.resultado_nota = bruto
        elif problema:
            a.problemas.append(f'resultado: {problema}')
        else:
            a.resultado = codigo


# ------------------------------------------------------- lectores de operación

def _op_2026(fila: Fila) -> Aporte:
    a = Aporte()
    a.persona, a.anotacion, a.acompanantes = _persona_de(fila, 'Cliente')
    a.telefono = fila.texto('CELULAR')
    # «Estado real» es la columna que la operación mantiene al día; «Estado del
    # Trámite» arrastra el valor con el que se creó la fila. Manda la primera y
    # la segunda queda de respaldo.
    _estado_y_resultado(fila, a, 'Estado real', 'Resultado')
    if a.estado is None:
        _estado_y_resultado(fila, a, 'Estado del Trámite', None)
    a.pais_cita = fila.texto('País de la Cita')
    _cita(fila, 'Fecha CAS', 'cas', a.citas)
    _cita(fila, 'Fecha Entrevista', 'entrevista', a.citas)
    a.servicio, _ = hom.servicio(fila.texto('Tipo'))
    return a


def _op_general(fila: Fila) -> Aporte:
    a = Aporte()
    a.persona, a.anotacion, a.acompanantes = _persona_de(fila, 'Cliente')
    a.telefono = fila.texto('Celular')
    _estado_y_resultado(fila, a, 'Estado del Trámite', None)
    a.pais_cita = fila.texto('País de la Cita')
    _cita(fila, 'Fecha CAS', 'cas', a.citas)
    _cita(fila, 'Fecha Entrevista', 'entrevista', a.citas)
    nota = fila.texto('Notas')
    if nota:
        codigo, problema = hom.resultado(nota)
        if codigo:
            a.resultado = codigo
        else:
            a.nota = nota
    return a


def _op_clientes_general(fila: Fila) -> Aporte:
    a = Aporte()
    a.persona, a.anotacion, a.acompanantes = _persona_de(fila, 'NOMBRE CLIENTE')
    a.telefono = fila.texto('CONTACTO')
    # Solo «CORREO DEL CLIENTE». «CORREO ELECTRONICO» está en la misma fila que
    # la contraseña del portal consular: es la otra mitad de una credencial y
    # D-09 lo deja fuera, no solo la contraseña.
    a.correo = fila.texto('CORREO DEL CLIENTE')
    _estado_y_resultado(fila, a, 'PROCESO', 'RESULTADO')
    a.servicio, _ = hom.servicio(fila.texto('TRAMITE'))
    _cita(fila, 'FECHA CAS', 'cas', a.citas)
    _cita(fila, 'FECHA CONSULAR', 'entrevista', a.citas)
    a.nota = fila.texto('NOTAS') or fila.texto('NOTAS 2')
    return a


def _op_adelantos(fila: Fila) -> Aporte:
    a = Aporte()
    a.persona, a.anotacion, a.acompanantes = _persona_de(fila, 'CLIENTE')
    _estado_y_resultado(fila, a, None, 'RESULTADO')
    _cita(fila, 'CAS', 'cas', a.citas)
    _cita(fila, 'CITA CONSULAR', 'entrevista', a.citas)
    a.nota = fila.texto('NOTA')
    a.servicio = 'adelantos'
    return a


def _op_tramite(fila: Fila) -> Aporte:
    a = Aporte()
    a.persona, a.anotacion, a.acompanantes = _persona_de(fila, 'NOMBRE')
    a.servicio, _ = hom.servicio(fila.texto('TRAMITE'))
    _cita(fila, 'FECHA CAS', 'cas', a.citas)
    _cita(fila, 'FECHA CONSULAR', 'entrevista', a.citas)
    a.nota = fila.texto('NOTA')
    return a


def _op_ds160(fila: Fila) -> Aporte:
    a = Aporte()
    a.persona, a.anotacion, a.acompanantes = _persona_de(fila, '-')
    a.ds160 = fila.texto('DS-160')
    a.pasaporte = fila.texto('PASAPORTE')
    return a


def _saas(fila: Fila) -> Aporte:
    a = Aporte()
    a.persona, a.anotacion, a.acompanantes = _persona_de(fila, 'Solicitante')
    a.pasaporte = fila.texto('Pasaporte')
    # El número de solicitud es la llave externa con la que el sistema va a
    # reconocer este trámite cuando llegue la importación del SaaS (RF-032).
    a.id_externo = fila.texto('N° Solicitud') or fila.texto('N. Solicitud')
    codigo, problema = hom.estado(fila.texto('Etapa actual'))
    a.estado = codigo
    if problema:
        a.problemas.append(f'etapa del SaaS: {problema}')
    return a


# ---------------------------------------------------------- lectores de dinero

def _abonos(fila: Fila, pares: list[tuple[str | None, str]]) -> list[tuple[dt.datetime | None, float]]:
    salida = []
    for col_fecha, col_monto in pares:
        monto = fila.numero(col_monto)
        if monto is None or monto <= 0:
            continue
        salida.append((fila.fecha(col_fecha) if col_fecha else None, monto))
    return salida


def _venta(fila: Fila, *, col_cliente: str, col_servicio: str, col_valor: str,
           col_fecha: str, pares_abono: list[tuple[str | None, str]],
           col_cantidad: str | None = None, col_canal: str | None = None,
           col_vendedor: str | None = None, col_banco: str | None = None,
           col_nota: str | None = None) -> Aporte:
    a = Aporte()
    a.persona, a.anotacion, a.acompanantes = _persona_de(fila, col_cliente)
    bruto_servicio = fila.texto(col_servicio)
    a.servicio, problema = hom.servicio(bruto_servicio)
    if problema:
        a.problemas.append(f'servicio: {problema}')
    a.valor_cobrado = fila.numero(col_valor)
    a.fecha_venta = fila.fecha(col_fecha)
    a.abonos = _abonos(fila, pares_abono)
    if col_cantidad:
        a.cantidad = fila.numero(col_cantidad)
    if col_canal:
        a.canal, _ = hom.canal(fila.texto(col_canal))
    if col_vendedor:
        a.vendedor, _ = hom.vendedor(fila.texto(col_vendedor))
    if col_banco:
        a.banco = fila.texto(col_banco)
    if col_nota:
        a.nota = fila.texto(col_nota)

    # Guarda dura: hay filas con el monto escrito en miles («1250» por
    # 1.250.000). Multiplicar por mil automáticamente sería inventar plata, así
    # que la fila se marca y la revisa una persona.
    if a.valor_cobrado is not None and 0 < a.valor_cobrado < 10_000:
        a.problemas.append(f'el valor cobrado ({a.valor_cobrado:,.0f}) parece estar escrito en '
                           f'miles; no se convierte automáticamente')
    return a


def _pagos(fila: Fila) -> Aporte:
    return _venta(fila, col_cliente='CLIENTE', col_servicio='SERVICIO', col_valor='VALOR COBRADO',
                  col_fecha='F.PAGO', col_cantidad='CANTIDAD',
                  pares_abono=[('F.PAGO', 'Abono 1'), ('F.PAGO 2', 'Abono2'), ('F.PAGO 3', 'Abono 3')],
                  col_canal='MEDIO', col_vendedor='VENDEDOR', col_banco='BANCO')


def _pagos2026(fila: Fila) -> Aporte:
    return _venta(fila, col_cliente='CLIENTE', col_servicio='SERVICIO', col_valor='VALOR COBRADO',
                  col_fecha='F. VENTA',
                  pares_abono=[('F.PAGO', 'Abono 1')], col_nota='NOTAS')


def _ventas_angie(fila: Fila) -> Aporte:
    a = _venta(fila, col_cliente='Nombre del cliente', col_servicio='Servicio',
               col_valor='VALOR COBRADO', col_fecha='Fecha de venta', col_cantidad='CANTIDAD',
               pares_abono=[], col_canal='MEDIO', col_vendedor='Nombre del vendedor')
    # La hoja registra la venta pero no el cobro: no trae ni una columna de
    # abono. Cargarla sin más pone toda su facturación en la cartera como deuda.
    a.problemas.append('la hoja no registra abonos: la venta entraría con saldo completo')
    return a


def _pagos_recibidos(fila: Fila) -> Aporte:
    """Un pago suelto: trae lo cobrado y la fecha, pero no el valor pactado.

    No se inventa el precio. La venta entra con valor pactado cero, que en el
    estado financiero sale como «sin acuerdo» y aparece en el reporte para que
    VisaNow diga cuánto se había pactado.
    """
    a = Aporte()
    a.persona, a.anotacion, a.acompanantes = _persona_de(fila, 'CLIENTE')
    a.telefono = fila.texto('CELULAR')
    a.servicio, problema = hom.servicio(fila.texto('PROCESO'))
    if problema:
        a.problemas.append(f'servicio: {problema}')
    monto = fila.numero('PAGO')
    cuando = fila.fecha('FECHA DE PAGO')
    a.fecha_venta = cuando
    if monto and monto > 0:
        a.abonos = [(cuando, monto)]
        # El valor pactado se asume igual a lo cobrado. No es un dato, es un
        # supuesto, y por eso queda anotado: dejarlo en cero produciría un saldo
        # a favor del cliente que nadie le debe, y la cartera del sistema saldría
        # negativa. Asumir «pagó lo que se le cobró» no inventa deuda ni crédito,
        # y si alguna de estas ventas sí tenía saldo, sale en el reporte.
        a.valor_cobrado = monto
        a.problemas.append('la hoja registra el pago pero no el valor pactado: se asume que el '
                           'servicio se pagó completo')
    a.nota = fila.texto('NOTAS')
    return a


# --------------------------------------------------------------- el catálogo

CATALOGO: list[Hoja] = [
    # --- operación
    Hoja('VISANOW CLIENTES.xlsx', '2026', 'operacion', _op_2026,
         por_que='Los trámites del año en curso. Es la hoja viva de la operación.'),
    Hoja('VISANOW CLIENTES.xlsx', 'GENERAL', 'operacion', _op_general,
         por_que='El histórico de trámites anteriores.'),
    Hoja('VISANOW CLIENTES.xlsx', 'DS-160', 'operacion', _op_ds160,
         por_que='Números de DS-160 y pasaportes. Se cifran al cargar.'),
    # Es de operación, no de dinero: nombra el trámite contratado pero no trae
    # ni valor ni abonos, así que no produce ventas.
    Hoja('CUENTAS VISANOW.xlsx', 'CLIENTES GENERAL ', 'operacion', _op_clientes_general,
         por_que='Trámites y citas que no están en el otro libro. La columna de '
                 'contraseña y su correo pareado no se leen (D-09).'),
    Hoja('CUENTAS VISANOW.xlsx', 'ADELANTOS', 'operacion', _op_adelantos,
         por_que='Adelantos de cita con sus fechas. La columna de contraseña no se lee (D-09).'),
    Hoja('CUENTAS VISANOW.xlsx', 'TRAMITE', 'operacion', _op_tramite,
         por_que='Pocas filas, pero traen citas que no están en ninguna otra hoja.'),
    Hoja('solicitantes_20260901_20260930.xlsx', 'Solicitudes', 'saas', _saas,
         por_que='El export del SaaS. Es la única fuente con número de solicitud, '
                 'que es la llave de la sincronización de la actividad 5.1.'),

    # --- dinero
    Hoja('CUENTAS VISANOW.xlsx', 'PAGOS', 'dinero', _pagos,
         por_que='El libro de ventas principal, con hasta tres abonos por venta.'),
    Hoja('CUENTAS VISANOW.xlsx', 'PAGOS2026', 'dinero', _pagos2026,
         por_que='Las ventas del año con su fecha de venta separada de la de pago.'),
    Hoja('CUENTAS VISANOW.xlsx', 'VENTAS ANGIE', 'dinero', _ventas_angie,
         por_que='Ventas registradas desde un formulario. No trae cobros: entra marcada.'),
    Hoja('CUENTAS VISANOW.xlsx', 'PAGOS RECIBIDOS', 'dinero', _pagos_recibidos,
         por_que='Pagos sueltos de clientes que en su mayoría no están en PAGOS.'),
]

# Lo que se deja fuera, dicho a propósito
EXCLUIDAS = {
    ('CUENTAS VISANOW.xlsx', 'REV PAGOS'):
        'Es la misma venta que PAGOS en casi todas sus filas, cortada en junio mientras PAGOS '
        'llega a septiembre. Migrarla duplicaría las ventas e inflaría la cartera con deuda que '
        'PAGOS ya registra como pagada.',
    ('CUENTAS VISANOW.xlsx', 'EXTRACTO'):
        'Extracto bancario: los mismos ingresos que ya están en PAGOS, más movimientos que no son '
        'de clientes. Sirve para cuadrar la caja, no para cargar pagos.',
    ('CUENTAS VISANOW.xlsx', 'PRECIOS'):
        'La lista de precios ya está sembrada en el catálogo de servicios y tarifas.',
    ('CUENTAS VISANOW.xlsx', ' PRECIOS'):
        'Copia de la lista de precios (con un espacio al inicio en el nombre de la hoja).',
    ('CUENTAS VISANOW.xlsx', 'EXPENSES'):
        'Suscripciones de software en otra moneda y sin fecha. Son gastos de la empresa, no del '
        'negocio de visas, y el MVP 1 no los necesita.',
    ('CUENTAS VISANOW.xlsx', 'GASTOS'):
        'Casi ninguna fila tiene fecha, que es obligatoria. Va al reporte de excepciones.',
    ('CUENTAS VISANOW.xlsx', 'GASTOS 2026'):
        'Gastos y comisiones pagadas. Se carga en la fase 4, cuando exista el módulo de costos.',
    ('CUENTAS VISANOW.xlsx', 'MIRIAM'):
        'El libro de la mensajera: son cuentas por pagar, no clientes. Va con los gastos.',
    ('VISANOW CLIENTES.xlsx', 'pauta'):
        'Leads de publicidad. Entran en la fase 3, cuando exista el embudo comercial.',
    ('VISANOW CLIENTES.xlsx', 'OPERACION YAZ'):
        'Mezcla un tablero de conteos con filas de cliente. Las filas se revisan aparte porque el '
        'encabezado está en la segunda fila y el bloque de conteos no se migra.',
    ('VISANOW CLIENTES.xlsx', 'Mensajes'):
        'Plantillas de mensajes. No hay tabla de plantillas en el MVP 1.',
    ('VISANOW CLIENTES.xlsx', '_Listas'):
        'Las listas de validación del libro. Son la autoridad de los catálogos, no datos.',
    ('VISANOW CLIENTES.xlsx', 'Instrucciones'):
        'Documenta cómo está construido el libro. Se leyó para armar el mapeo.',
    ('VISANOW CLIENTES.xlsx', 'BDGENERAL'):
        'Una sola celda, con un error de Excel.',
    ('VISANOW CLIENTES.xlsx', 'Hoja 13'):
        'Vacía.',
    ('VISANOW CLIENTES.xlsx', 'Respuestas de formulario 1'):
        'Tres filas de personas que no aparecen en ninguna otra hoja. Van al reporte.',
}


def recorrer(hoja: Hoja):
    """Las filas de una hoja, ya convertidas en aportes."""
    ruta = FUENTE / hoja.archivo
    for fila in leer_hoja(ruta, hoja.nombre, fila_encabezado=hoja.fila_encabezado):
        for prohibida in COLUMNAS_PROHIBIDAS:
            fila.celdas.pop(prohibida, None)
        aporte = hoja.extraer(fila)
        aporte.problemas.extend(fila.problemas)
        yield fila, aporte
