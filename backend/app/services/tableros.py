"""Los cuatro tableros (RF-070 a RF-075): comercial, operativo, financiero y ejecutivo.

Todo lo que hay aquí **lee**. Los saldos salen de `v_estado_financiero` y
`v_cartera`: si un tablero rehiciera la cuenta, el número del tablero y el de la
pantalla de cartera dirían cosas distintas, y con eso se pierde la confianza en
ambos.

Las fechas del filtro son días de Bogotá. El servidor corre en UTC, así que una
columna `timestamptz` se pasa a America/Bogota antes de compararla con el día:
sin eso, algo registrado a las 8 p. m. del 31 cae en el mes siguiente.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field

from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errores import Invalido, Prohibido
from app.models.esquema import Usuarios
from app.services.usuarios import permisos_de_rol

TABLEROS = ('comercial', 'operativo', 'financiero', 'ejecutivo')
# Los que suman plata de la agencia: vendido, recaudado, cartera, vencido.
CON_PLATA = ('financiero', 'ejecutivo')
# Un día de Bogotá a partir de un instante guardado con zona
_DIA = "(({col}) at time zone 'America/Bogota')::date"


@dataclass
class Filtros:
    desde: dt.date | None = None
    hasta: dt.date | None = None
    vendedor_id: int | None = None
    servicio_id: int | None = None
    estado: str | None = None


@dataclass
class Indicador:
    clave: str
    nombre: str
    valor: float
    formato: str = 'numero'          # numero | pesos | porcentaje


@dataclass
class Tabla:
    clave: str
    titulo: str
    columnas: list[str]
    filas: list[list] = field(default_factory=list)


@dataclass
class Tablero:
    tablero: str
    titulo: str
    indicadores: list[Indicador]
    tablas: list[Tabla]


def _rango(col: str, f: Filtros, p: dict, prefijo: str) -> list[str]:
    dia = _DIA.format(col=col)
    out = []
    if f.desde:
        out.append(f'{dia} >= :{prefijo}_d')
        p[f'{prefijo}_d'] = f.desde
    if f.hasta:
        out.append(f'{dia} <= :{prefijo}_h')
        p[f'{prefijo}_h'] = f.hasta
    return out


def _donde(cond: list[str]) -> str:
    return ('where ' + ' and '.join(cond)) if cond else ''


def _filas(db: Session, sql: str, p: dict) -> list[list]:
    return [list(r) for r in db.execute(text(sql), p).all()]


def _num(v) -> float:
    return float(v or 0)


def _restringir(actor: Usuarios, f: Filtros, tablero: str) -> Filtros:
    """El alcance del usuario es un control de acceso, no un filtro (RNF-03).

    Quien solo ve lo suyo no puede abrir los tableros que suman toda la agencia,
    y en los demás se le fuerza su propio filtro de vendedor.
    """
    if actor.alcance == 'todos':
        return f
    if tablero in ('financiero', 'ejecutivo'):
        raise Prohibido('Este tablero suma toda la agencia y su alcance no lo incluye.',
                        codigo='sin_alcance')
    f.vendedor_id = actor.id
    return f


# ----------------------------------------------------------------- comercial

def _comercial(db: Session, f: Filtros) -> Tablero:
    p: dict = {}
    c = _rango('o.creado_en', f, p, 'o')
    if f.vendedor_id:
        c.append('o.asesor_id = :v')
        p['v'] = f.vendedor_id
    if f.servicio_id:
        c.append('o.servicio_id = :s')
        p['s'] = f.servicio_id
    if f.estado:
        c.append('e.codigo = :e')
        p['e'] = f.estado
    base = f"""from oportunidades o join estados_comerciales e on e.id = o.estado_id
               {_donde(c)}"""
    leads, ganados, perdidos = db.execute(text(f"""
        select count(*), count(*) filter (where e.codigo = 'ganado'),
               count(*) filter (where e.codigo = 'perdido') {base}"""), p).first()
    # Conversión sobre lo ya decidido: dividir por los leads abiertos castiga al
    # equipo por los que todavía no tuvieron tiempo de cerrarse.
    cerrados = ganados + perdidos
    conversion = (ganados / cerrados * 100) if cerrados else 0
    por_canal = _filas(db, f"""
        select coalesce(ca.nombre, 'Sin canal'), count(*),
               count(*) filter (where e.codigo = 'ganado'),
               round(100.0 * count(*) filter (where e.codigo = 'ganado')
                     / nullif(count(*) filter (where e.codigo in ('ganado','perdido')), 0), 1)
        from oportunidades o join estados_comerciales e on e.id = o.estado_id
        left join canales ca on ca.id = o.canal_id {_donde(c)} group by 1 order by 2 desc""", p)
    por_vendedor = _filas(db, f"""
        select coalesce(u.nombre, 'Sin asesor'), count(*),
               count(*) filter (where e.codigo = 'ganado'),
               round(100.0 * count(*) filter (where e.codigo = 'ganado')
                     / nullif(count(*) filter (where e.codigo in ('ganado','perdido')), 0), 1)
        from oportunidades o join estados_comerciales e on e.id = o.estado_id
        left join usuarios u on u.id = o.asesor_id {_donde(c)} group by 1 order by 2 desc""", p)
    por_estado = _filas(db, f"""
        select e.nombre, count(*), coalesce(sum(o.valor_estimado), 0) {base}
        group by e.nombre, e.orden order by e.orden""", p)
    return Tablero('comercial', 'Tablero comercial', [
        Indicador('leads', 'Leads', leads),
        Indicador('ganados', 'Ganados', ganados),
        Indicador('perdidos', 'Perdidos', perdidos),
        Indicador('conversion', 'Conversión sobre cerrados', round(conversion, 1), 'porcentaje'),
    ], [
        Tabla('canal', 'Por canal', ['Canal', 'Leads', 'Ganados', 'Conversión %'], por_canal),
        Tabla('vendedor', 'Por vendedor', ['Vendedor', 'Leads', 'Ganados', 'Conversión %'],
              por_vendedor),
        Tabla('estado', 'Por estado', ['Estado', 'Leads', 'Valor estimado'], por_estado),
    ])


# ------------------------------------------------------------------ operativo

def _operativo(db: Session, f: Filtros) -> Tablero:
    p: dict = {}
    c = _rango('ca.creado_en', f, p, 'c')
    if f.vendedor_id:
        # En operación «vendedor» es la persona responsable del trámite
        c.append('ca.responsable_id = :v')
        p['v'] = f.vendedor_id
    if f.servicio_id:
        c.append('n.servicio_id = :s')
        p['s'] = f.servicio_id
    if f.estado:
        c.append('e.codigo = :e')
        p['e'] = f.estado
    union = """from casos ca join estados_operativos e on e.id = ca.estado_id
               join negocios n on n.id = ca.negocio_id"""
    abiertos = ['e.es_final = false'] + c
    total, activos, sin_resp = db.execute(text(f"""
        select count(*), count(*) filter (where not e.es_final),
               count(*) filter (where not e.es_final and ca.responsable_id is null)
        {union} {_donde(c)}"""), p).first()
    # «En riesgo»: abierto y sin actividad hace más de 15 días. El umbral sale de
    # la operación: pasada una quincena sin moverse, la cita o el pago ya se enfriaron.
    riesgo = db.scalar(text(f"""
        select count(*) {union}
         {_donde(abiertos + ["ca.ultima_actividad_en < now() - interval '15 days'"])}"""), p)
    por_estado = _filas(db, f"""
        select e.nombre, count(*),
               coalesce(round(avg(extract(epoch from now() - ca.ultima_actividad_en) / 86400)), 0)
        {union} {_donde(c)} group by e.nombre, e.orden order by e.orden""", p)
    por_resp = _filas(db, f"""
        select coalesce(u.nombre, 'Sin responsable'), count(*)
        {union} left join usuarios u on u.id = ca.responsable_id
        {_donde(abiertos)} group by 1 order by 2 desc""", p)
    antiguos = _filas(db, f"""
        select ca.id, s.nombre, e.nombre,
               extract(day from now() - ca.ultima_actividad_en)::int
        {union} join solicitantes s on s.id = ca.solicitante_id
        {_donde(abiertos)} order by ca.ultima_actividad_en limit 20""", p)
    return Tablero('operativo', 'Tablero operativo', [
        Indicador('tramites', 'Trámites', total),
        Indicador('activos', 'Activos', activos),
        Indicador('riesgo', 'En riesgo (sin movimiento > 15 días)', riesgo),
        Indicador('sin_responsable', 'Sin responsable', sin_resp),
    ], [
        Tabla('estado', 'Por estado', ['Estado', 'Trámites', 'Días promedio sin actividad'],
              por_estado),
        Tabla('responsable', 'Carga por responsable (abiertos)', ['Responsable', 'Trámites'],
              por_resp),
        Tabla('antiguos', 'Los 20 más quietos', ['Trámite', 'Solicitante', 'Estado',
                                                  'Días sin actividad'], antiguos),
    ])


# ----------------------------------------------------------------- financiero

def _financiero(db: Session, f: Filtros) -> Tablero:
    # Vendido, recaudado y cartera van por separado: son tres preguntas distintas
    # y mezclarlas es lo que hoy hace que los libros no cuadren.
    pv: dict = {}
    cv: list[str] = []
    if f.desde:
        cv.append('n.fecha_venta >= :vd')
        pv['vd'] = f.desde
    if f.hasta:
        cv.append('n.fecha_venta <= :vh')
        pv['vh'] = f.hasta
    if f.vendedor_id:
        cv.append('n.vendedor_id = :v')
        pv['v'] = f.vendedor_id
    if f.servicio_id:
        cv.append('n.servicio_id = :s')
        pv['s'] = f.servicio_id
    if f.estado:
        cv.append('ef.estado_financiero = :e')
        pv['e'] = f.estado
    venta = f"""from negocios n join v_cartera c on c.negocio_id = n.id
                join v_estado_financiero ef on ef.negocio_id = n.id
                join servicios s on s.id = n.servicio_id {_donde(cv)}"""
    vendido, cobrado, cartera, vencido = db.execute(text(f"""
        select coalesce(sum(c.valor_pactado), 0), coalesce(sum(c.total_pagado), 0),
               coalesce(sum(c.saldo), 0), coalesce(sum(c.vencido), 0) {venta}"""), pv).first()
    # Recaudo del periodo por fecha del pago, no de la venta: es plata que entró
    # en esos días aunque la venta sea anterior.
    pp: dict = {}
    cp = ["pa.estado = 'confirmado'"]
    if f.desde:
        cp.append('pa.fecha >= :pd')
        pp['pd'] = f.desde
    if f.hasta:
        cp.append('pa.fecha <= :ph')
        pp['ph'] = f.hasta
    if f.vendedor_id:
        cp.append('n.vendedor_id = :v')
        pp['v'] = f.vendedor_id
    if f.servicio_id:
        cp.append('n.servicio_id = :s')
        pp['s'] = f.servicio_id
    recaudado = db.scalar(text(f"""
        select coalesce(sum(pa.monto_bruto), 0) from pagos pa
        join negocios n on n.id = pa.negocio_id {_donde(cp)}"""), pp)
    por_servicio = _filas(db, f"""
        select s.nombre, count(*), coalesce(sum(c.valor_pactado), 0),
               coalesce(sum(c.total_pagado), 0), coalesce(sum(c.saldo), 0)
        {venta}
        group by s.nombre order by 3 desc""", pv)
    por_estado = _filas(db, f"""
        select ef.estado_financiero, count(*), coalesce(sum(c.saldo), 0) {venta}
        group by 1 order by 2 desc""", pv)
    sin_asignar = db.execute(text("""
        select count(*), coalesce(sum(monto_bruto), 0) from pagos
         where negocio_id is null and estado in ('no_identificado', 'pendiente')""")).first()
    return Tablero('financiero', 'Tablero financiero', [
        Indicador('vendido', 'Vendido', _num(vendido), 'pesos'),
        Indicador('recaudado', 'Recaudado en el periodo', _num(recaudado), 'pesos'),
        Indicador('cartera', 'Cartera (saldo)', _num(cartera), 'pesos'),
        Indicador('vencido', 'Vencido', _num(vencido), 'pesos'),
        Indicador('sin_identificar', 'Pagos sin identificar', _num(sin_asignar[1]), 'pesos'),
    ], [
        Tabla('servicio', 'Por servicio', ['Servicio', 'Ventas', 'Vendido', 'Cobrado', 'Saldo'],
              por_servicio),
        Tabla('estado', 'Por estado financiero', ['Estado', 'Ventas', 'Saldo'], por_estado),
    ])


# ------------------------------------------------------------------ ejecutivo

def _ejecutivo(db: Session, f: Filtros) -> Tablero:
    """Un número de cada frente; el detalle está en los otros tres."""
    com, ope, fin = _comercial(db, f), _operativo(db, f), _financiero(db, f)
    ind = ([i for i in com.indicadores if i.clave in ('leads', 'conversion')]
           + [i for i in ope.indicadores if i.clave in ('activos', 'riesgo')]
           + [i for i in fin.indicadores if i.clave in ('vendido', 'recaudado', 'cartera', 'vencido')])
    return Tablero('ejecutivo', 'Tablero ejecutivo', ind,
                   [com.tablas[1], fin.tablas[0]])


_CONSTRUCTORES = {'comercial': _comercial, 'operativo': _operativo,
                  'financiero': _financiero, 'ejecutivo': _ejecutivo}


def construir(db: Session, actor: Usuarios, tablero: str, f: Filtros) -> Tablero:
    if tablero not in _CONSTRUCTORES:
        raise Invalido(f'Tablero desconocido. Opciones: {", ".join(TABLEROS)}.')
    if f.desde and f.hasta and f.desde > f.hasta:
        raise Invalido('La fecha inicial es posterior a la final.')
    # El alcance no alcanza para decidir esto. Operaciones se crea con alcance
    # «todos» —tiene que ver todos los trámites— y con eso entraba al tablero
    # financiero, que es exactamente la contabilidad que la administradora dijo
    # que ese rol no ve (respuesta del 29/09). Ver plata es un permiso, no un
    # alcance, y el permiso es `pagos.ver`.
    if tablero in CON_PLATA and 'pagos.ver' not in permisos_de_rol(db, actor.rol_id):
        raise Prohibido('Este tablero suma la plata de la agencia y su rol no ve montos.',
                        codigo='sin_permiso')
    return _CONSTRUCTORES[tablero](db, _restringir(actor, f, tablero))


# ----------------------------------------------------------------- exportación

def a_csv(t: Tablero) -> bytes:
    """Todo en un solo CSV: indicadores y luego cada tabla, separadas por una línea en blanco.

    Con BOM para que Excel en español abra bien las tildes.
    """
    sal = io.StringIO()
    w = csv.writer(sal, delimiter=';')
    w.writerow([t.titulo])
    for i in t.indicadores:
        w.writerow([i.nombre, i.valor])
    for tabla in t.tablas:
        w.writerow([])
        w.writerow([tabla.titulo])
        w.writerow(tabla.columnas)
        w.writerows(tabla.filas)
    return ('﻿' + sal.getvalue()).encode('utf-8')


def a_xlsx(t: Tablero) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Indicadores'
    hoja.append([t.titulo])
    for i in t.indicadores:
        hoja.append([i.nombre, i.valor])
    for tabla in t.tablas:
        h = libro.create_sheet(tabla.titulo[:31])
        h.append(tabla.columnas)
        for fila in tabla.filas:
            h.append([float(v) if hasattr(v, 'quantize') else v for v in fila])
    sal = io.BytesIO()
    libro.save(sal)
    return sal.getvalue()
