"""Rentabilidad: que quedo de verdad de cada venta (RF-054).

La resta completa, en el orden en que se explica:

    recaudado
  - lo que se llevo la pasarela o el banco  ->  INGRESO NETO
  - la comision de la vendedora
  - los gastos cargados a esa venta
  - lo que cuesta atender el servicio
  =============================================
    MARGEN

Cada pieza ya existia por separado y nadie las restaba: el tablero financiero
suma `monto_bruto` y lo llama recaudado, las comisiones se listan y se liquidan,
y los gastos directos se registran. Vendido no es ganado, y esa es justamente la
diferencia que esta pantalla muestra.

**Por que la venta es la unidad y no el mes.** Una venta y todo lo que costo van
juntas: la comision es de esa venta, la mensajeria es de ese tramite, el
tramitador se paga por ese servicio. Si el margen de octubre se armara con la
plata que entro en octubre y los gastos pagados en octubre, el resultado del mes
dependeria de cuando al cliente se le dio por pagar y de cuando el proveedor
paso la cuenta. Por eso todo se le atribuye a la venta, y la venta pertenece al
mes en que se vendio (`fecha_venta`). «Por periodo» agrupa esas ventas; «por
servicio» agrupa las mismas ventas de otra forma. Son la misma resta mirada
desde tres lados, y por eso los tres cuadran entre si.

**La tasa consular no es ingreso.** El servicio de tipo `recaudo_terceros` es
plata que se le cobra al cliente y se le entrega al consulado: nunca fue de la
agencia. Contarla como ingreso infla el margen justo en lo que no se gano, asi
que entra en su propia columna (`recaudo_terceros`) y en el margen vale cero.
Es el mismo criterio con el que `comisiones.py` la saca de la base de calculo.

**El ingreso es lo que entro, no lo que se facturo.** Se lee
`v_estado_financiero.neto_recibido`, que es la suma de los pagos confirmados ya
descontado el costo del medio de pago. Una venta recien cerrada y sin pagar
tiene margen negativo si ya genero gastos, y eso es la verdad: todavia no ha
entrado un peso. Para leerlo en contexto, el detalle de la venta tambien muestra
lo pactado y el saldo.

Nada de esto se guarda en ninguna columna: el margen se calcula al preguntar,
igual que el saldo (RN-01). Lo unico que se guarda es lo que cuesta cada
servicio, en `costos_servicio`, que es un dato que alguien escribe.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errores import Invalido, NoEncontrado, Prohibido
from app.models.esquema import Usuarios

# Como se ordena la lista de ventas. «peores» primero es el orden util: la
# pregunta del dueno es cual venta se esta comiendo la plata, no cual va bien.
ORDENES = ('peores', 'mejores', 'recientes')


@dataclass
class Filtros:
    desde: dt.date | None = None
    hasta: dt.date | None = None
    servicio_id: int | None = None
    vendedor_id: int | None = None


@dataclass
class Margen:
    """Una resta completa. Sirve para el total, para un servicio y para un mes."""
    clave: str
    etiqueta: str
    ventas: int
    ingreso_bruto: float
    costo_medio: float
    ingreso_neto: float
    comisiones: float
    gastos_directos: float
    costo_servicio: float
    margen: float
    #: Nulo a proposito cuando no entro plata: un porcentaje sobre cero no
    #: significa nada y mostrarlo como 0 % haria creer que la venta salio en
    #: tablas cuando lo que pasa es que nadie ha pagado.
    margen_pct: float | None
    recaudo_terceros: float


@dataclass
class MargenVenta(Margen):
    """El margen de una venta, con lo que hace falta para ubicarla."""
    negocio_id: int
    fecha_venta: dt.date
    servicio: str
    es_recaudo_de_terceros: bool
    vendedor: str | None
    valor_pactado: float
    saldo: float


@dataclass
class Informe:
    """Lo que responde la pantalla: el total y los dos cortes del requisito."""
    total: Margen
    por_servicio: list[Margen]
    por_periodo: list[Margen]


# --------------------------------------------------------------------- consulta

#: Una sola definicion de la resta, para que el total, el corte por servicio, el
#: corte por mes y el detalle de una venta no puedan decir cosas distintas. Si
#: cada consulta repitiera la resta, bastaria con corregir una y olvidar las
#: otras para que la pantalla se contradijera consigo misma.
_VENTA = """
    select
      n.id                                    as negocio_id,
      n.fecha_venta,
      n.servicio_id,
      n.vendedor_id,
      s.nombre                                as servicio,
      s.tipo = 'recaudo_terceros'             as es_recaudo_de_terceros,
      n.valor_pactado,
      coalesce(ef.saldo, 0)                   as saldo,
      -- La tasa consular se aparta aqui: entra en su columna y no suma ingreso.
      case when s.tipo = 'recaudo_terceros' then 0
           else coalesce(ef.total_pagado, 0) end            as ingreso_bruto,
      -- Lo que se llevo la pasarela es la diferencia entre el bruto y el neto
      -- de la vista; no se vuelve a restar despues, porque ya esta descontado
      -- dentro del ingreso neto.
      case when s.tipo = 'recaudo_terceros' then 0
           else coalesce(ef.total_pagado, 0)
                - coalesce(ef.neto_recibido, 0) end         as costo_medio,
      case when s.tipo = 'recaudo_terceros' then 0
           else coalesce(ef.neto_recibido, 0) end           as ingreso_neto,
      case when s.tipo = 'recaudo_terceros' then coalesce(ef.total_pagado, 0)
           else 0 end                                       as recaudo_terceros,
      coalesce(co.comisiones, 0)              as comisiones,
      coalesce(ga.gastos, 0)                  as gastos_directos,
      coalesce(cs.costo, 0)                   as costo_servicio
    from negocios n
    join servicios s on s.id = n.servicio_id
    join v_estado_financiero ef on ef.negocio_id = n.id
    -- Las anuladas no se descuentan: una comision anulada es plata que no salio.
    left join lateral (
      select sum(c.monto) as comisiones from comisiones c
       where c.negocio_id = n.id and c.estado <> 'anulada') co on true
    -- Gasto directo es el que se le cargo a la venta o a uno de sus tramites;
    -- la publicidad del mes es gasto de la casa y no se le carga a nadie.
    left join lateral (
      select sum(g.monto) as gastos from gastos g
       where g.estado <> 'anulado'
         and (g.negocio_id = n.id
              or g.caso_id in (select ca.id from casos ca where ca.negocio_id = n.id))) ga on true
    -- El costo que regia el dia de la venta, no el de hoy: subirle hoy el
    -- precio al tramitador no puede cambiar el margen del ano pasado.
    left join lateral (
      select sum(case when k.modalidad = 'por_persona'
                      then k.monto * greatest(n.cantidad_solicitantes, 1)
                      else k.monto end) as costo
        from costos_servicio k
       where k.servicio_id = n.servicio_id and k.activo
         and k.vigente_desde <= n.fecha_venta
         and (k.vigente_hasta is null or k.vigente_hasta >= n.fecha_venta)) cs on true
"""

_MARGEN = 'ingreso_neto - comisiones - gastos_directos - costo_servicio'

#: Las sumas, en el mismo orden que los campos de `Margen`.
_SUMAS = f"""
      count(*),
      coalesce(sum(ingreso_bruto), 0), coalesce(sum(costo_medio), 0),
      coalesce(sum(ingreso_neto), 0), coalesce(sum(comisiones), 0),
      coalesce(sum(gastos_directos), 0), coalesce(sum(costo_servicio), 0),
      coalesce(sum({_MARGEN}), 0), coalesce(sum(recaudo_terceros), 0)
"""


def _condiciones(f: Filtros, p: dict) -> str:
    """El periodo se mide por la fecha de la venta.

    `negocios.fecha_venta` es un `date` y no un instante con zona, asi que aqui
    no hay que pasar nada a hora de Bogota como en los tableros: el dia que
    quedo escrito es el dia que vale.
    """
    cond = []
    if f.desde:
        cond.append('n.fecha_venta >= :desde')
        p['desde'] = f.desde
    if f.hasta:
        cond.append('n.fecha_venta <= :hasta')
        p['hasta'] = f.hasta
    if f.servicio_id:
        cond.append('n.servicio_id = :servicio_id')
        p['servicio_id'] = f.servicio_id
    if f.vendedor_id:
        cond.append('n.vendedor_id = :vendedor_id')
        p['vendedor_id'] = f.vendedor_id
    return ('where ' + ' and '.join(cond)) if cond else ''


def _num(v) -> float:
    return float(v or 0)


def _porcentaje(margen: float, ingreso_neto: float) -> float | None:
    if not ingreso_neto:
        return None
    return round(margen / ingreso_neto * 100, 1)


def _margen(clave: str, etiqueta: str, fila) -> Margen:
    ventas, bruto, medio, neto, comis, gastos, costo, margen, terceros = fila
    return Margen(clave=clave, etiqueta=etiqueta, ventas=int(ventas or 0),
                  ingreso_bruto=_num(bruto), costo_medio=_num(medio), ingreso_neto=_num(neto),
                  comisiones=_num(comis), gastos_directos=_num(gastos),
                  costo_servicio=_num(costo), margen=_num(margen),
                  margen_pct=_porcentaje(_num(margen), _num(neto)),
                  recaudo_terceros=_num(terceros))


# ----------------------------------------------------------------- el candado

def _exigir_alcance_total(actor: Usuarios) -> None:
    """Quien solo ve lo suyo no suma la agencia entera (RNF-03).

    Es el mismo candado del tablero financiero y vive aqui, en el servicio, no
    en la ruta: el filtro de la pantalla es una comodidad y se puede no enviar,
    esto es control de acceso y no se puede apagar desde la API.
    """
    if actor.alcance != 'todos':
        raise Prohibido('Esta cifra suma toda la agencia y su alcance no lo incluye.',
                        codigo='sin_alcance')


def _validar(f: Filtros) -> Filtros:
    if f.desde and f.hasta and f.desde > f.hasta:
        raise Invalido('La fecha inicial es posterior a la final.')
    return f


# ------------------------------------------------------------------- consultas

def informe(db: Session, actor: Usuarios, f: Filtros) -> Informe:
    """El total del periodo y los mismos numeros cortados por servicio y por mes."""
    _exigir_alcance_total(actor)
    _validar(f)
    p: dict = {}
    base = f'with venta as ({_VENTA} {_condiciones(f, p)})'

    total = db.execute(text(f'{base} select {_SUMAS} from venta'), p).first()

    por_servicio = [
        _margen(str(servicio_id), nombre, fila)
        for servicio_id, nombre, *fila in db.execute(text(f"""
            {base} select servicio_id, servicio, {_SUMAS} from venta
             group by servicio_id, servicio order by 1, 2"""), p)]
    # Ordenado por el margen de menos a mas: arriba queda el servicio que esta
    # dando perdida, que es lo que hay que ver primero.
    por_servicio.sort(key=lambda m: m.margen)

    por_periodo = [
        _margen(mes.isoformat(), mes.strftime('%Y-%m'), fila)
        for mes, *fila in db.execute(text(f"""
            {base}
            select date_trunc('month', fecha_venta)::date as mes, {_SUMAS} from venta
             group by mes order by mes"""), p)]

    return Informe(total=_margen('total', 'Total del periodo', total),
                   por_servicio=por_servicio, por_periodo=por_periodo)


def _venta(fila) -> MargenVenta:
    base = _margen(str(fila.negocio_id), f'Venta {fila.negocio_id}',
                   (1, fila.ingreso_bruto, fila.costo_medio, fila.ingreso_neto,
                    fila.comisiones, fila.gastos_directos, fila.costo_servicio,
                    fila.margen, fila.recaudo_terceros))
    return MargenVenta(**base.__dict__, negocio_id=fila.negocio_id,
                       fecha_venta=fila.fecha_venta, servicio=fila.servicio,
                       es_recaudo_de_terceros=bool(fila.es_recaudo_de_terceros),
                       vendedor=fila.vendedor, valor_pactado=_num(fila.valor_pactado),
                       saldo=_num(fila.saldo))


def por_negocio(db: Session, actor: Usuarios, f: Filtros, *, orden: str = 'peores',
                pagina: int = 1, tamano: int = 50) -> tuple[int, list[MargenVenta]]:
    """Una fila por venta: «por negocio» del requisito."""
    _exigir_alcance_total(actor)
    _validar(f)
    if orden not in ORDENES:
        raise Invalido(f'Orden desconocido. Opciones: {", ".join(ORDENES)}.')
    p: dict = {}
    base = f'with venta as ({_VENTA} {_condiciones(f, p)})'
    total = db.scalar(text(f'{base} select count(*) from venta'), p) or 0

    # El id desempata para que dos ventas con el mismo margen no se barajen
    # entre paginas y una desaparezca del listado.
    como = {'peores': 'margen asc, negocio_id',
            'mejores': 'margen desc, negocio_id',
            'recientes': 'fecha_venta desc, negocio_id desc'}[orden]
    p['limite'], p['salto'] = tamano, (pagina - 1) * tamano
    filas = db.execute(text(f"""
        {base}
        select v.*, {_MARGEN} as margen, u.nombre as vendedor
          from venta v left join usuarios u on u.id = v.vendedor_id
         order by {como} limit :limite offset :salto"""), p).all()
    return int(total), [_venta(x) for x in filas]


def de_la_venta(db: Session, actor: Usuarios, negocio_id: int) -> MargenVenta:
    """El margen de una venta, pieza por pieza (RF-054, «por negocio»).

    El alcance se revisa sobre la venta y no sobre el filtro: quien solo ve lo
    suyo puede mirar el margen de lo que vendio, y nada mas.
    """
    fila = db.execute(text(f"""
        with venta as ({_VENTA} where n.id = :negocio_id)
        select v.*, {_MARGEN} as margen, u.nombre as vendedor
          from venta v left join usuarios u on u.id = v.vendedor_id"""),
                      {'negocio_id': negocio_id}).first()
    if fila is None:
        raise NoEncontrado('La venta no existe.')
    if actor.alcance != 'todos' and fila.vendedor_id != actor.id:
        raise Prohibido('Esa venta no es suya y su alcance no la incluye.',
                        codigo='sin_alcance')
    return _venta(fila)
