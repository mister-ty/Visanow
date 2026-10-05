from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Negocios, Usuarios
from app.schemas import ventas as esq
from app.services import ventas as servicio

router = APIRouter(tags=['cotización y ventas'])


def _salida(db: Session, n: Negocios) -> esq.VentaSalida:
    casos = servicio.casos_de_la_venta(db, n.id)
    return esq.VentaSalida(
        id=n.id, cliente_id=n.cliente_id, cliente=n.cliente.nombre,
        oportunidad_id=n.oportunidad_id, servicio_id=n.servicio_id, servicio=n.servicio.nombre,
        fecha_venta=n.fecha_venta, cantidad_solicitantes=n.cantidad_solicitantes,
        valor_lista=float(n.valor_lista), descuento=float(n.descuento),
        valor_pactado=float(n.valor_pactado), moneda=n.moneda, vendedor_id=n.vendedor_id,
        observaciones=n.observaciones, creado_en=n.creado_en,
        casos=[esq.CasoDeVenta(id=c.id, solicitante_id=c.solicitante_id,
                               solicitante=c.solicitante.nombre) for c in casos])


@router.post('/cotizar', response_model=esq.CotizacionSalida)
def cotizar(datos: esq.CotizarEntrada, _: Usuarios = Depends(requiere('oportunidades.ver')),
            db: Session = Depends(get_db)):
    """El precio del catálogo para N personas, con la tarifa vigente ese día (RF-013).

    No escribe nada: sirve para mostrarle al cliente qué va a pagar antes de
    cerrar la venta.
    """
    c = servicio.cotizar(db, **datos.model_dump(exclude_unset=True))
    return esq.CotizacionSalida(**c.__dict__)


@router.post('/oportunidades/{oportunidad_id}/ganar', response_model=esq.VentaSalida,
             status_code=status.HTTP_201_CREATED)
def ganar(oportunidad_id: int, datos: esq.ConvertirEntrada, request: Request,
          actor: Usuarios = Depends(requiere('negocios.crear')), db: Session = Depends(get_db)):
    """Convierte la oportunidad en venta y abre un trámite por persona (RF-014).

    Sin volver a digitar: el cliente, el servicio, el país y el asesor salen de
    la oportunidad, y las personas, de la ficha del cliente.
    """
    n = servicio.convertir(db, actor, oportunidad_id, ip=ip_cliente(request),
                           **datos.model_dump(exclude_unset=True))
    return _salida(db, servicio.obtener(db, n.id))


@router.get('/ventas/{negocio_id}', response_model=esq.VentaSalida)
def detalle(negocio_id: int, _: Usuarios = Depends(requiere('negocios.ver')),
            db: Session = Depends(get_db)):
    return _salida(db, servicio.obtener(db, negocio_id))
