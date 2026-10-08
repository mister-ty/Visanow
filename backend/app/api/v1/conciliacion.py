from datetime import date

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import MovimientosBanco, Usuarios
from app.schemas import conciliacion as esq
from app.services import conciliacion as serv

router = APIRouter(tags=['conciliación bancaria'])


def _movimiento(m: MovimientosBanco) -> esq.MovimientoSalida:
    negocio_id, cliente = None, None
    if m.pago is not None:
        negocio_id = m.pago.negocio_id
        if m.pago.negocio is not None and m.pago.negocio.cliente is not None:
            cliente = m.pago.negocio.cliente.nombre
    return esq.MovimientoSalida(
        id=m.id, banco=m.banco, fecha=m.fecha, valor=float(m.valor), moneda=m.moneda,
        descripcion=m.descripcion, referencia=m.referencia, estado=m.estado,
        pago_id=m.pago_id, negocio_id=negocio_id, cliente=cliente,
        duplicado_de_id=m.duplicado_de_id,
        motivo_descarte=m.motivo_descarte, nota_cliente=m.nota_cliente,
        nota_abono=m.nota_abono, conciliado_en=m.conciliado_en, creado_en=m.creado_en)


@router.post('/conciliacion/importar', response_model=esq.ImportarSalida,
             status_code=status.HTTP_201_CREATED)
def importar(datos: esq.ImportarEntrada, request: Request,
             actor: Usuarios = Depends(requiere('pagos.crear')),
             db: Session = Depends(get_db)):
    """Carga las líneas del extracto del banco (RF-044).

    Se puede correr dos veces el mismo archivo sin duplicar nada: cada línea
    lleva una huella. Lo que entra no queda cuadrado contra nada todavía.
    """
    r = serv.importar(db, actor, [m.model_dump() for m in datos.movimientos],
                      archivo=datos.archivo, hoja=datos.hoja, ip=ip_cliente(request))
    return esq.ImportarSalida(leidos=r.leidos, nuevos=r.nuevos, repetidos=r.repetidos,
                              sin_fecha=r.sin_fecha, sin_valor=r.sin_valor)


@router.get('/conciliacion/movimientos', response_model=esq.PaginaMovimientos)
def bandeja(estado: esq.EstadoMovimiento | None = 'sin_conciliar',
            desde: date | None = None, hasta: date | None = None,
            banco: str | None = None, pagina: int = 1, tamano: int = 50,
            _: Usuarios = Depends(requiere('pagos.ver')), db: Session = Depends(get_db)):
    """El extracto, por estado. Por defecto, lo que falta por cuadrar."""
    total, suma, filas = serv.bandeja(db, estado=estado, desde=desde, hasta=hasta,
                                      banco=banco, pagina=pagina, tamano=tamano)
    return esq.PaginaMovimientos(total=total, suma=suma, pagina=pagina, tamano=tamano,
                                 items=[_movimiento(m) for m in filas])


@router.get('/conciliacion/movimientos/{movimiento_id}/candidatos',
            response_model=esq.SugerenciasSalida)
def candidatos(movimiento_id: int, dias: int = serv.DIAS_DE_GRACIA,
               _: Usuarios = Depends(requiere('pagos.ver')), db: Session = Depends(get_db)):
    """Los pagos que calzan por valor y fecha.

    Nunca por nombre: quien consigna muchas veces no es el cliente, así que el
    nombre produciría cruces falsos, y un cruce falso deja una venta marcada
    como pagada con plata de otro.
    """
    m, posibles = serv.sugerencias(db, movimiento_id, dias=dias)
    exactos = [c for c in posibles if c.exacto]
    return esq.SugerenciasSalida(
        movimiento=_movimiento(m),
        candidatos=[esq.CandidatoSalida(**vars(c)) for c in posibles],
        sin_duda=len(exactos) == 1)


@router.post('/conciliacion/cruzar', response_model=esq.CruceAutomaticoSalida)
def cruzar(datos: esq.CruceAutomaticoEntrada, request: Request,
           actor: Usuarios = Depends(requiere('pagos.editar')),
           db: Session = Depends(get_db)):
    """Cuadra solas las que no tienen duda y deja el resto a la vista.

    «Sin duda» es estricto: un solo pago candidato y del mismo día. Si hay dos
    pagos del mismo valor esa semana, los dos se quedan sin cuadrar.
    """
    r = serv.cruzar_automatico(db, actor, desde=datos.desde, hasta=datos.hasta,
                               ip=ip_cliente(request))
    return esq.CruceAutomaticoSalida(**r)


@router.post('/conciliacion/movimientos/{movimiento_id}/conciliar',
             response_model=esq.MovimientoSalida)
def conciliar(movimiento_id: int, datos: esq.ConciliarEntrada, request: Request,
              actor: Usuarios = Depends(requiere('pagos.editar')),
              db: Session = Depends(get_db)):
    """Cuadra el movimiento contra un pago, o contra una venta creando el pago.

    Lo segundo es el caso de todos los días: el cliente avisa por WhatsApp que
    consignó y el pago todavía no está registrado, así que nace del movimiento
    del banco, con su fecha y su valor.
    """
    m = serv.conciliar(db, actor, movimiento_id, pago_id=datos.pago_id,
                       negocio_id=datos.negocio_id, ip=ip_cliente(request))
    return _movimiento(m)


@router.post('/conciliacion/movimientos/{movimiento_id}/parcial',
             response_model=esq.MovimientoSalida)
def parcial(movimiento_id: int, datos: esq.ParcialEntrada, request: Request,
            actor: Usuarios = Depends(requiere('pagos.editar')),
            db: Session = Depends(get_db)):
    """El movimiento cubre solo una parte de un pago, o al reves.

    El cliente paga una venta con dos transferencias, o manda una sola que cubre
    dos ventas. Queda a medias y dicho, en vez de darse por cerrado.
    """
    return _movimiento(serv.marcar_parcial(db, actor, movimiento_id, datos.pago_id,
                                           ip=ip_cliente(request)))


@router.post('/conciliacion/movimientos/{movimiento_id}/duplicado',
             response_model=esq.MovimientoSalida)
def duplicado(movimiento_id: int, datos: esq.DuplicadoEntrada, request: Request,
              actor: Usuarios = Depends(requiere('pagos.editar')),
              db: Session = Depends(get_db)):
    """El banco reporto dos veces la misma transferencia.

    Se marca la repetida apuntando a la buena. No se borra: el extracto tiene
    que seguir cuadrando linea por linea contra lo que mando el banco.
    """
    return _movimiento(serv.marcar_duplicado(db, actor, movimiento_id,
                                             datos.duplicado_de_id, ip=ip_cliente(request)))


@router.post('/conciliacion/movimientos/{movimiento_id}/reversado',
             response_model=esq.MovimientoSalida)
def reversado(movimiento_id: int, datos: esq.ReversadoEntrada, request: Request,
              actor: Usuarios = Depends(requiere('pagos.editar')),
              db: Session = Depends(get_db)):
    """La plata entro y se devolvio: no es ingreso aunque aparezca como tal."""
    return _movimiento(serv.marcar_reversado(db, actor, movimiento_id, datos.motivo,
                                             ip=ip_cliente(request)))


@router.post('/conciliacion/movimientos/{movimiento_id}/descartar',
             response_model=esq.MovimientoSalida)
def descartar(movimiento_id: int, datos: esq.DescartarEntrada, request: Request,
              actor: Usuarios = Depends(requiere('pagos.editar')),
              db: Session = Depends(get_db)):
    """Marca el movimiento como que no es plata de un cliente, con su razón.

    No se borra: la línea sigue ahí con el motivo, porque el extracto tiene que
    seguir cuadrando contra el banco.
    """
    return _movimiento(serv.descartar(db, actor, movimiento_id, datos.motivo,
                                      ip=ip_cliente(request)))


@router.post('/conciliacion/movimientos/{movimiento_id}/deshacer',
             response_model=esq.MovimientoSalida)
def deshacer(movimiento_id: int, request: Request,
             actor: Usuarios = Depends(requiere('pagos.editar')),
             db: Session = Depends(get_db)):
    """Devuelve el movimiento a la bandeja. El pago que se le creó no se borra."""
    return _movimiento(serv.deshacer(db, actor, movimiento_id, ip=ip_cliente(request)))


@router.get('/conciliacion/resumen', response_model=esq.ResumenSalida)
def resumen(desde: date | None = None, hasta: date | None = None,
            _: Usuarios = Depends(requiere('pagos.ver')), db: Session = Depends(get_db)):
    """Cuánto del extracto está cuadrado y cuánto no: el número del cierre."""
    return esq.ResumenSalida(**serv.resumen(db, desde=desde, hasta=hasta))
