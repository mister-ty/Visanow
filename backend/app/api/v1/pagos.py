from datetime import date

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.paginacion import Pagina, Tamano
from app.core.deps import ip_cliente, requiere
from app.core.errores import NoEncontrado
from app.db.session import get_db
from app.models.esquema import AjustesNegocio, CuotasNegocio, Pagos, Usuarios
from app.schemas import pagos as esq
from app.services import cartera as serv_cartera
from app.services import pagos as servicio

router = APIRouter(tags=['pagos, saldo y cartera'])


def _pago(p: Pagos) -> esq.PagoSalida:
    return esq.PagoSalida(
        id=p.id, negocio_id=p.negocio_id, fecha=p.fecha, monto_bruto=float(p.monto_bruto),
        costo_medio=float(p.costo_medio), monto_neto=float(p.monto_neto or 0), moneda=p.moneda,
        medio_pago_id=p.medio_pago_id, medio_pago=p.medio_pago.nombre if p.medio_pago else None,
        banco_cuenta_id=p.banco_cuenta_id, referencia=p.referencia, estado=p.estado,
        pagador_nombre=p.pagador_nombre, observacion=p.observacion, creado_en=p.creado_en)


def _cuota(c: CuotasNegocio) -> esq.CuotaSalida:
    return esq.CuotaSalida(numero=c.numero, concepto=c.concepto, monto=float(c.monto),
                           fecha_pactada=c.fecha_pactada)


def _ajuste(a: AjustesNegocio) -> esq.AjusteSalida:
    return esq.AjusteSalida(id=a.id, tipo=a.tipo, monto=float(a.monto), motivo=a.motivo,
                            fecha=a.fecha, autorizado_por=a.autorizado_por)


# --------------------------------------------------------------------- pagos

@router.post('/pagos', response_model=esq.PagoSalida, status_code=status.HTTP_201_CREATED)
def registrar(datos: esq.PagoCrear, request: Request,
              actor: Usuarios = Depends(requiere('pagos.crear')), db: Session = Depends(get_db)):
    """Un pago es una fila, no una columna (RN-02): caben los que sean.

    Si no se sabe de qué venta es, entra igual y queda en la bandeja de no
    identificados: es mejor que perderlo o inventarle dueño (RF-043).
    """
    return _pago(servicio.registrar(db, actor, datos.model_dump(exclude_unset=True),
                                    ip=ip_cliente(request)))


@router.get('/pagos', response_model=esq.PaginaPagos)
def listar(negocio_id: int | None = None,
           sin_asignar: bool = Query(default=False, description='La bandeja de no identificados'),
           desde: date | None = None, hasta: date | None = None,
           referencia: str | None = Query(default=None,
                                          description='La referencia del comprobante, o un '
                                                      'pedazo de ella (RF-029)'),
           pagina: Pagina = 1, tamano: Tamano = 50,
           _: Usuarios = Depends(requiere('pagos.ver')), db: Session = Depends(get_db)):
    """Los pagos, con los filtros de la pantalla.

    Buscar por referencia es la forma de responder «¿llegó este pago?» con el
    comprobante del cliente a la vista, sin tener que adivinar la fecha.
    """
    total, filas = servicio.listar(db, negocio_id=negocio_id, sin_asignar=sin_asignar,
                                   desde=desde, hasta=hasta, referencia=referencia,
                                   pagina=pagina, tamano=tamano)
    return esq.PaginaPagos(total=total, pagina=pagina, tamano=tamano,
                           items=[_pago(p) for p in filas])


@router.post('/pagos/{pago_id}/asignar', response_model=esq.PagoSalida)
def asignar(pago_id: int, datos: esq.AsignarPago, request: Request,
            actor: Usuarios = Depends(requiere('pagos.editar')), db: Session = Depends(get_db)):
    """Le pone dueño a un pago que llegó suelto."""
    return _pago(servicio.asignar(db, actor, pago_id, datos.negocio_id, ip=ip_cliente(request)))


@router.post('/pagos/{pago_id}/estado', response_model=esq.PagoSalida)
def cambiar_estado(pago_id: int, datos: esq.CambiarEstadoPago, request: Request,
                   actor: Usuarios = Depends(requiere('pagos.editar')),
                   db: Session = Depends(get_db)):
    """Reversar o marcar duplicado. Nunca se borra: un pago borrado es plata que
    desaparece del historial sin dejar rastro."""
    return _pago(servicio.cambiar_estado(db, actor, pago_id, datos.estado, datos.observacion,
                                         ip=ip_cliente(request)))


# ------------------------------------------------- acuerdo económico y saldo

@router.post('/ventas/{negocio_id}/cuotas', response_model=list[esq.CuotaSalida],
             status_code=status.HTTP_201_CREATED)
def crear_cuotas(negocio_id: int, datos: esq.PlanCuotas, request: Request,
                 actor: Usuarios = Depends(requiere('negocios.editar')),
                 db: Session = Depends(get_db)):
    """Parte la venta en anticipo y saldo (RF-040).

    Sin plan de cuotas la cartera vencida sale en cero: una venta que no vence
    nunca no la cobra nadie.
    """
    cuotas = servicio.plan_de_cuotas(db, actor, negocio_id, reparto=datos.reparto,
                                     plazo_dias=datos.plazo_dias, ip=ip_cliente(request))
    return [_cuota(c) for c in cuotas]


@router.get('/ventas/{negocio_id}/estado-financiero', response_model=esq.EstadoFinancieroSalida)
def estado_financiero(negocio_id: int, _: Usuarios = Depends(requiere('pagos.ver')),
                      db: Session = Depends(get_db)):
    """El saldo y su desglose (RF-042). Lo calcula la vista, no se guarda (RN-01)."""
    estado = serv_cartera.estado_de(db, negocio_id)
    if estado is None:
        raise NoEncontrado('La venta no existe.')
    return esq.EstadoFinancieroSalida(
        **estado.__dict__,
        cuotas=[_cuota(c) for c in servicio.cuotas_de(db, negocio_id)],
        pagos=[_pago(p) for p in servicio.pagos_de(db, negocio_id)],
        ajustes_detalle=[_ajuste(a) for a in servicio.ajustes_de(db, negocio_id)])


@router.post('/ventas/{negocio_id}/ajustes', response_model=esq.AjusteSalida,
             status_code=status.HTTP_201_CREATED)
def ajustar(negocio_id: int, datos: esq.AjusteCrear, request: Request,
            actor: Usuarios = Depends(requiere('ajustes.crear')), db: Session = Depends(get_db)):
    """Reembolsos, cargos, descuentos posteriores y condonaciones (RF-045).

    El monto va siempre en positivo: el tipo decide si sube o baja la deuda.
    """
    return _ajuste(servicio.ajustar(db, actor, negocio_id, tipo=datos.tipo, monto=datos.monto,
                                    motivo=datos.motivo, fecha=datos.fecha,
                                    ip=ip_cliente(request)))


# ------------------------------------------------------------------- cartera

class FiltrosCartera:
    """Lo que se puede filtrar de la cartera (RF-046).

    Van juntos en una sola clase porque la lista, los totales de arriba y el
    informe por edades admiten exactamente los mismos filtros. Si cada
    respuesta tuviera los suyos, la pantalla acabaría mostrando totales de una
    cosa y una tabla de otra.

    Filtrar es una comodidad del usuario, no un control de acceso: quién puede
    ver montos lo decide el permiso `pagos.ver`.
    """

    def __init__(
        self,
        solo_vencida: bool = False,
        tramo: esq.TramoMora | None = Query(
            default=None, description='Solo un corte de antigüedad: 1_30, 31_60, 61_90, mas_90'),
        desde_dias: int | None = Query(default=None, ge=0,
                                       description='Vencida hace más de N días'),
        vence_en_dias: int | None = Query(
            default=None, ge=0, description='Lo que se le vence en los próximos N días'),
        vendedor_id: int | None = None,
        cliente_id: int | None = None,
        servicio_id: int | None = None,
        desde: date | None = Query(default=None, description='Vendido desde esta fecha'),
        hasta: date | None = Query(default=None, description='Vendido hasta esta fecha'),
    ):
        self.como_dict = {
            'solo_vencida': solo_vencida, 'tramo': tramo, 'desde_dias': desde_dias,
            'vence_en_dias': vence_en_dias, 'vendedor_id': vendedor_id,
            'cliente_id': cliente_id, 'servicio_id': servicio_id,
            'desde': desde, 'hasta': hasta}


@router.get('/cartera', response_model=esq.PaginaCartera)
def listar_cartera(filtros: FiltrosCartera = Depends(), pagina: Pagina = 1, tamano: Tamano = 50,
                   _: Usuarios = Depends(requiere('pagos.ver')), db: Session = Depends(get_db)):
    """Quién debe, cuánto, desde cuándo y qué se le vence (RF-046)."""
    total, suma, filas = serv_cartera.cartera(db, pagina=pagina, tamano=tamano,
                                              **filtros.como_dict)
    return esq.PaginaCartera(total=total, suma_saldo=suma, pagina=pagina, tamano=tamano,
                             items=[esq.FilaCarteraSalida(**f.__dict__) for f in filas])


@router.get('/cartera/resumen', response_model=esq.ResumenCartera)
def resumen_cartera(filtros: FiltrosCartera = Depends(),
                    _: Usuarios = Depends(requiere('pagos.ver')), db: Session = Depends(get_db)):
    """Los totales de lo que se está mirando: obedecen el filtro igual que la tabla."""
    return esq.ResumenCartera(**serv_cartera.resumen(db, **filtros.como_dict))


@router.get('/cartera/antiguedad', response_model=list[esq.TramoAntiguedad])
def cartera_por_antiguedad(filtros: FiltrosCartera = Depends(),
                           _: Usuarios = Depends(requiere('pagos.ver')),
                           db: Session = Depends(get_db)):
    """La cartera repartida por edades, en los cortes de la contabilidad (RF-046).

    Es el informe con el que se cobra: dice cuánta plata lleva entre 1 y 30
    días, entre 31 y 60, entre 61 y 90, y cuánta pasó de 90 y ya hay que tratar
    aparte.
    """
    return [esq.TramoAntiguedad(**t) for t in serv_cartera.antiguedad(db, **filtros.como_dict)]


@router.get('/cartera/por-estado', response_model=list[esq.PorEstado])
def cartera_por_estado(_: Usuarios = Depends(requiere('pagos.ver')),
                       db: Session = Depends(get_db)):
    return [esq.PorEstado(estado=e, cuantas=n, saldo=s) for e, n, s in serv_cartera.por_estado(db)]
