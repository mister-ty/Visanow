from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.schemas import fichas as esq
from app.services import casos as serv_casos
from app.services import fichas, personas
from app.services.usuarios import permisos_de_rol

router = APIRouter(tags=['ficha 360 y búsqueda'])


@router.get('/buscar', response_model=list[esq.ResultadoBusqueda])
def buscar(q: str = Query(min_length=2, description='Nombre, teléfono, documento, correo, pasaporte, '
                                                    'DS-160 o n.º de solicitud del SaaS'),
           _: Usuarios = Depends(requiere('clientes.ver')), db: Session = Depends(get_db)):
    """Una sola caja de búsqueda para todo el sistema (RF-029)."""
    return [esq.ResultadoBusqueda(**r.__dict__) for r in fichas.buscar_global(db, q)]


@router.get('/clientes/{cliente_id}/ficha', response_model=esq.Ficha360)
def ficha_360(cliente_id: int, actor: Usuarios = Depends(requiere('clientes.ver')),
              db: Session = Depends(get_db)):
    """RF-005: el cliente, quiénes viajan con él, sus trámites, sus próximas
    citas y la cronología, en una sola pantalla."""
    from app.api.v1.clientes import detalle as detalle_cliente
    from app.api.v1.casos import _salida as caso_salida

    cliente = personas.obtener(db, cliente_id)
    ve_tramites = 'casos.ver' in permisos_de_rol(db, actor.rol_id)
    tramites = fichas.tramites_de(db, cliente_id) if ve_tramites else []
    citas = fichas.proximas_citas(db, cliente_id) if ve_tramites else []
    personas_totales = len(fichas.solicitantes_ids(db, cliente_id))
    ahora = datetime.now(timezone.utc)

    return esq.Ficha360(
        cliente=detalle_cliente(cliente_id, actor, db),
        resumen=esq.ResumenFicha(
            personas=personas_totales,
            tramites_abiertos=sum(1 for c in tramites if not c.estado.es_final),
            tramites_total=len(tramites),
            proxima_cita=citas[0].inicia_en if citas else None,
            ultimo_contacto_en=cliente.ultimo_contacto_en,
            dias_sin_contacto=((ahora - cliente.ultimo_contacto_en).days
                               if cliente.ultimo_contacto_en else None)),
        tramites=[caso_salida(db, c) for c in tramites],
        citas=[esq.CitaProxima(id=x.id, caso_id=x.caso_id, solicitante=x.caso.solicitante.nombre,
                               tipo=x.tipo, inicia_en=x.inicia_en, estado=x.estado,
                               sede=x.sede.nombre if x.sede else None) for x in citas],
        cronologia=[esq.SucesoSalida(**s.__dict__) for s in fichas.cronologia(db, cliente_id)],
        ve_tramites=ve_tramites)


@router.post('/clientes/{cliente_id}/notas', response_model=esq.NotaSalida,
             status_code=status.HTTP_201_CREATED)
def anotar_cliente(cliente_id: int, datos: esq.NotaCrear, request: Request,
                   actor: Usuarios = Depends(requiere('clientes.editar')),
                   db: Session = Depends(get_db)):
    """Deja constancia de una llamada, un WhatsApp o una nota (RF-012)."""
    personas.obtener(db, cliente_id)       # 404 si no existe
    a = fichas.registrar_nota(db, actor, entidad='cliente', entidad_id=cliente_id,
                              ip=ip_cliente(request), **datos.model_dump())
    return esq.NotaSalida.model_validate(a, from_attributes=True)


@router.post('/casos/{caso_id}/notas', response_model=esq.NotaSalida,
             status_code=status.HTTP_201_CREATED)
def anotar_caso(caso_id: int, datos: esq.NotaCrear, request: Request,
                actor: Usuarios = Depends(requiere('casos.editar')), db: Session = Depends(get_db)):
    serv_casos.obtener(db, caso_id)        # 404 si no existe
    a = fichas.registrar_nota(db, actor, entidad='caso', entidad_id=caso_id,
                              ip=ip_cliente(request), **datos.model_dump())
    return esq.NotaSalida.model_validate(a, from_attributes=True)
