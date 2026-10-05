from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Oportunidades, Usuarios
from app.schemas import oportunidades as esq
from app.services import oportunidades as servicio

router = APIRouter(tags=['embudo comercial'])


def _salida(o: Oportunidades) -> esq.OportunidadSalida:
    return esq.OportunidadSalida(
        id=o.id, cliente_id=o.cliente_id, cliente=o.cliente.nombre,
        estado=o.estado.codigo, estado_nombre=o.estado.nombre, es_cierre=o.estado.es_cierre,
        asesor=o.asesor.nombre if o.asesor else None, asesor_id=o.asesor_id,
        servicio_id=o.servicio_id, pais_id=o.pais_id, canal_id=o.canal_id,
        campania_id=o.campania_id, campania=o.campania,
        valor_estimado=float(o.valor_estimado) if o.valor_estimado is not None else None,
        proxima_accion=o.proxima_accion, proxima_accion_fecha=o.proxima_accion_fecha,
        dias_sin_contacto=servicio.dias_sin_contacto(o),
        ultimo_contacto_en=o.ultimo_contacto_en, motivo_perdida_id=o.motivo_perdida_id,
        creado_en=o.creado_en, cerrado_en=o.cerrado_en)


@router.get('/oportunidades', response_model=esq.PaginaOportunidades)
def listar(estado: str | None = None, asesor_id: int | None = None, canal_id: int | None = None,
           servicio_id: int | None = None, campania_id: int | None = None,
           incluir_cerradas: bool = False,
           frias_desde: int | None = Query(default=None,
                                           description='Sin contacto hace más de N días'),
           texto: str | None = None, pagina: int = 1, tamano: int = 50,
           actor: Usuarios = Depends(requiere('oportunidades.ver')),
           db: Session = Depends(get_db)):
    """Lista filtrable del embudo (RF-011).

    Lo que devuelve depende del alcance del usuario (RNF-03): una comercial con
    alcance «propios» ve sus oportunidades aunque no filtre por asesor.
    """
    total, filas = servicio.listar(db, actor=actor, estado_codigo=estado, asesor_id=asesor_id,
                                   canal_id=canal_id, servicio_id=servicio_id,
                                   campania_id=campania_id, incluir_cerradas=incluir_cerradas,
                                   frias_desde=frias_desde, texto=texto,
                                   pagina=pagina, tamano=tamano)
    return esq.PaginaOportunidades(total=total, pagina=pagina, tamano=tamano,
                                   items=[_salida(o) for o in filas])


@router.get('/oportunidades/embudo', response_model=list[esq.PasoEmbudo])
def embudo(actor: Usuarios = Depends(requiere('oportunidades.ver')), db: Session = Depends(get_db)):
    """Cuántas oportunidades y cuánto dinero hay en cada paso: el Kanban en números."""
    return [esq.PasoEmbudo(codigo=e.codigo, nombre=e.nombre, orden=e.orden,
                           es_cierre=e.es_cierre, cuantas=n, valor_estimado=v)
            for e, n, v in servicio.embudo(db, actor=actor)]


@router.post('/oportunidades', response_model=esq.OportunidadSalida,
             status_code=status.HTTP_201_CREATED)
def crear(datos: esq.OportunidadCrear, request: Request,
          actor: Usuarios = Depends(requiere('oportunidades.crear')),
          db: Session = Depends(get_db)):
    o = servicio.crear(db, actor, datos.model_dump(exclude_unset=True), ip=ip_cliente(request))
    return _salida(servicio.obtener(db, o.id))


@router.get('/oportunidades/{oportunidad_id}', response_model=esq.OportunidadSalida)
def detalle(oportunidad_id: int, actor: Usuarios = Depends(requiere('oportunidades.ver')),
            db: Session = Depends(get_db)):
    return _salida(servicio.obtener(db, oportunidad_id, actor=actor))


@router.patch('/oportunidades/{oportunidad_id}', response_model=esq.OportunidadSalida)
def editar(oportunidad_id: int, datos: esq.OportunidadEditar, request: Request,
           actor: Usuarios = Depends(requiere('oportunidades.editar')),
           db: Session = Depends(get_db)):
    servicio.editar(db, actor, oportunidad_id, datos.model_dump(exclude_unset=True),
                    ip=ip_cliente(request))
    return _salida(servicio.obtener(db, oportunidad_id, actor=actor))


@router.post('/oportunidades/{oportunidad_id}/estado', response_model=esq.OportunidadSalida)
def mover(oportunidad_id: int, datos: esq.MoverOportunidad, request: Request,
          actor: Usuarios = Depends(requiere('oportunidades.editar')),
          db: Session = Depends(get_db)):
    """Mueve la oportunidad por el embudo. Perder exige motivo (RF-015)."""
    servicio.mover(db, actor, oportunidad_id, codigo_destino=datos.codigo_destino,
                   motivo_perdida=datos.motivo_perdida, nota=datos.nota,
                   proxima_accion=datos.proxima_accion, ip=ip_cliente(request))
    return _salida(servicio.obtener(db, oportunidad_id, actor=actor))


@router.post('/oportunidades/{oportunidad_id}/contacto', response_model=esq.OportunidadSalida)
def contacto(oportunidad_id: int, datos: esq.ContactoOportunidad, request: Request,
             actor: Usuarios = Depends(requiere('oportunidades.editar')),
             db: Session = Depends(get_db)):
    """Deja constancia de que se le habló y de qué sigue (RF-012)."""
    servicio.registrar_contacto(db, actor, oportunidad_id,
                                proxima_accion=datos.proxima_accion,
                                proxima_accion_fecha=datos.proxima_accion_fecha,
                                ip=ip_cliente(request))
    return _salida(servicio.obtener(db, oportunidad_id, actor=actor))
