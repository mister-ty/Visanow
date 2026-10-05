"""Cotizar y convertir la oportunidad en venta (RF-013, RF-014, RF-040).

Dos cosas que hoy se hacen a mano y se equivocan por eso:

**Cotizar.** El precio depende del servicio y de cuántas personas viajan, y la
lista de precios lo dice: adelantos para una persona son $700.000 y para cuatro
$2.300.000, que no es cuatro veces el de una. Hoy alguien hace esa cuenta en la
cabeza o copia de una cotización anterior, que puede ser de otra época de
precios. Aquí el precio sale del catálogo, con la tarifa que estaba vigente el
día de la venta y no la última que alguien cargó.

**Convertir.** Al ganar la oportunidad hay que crear la venta y abrir un trámite
por cada persona que viaja. Hacerlo a mano significa volver a digitar el
cliente, el servicio y el país tres veces, y es donde se cuelan los errores.

Una regla que atraviesa las dos: **la tasa consular no es parte del precio.** Son
$185 por persona que el cliente le paga directamente al consulado (lo confirmó
la administradora el 03/10). Entra en la cotización como información, para que
el cliente sepa cuánto le va a costar todo, pero no suma al valor pactado ni
entra en la base de la comisión.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import Conflicto, Invalido, NoEncontrado
from app.models.esquema import (Casos, EstadosOperativos, Grupos, Negocios, Oportunidades,
                                Servicios, Solicitantes, Tarifas, Usuarios)
from app.services import oportunidades as serv_oportunidades
from app.services.auditoria import auditar, instantanea

BOGOTA = ZoneInfo('America/Bogota')
ESTADO_CASO_INICIAL = 'registrado'


@dataclass
class Cotizacion:
    """Lo que se le dice al cliente que va a pagar, desglosado."""
    servicio_id: int
    servicio: str
    personas: int
    valor_lista: float
    descuento: float
    valor_pactado: float
    moneda: str
    tarifa_id: int | None
    vigente_desde: dt.date | None
    # La tasa consular va aparte: es plata del consulado, no de VisaNow
    tasa_consular_valor: float | None = None
    tasa_consular_moneda: str | None = None
    tasa_consular_total: float | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def hay_tarifa(self) -> bool:
        return self.tarifa_id is not None


def tarifa_vigente(db: Session, servicio_id: int, personas: int,
                   fecha: dt.date) -> Tarifas | None:
    """La tarifa que regía ese día para ese número de personas.

    Se elige por vigencia y no «la última»: hay dos épocas de precios en el
    catálogo, y cotizar una venta de hace tres meses con los precios de hoy la
    deja mal. Si no hay tarifa para ese número exacto de personas, se toma la
    del grupo más grande que sí exista y se avisa: los grupos de seis y siete
    no están en la lista de precios y se negocian.
    """
    base = (select(Tarifas)
            .where(Tarifas.servicio_id == servicio_id,
                   Tarifas.vigente_desde <= fecha,
                   (Tarifas.vigente_hasta.is_(None)) | (Tarifas.vigente_hasta >= fecha)))
    exacta = db.scalars(base.where(Tarifas.personas == personas)
                        .order_by(Tarifas.vigente_desde.desc())).first()
    if exacta:
        return exacta
    return db.scalars(base.where(Tarifas.personas <= personas)
                      .order_by(Tarifas.personas.desc(),
                                Tarifas.vigente_desde.desc())).first()


def cotizar(db: Session, *, servicio_id: int, personas: int = 1,
            descuento: float = 0.0, fecha: dt.date | None = None,
            valor_pactado: float | None = None) -> Cotizacion:
    """El precio de un servicio para N personas, con su desglose (RF-013)."""
    if personas < 1:
        raise Invalido('La cantidad de personas tiene que ser al menos una.')
    servicio = db.get(Servicios, servicio_id)
    if servicio is None:
        raise NoEncontrado('El servicio no existe.')
    fecha = fecha or dt.datetime.now(BOGOTA).date()

    tarifa = tarifa_vigente(db, servicio_id, personas, fecha)
    avisos: list[str] = []
    if tarifa is None:
        lista = float(valor_pactado or 0)
        avisos.append(f'No hay tarifa de catálogo para «{servicio.nombre}» vigente al '
                      f'{fecha:%d/%m/%Y}: el valor se negocia y queda anotado.')
    else:
        lista = float(tarifa.valor)
        if tarifa.personas != personas:
            avisos.append(f'La lista de precios llega hasta {tarifa.personas} persona(s). '
                          f'Para {personas} se toma esa tarifa como base y se negocia el resto.')

    pactado = float(valor_pactado) if valor_pactado is not None else max(0.0, lista - descuento)
    # Si dieron el precio negociado, el descuento es la diferencia: así el
    # sistema siempre puede decir cuánto se rebajó y sobre qué.
    rebaja = max(0.0, lista - pactado) if valor_pactado is not None else max(0.0, descuento)
    if pactado > lista and tarifa is not None:
        avisos.append('El valor pactado es mayor que el de lista. Si es a propósito '
                      '(extras, urgencia), anótelo en las observaciones de la venta.')

    cot = Cotizacion(
        servicio_id=servicio.id, servicio=servicio.nombre, personas=personas,
        valor_lista=lista, descuento=rebaja, valor_pactado=pactado,
        moneda=tarifa.moneda if tarifa else 'COP',
        tarifa_id=tarifa.id if tarifa else None,
        vigente_desde=tarifa.vigente_desde if tarifa else None, avisos=avisos)

    if servicio.tasa_consular_valor:
        cot.tasa_consular_valor = float(servicio.tasa_consular_valor)
        cot.tasa_consular_moneda = servicio.tasa_consular_moneda
        cot.tasa_consular_total = float(servicio.tasa_consular_valor) * personas
        cot.avisos.append(
            f'Además, la tasa consular de {cot.tasa_consular_total:,.0f} '
            f'{cot.tasa_consular_moneda} ({personas} × {cot.tasa_consular_valor:,.0f}) la paga '
            f'el cliente directamente al consulado: no entra en este valor ni comisiona.')
    return cot


# ------------------------------------------------------- conversión a venta

def _personas_del_cliente(db: Session, cliente_id: int) -> list[Solicitantes]:
    grupos = select(Grupos.id).where(Grupos.cliente_contacto_id == cliente_id)
    return list(db.scalars(
        select(Solicitantes)
        .where(Solicitantes.fusionado_en_id.is_(None),
               (Solicitantes.cliente_id == cliente_id) | (Solicitantes.grupo_id.in_(grupos)))
        .order_by(Solicitantes.id)))


def convertir(db: Session, actor: Usuarios, oportunidad_id: int, *, servicio_id: int | None = None,
              personas: int | None = None, descuento: float = 0.0,
              valor_pactado: float | None = None, fecha_venta: dt.date | None = None,
              solicitantes_ids: list[int] | None = None, pais_id: int | None = None,
              observaciones: str | None = None,
              abrir_tramites: bool = True, ip: str | None = None) -> Negocios:
    """Gana la oportunidad: crea la venta y abre un trámite por persona (RF-014).

    «Sin volver a digitar» es el punto: el cliente, el servicio, el país y el
    asesor salen de la oportunidad; las personas, de la ficha del cliente. Lo
    único que se pregunta es el precio y quiénes viajan.
    """
    o = serv_oportunidades.obtener(db, oportunidad_id, actor=actor)
    if o.estado.es_cierre:
        raise Conflicto('La oportunidad ya está cerrada.', codigo='oportunidad_cerrada')

    servicio_id = servicio_id or o.servicio_id
    if not servicio_id:
        raise Invalido('Diga qué servicio se vendió: la oportunidad no lo tiene registrado.')

    viajan = ([db.get(Solicitantes, i) for i in solicitantes_ids] if solicitantes_ids
              else _personas_del_cliente(db, o.cliente_id))
    viajan = [s for s in viajan if s is not None]
    if abrir_tramites and not viajan:
        raise Invalido('Registre al menos una persona que viaja antes de convertir la venta. '
                       'El trámite se abre sobre la persona, no sobre el cliente.',
                       codigo='sin_solicitantes')

    cantidad = personas or len(viajan) or 1
    fecha = fecha_venta or dt.datetime.now(BOGOTA).date()
    cot = cotizar(db, servicio_id=servicio_id, personas=cantidad,
                  descuento=descuento, fecha=fecha, valor_pactado=valor_pactado)

    negocio = Negocios(cliente_id=o.cliente_id, oportunidad_id=o.id, servicio_id=servicio_id,
                       fecha_venta=fecha, cantidad_solicitantes=cantidad,
                       valor_lista=Decimal(str(cot.valor_lista)),
                       descuento=Decimal(str(cot.descuento)),
                       valor_pactado=Decimal(str(cot.valor_pactado)),
                       moneda=cot.moneda, vendedor_id=o.asesor_id, canal_id=o.canal_id,
                       observaciones=observaciones)
    db.add(negocio)
    db.flush()

    casos = []
    if abrir_tramites:
        estado = db.scalar(select(EstadosOperativos)
                           .where(EstadosOperativos.codigo == ESTADO_CASO_INICIAL))
        destino = pais_id or o.pais_id or db.get(Servicios, servicio_id).pais_id
        if destino is None:
            raise Invalido('Diga a qué país es la visa: ni la oportunidad ni el servicio lo dicen.',
                           codigo='falta_pais')
        for s in viajan:
            caso = Casos(solicitante_id=s.id, pais_id=destino, estado_id=estado.id,
                         fuente='manual', negocio_id=negocio.id, responsable_id=o.asesor_id,
                         proxima_accion='Pedir documentos al cliente',
                         ultima_actividad_en=dt.datetime.now(BOGOTA))
            db.add(caso)
            casos.append(caso)
        db.flush()
        for caso in casos:
            db.add(_historial_creado(caso, negocio, actor))

    auditar(db, operacion='insert', entidad='negocios', usuario_id=actor.id, entidad_id=negocio.id,
            despues=instantanea(negocio) | {'casos_creados': len(casos)}, ip=ip)
    db.commit()

    # Se gana después de crear la venta: si algo falla arriba, la oportunidad
    # sigue abierta y se puede reintentar sin quedar en un estado a medias.
    serv_oportunidades.mover(db, actor, oportunidad_id, codigo_destino='ganado', ip=ip)
    db.refresh(negocio)
    return negocio


def _historial_creado(caso: Casos, negocio: Negocios, actor: Usuarios):
    from app.models.esquema import CasosHistorial
    return CasosHistorial(
        caso_id=caso.id, campo='creado', valor_anterior=None, valor_nuevo=ESTADO_CASO_INICIAL,
        usuario_id=actor.id,
        observacion=f'Trámite abierto automáticamente al ganar la venta #{negocio.id}')


def casos_de_la_venta(db: Session, negocio_id: int) -> list[Casos]:
    return list(db.scalars(select(Casos).where(Casos.negocio_id == negocio_id)
                           .options(selectinload(Casos.solicitante))
                           .order_by(Casos.id)))


def obtener(db: Session, negocio_id: int) -> Negocios:
    n = db.get(Negocios, negocio_id, options=[selectinload(Negocios.cliente),
                                              selectinload(Negocios.servicio)])
    if n is None:
        raise NoEncontrado('La venta no existe.')
    return n
