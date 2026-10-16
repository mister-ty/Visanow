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


# Ojo con el orden: `/ventas/repetidas` va ANTES de `/ventas/{negocio_id}`.
# FastAPI resuelve por orden de declaración, así que con la variable primero la
# palabra «repetidas» entra como si fuera un id y la respuesta es un 422 por un
# entero que no es un entero. La ruta existiría y no se podría llamar. Hay prueba
# que la llama por su URL, que es la única forma de que esto no vuelva a pasar.
@router.get('/ventas/repetidas', response_model=list[esq.VentaRepetida])
def repetidas(_: Usuarios = Depends(requiere('pagos.ver')), db: Session = Depends(get_db)):
    """Ventas que parecen ser la misma anotada dos veces (RF-040).

    La carga trajo el mismo negocio dos veces cuando aparecía en dos hojas del
    mismo libro: la idempotencia es por `(archivo, hoja, fila)`, así que el
    mismo hecho en dos sitios son dos filas. Medido sobre producción: 16 casos y
    $18.006.000 de más en la cartera, que es el número con el que se decide a
    quién se le cobra.

    Exige `pagos.ver` y no `negocios.ver`: lo que esta lista enseña son montos y
    saldos, que es «lo de la contabilidad» que operaciones no ve.
    """
    return [esq.VentaRepetida(**g) for g in servicio.repetidas(db)]


@router.get('/ventas/{negocio_id}', response_model=esq.VentaSalida)
def detalle(negocio_id: int, _: Usuarios = Depends(requiere('negocios.ver')),
            db: Session = Depends(get_db)):
    return _salida(db, servicio.obtener(db, negocio_id))


@router.post('/ventas/{negocio_id}/anular', response_model=esq.VentaSalida)
def anular(negocio_id: int, datos: esq.AnularVentaEntrada, request: Request,
           actor: Usuarios = Depends(requiere('negocios.editar')),
           db: Session = Depends(get_db)):
    """Saca una venta de la cartera sin borrarla (RN-01, RN-08).

    Se niega si todavía tiene pagos confirmados: en las ventas repetidas los
    pagos están repartidos entre las dos copias, así que anular a secas haría
    desaparecer plata que sí entró. Cada pago se resuelve antes, marcándolo
    duplicado o moviéndolo a la venta que se queda.
    """
    n = servicio.anular(db, actor, negocio_id, datos.motivo, ip=ip_cliente(request))
    return _salida(db, n)
