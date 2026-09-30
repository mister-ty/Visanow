from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.core.errores import Prohibido
from app.db.session import get_db
from app.models.esquema import Casos, Usuarios
from app.schemas import casos as esq
from app.services import casos as servicio
from app.services.historial import describir
from app.services.usuarios import permisos_de_rol

router = APIRouter(tags=['trámites'])


def _salida(db: Session, c: Casos) -> esq.CasoSalida:
    return esq.CasoSalida(
        id=c.id, solicitante_id=c.solicitante_id, solicitante=c.solicitante.nombre,
        estado=c.estado.codigo, estado_nombre=c.estado.nombre, es_final=c.estado.es_final,
        responsable=c.responsable.nombre if c.responsable else None, responsable_id=c.responsable_id,
        pais=c.pais.nombre if c.pais else None, fuente=c.fuente, id_externo=c.id_externo,
        resultado=c.resultado, proxima_accion=c.proxima_accion,
        proxima_accion_fecha=c.proxima_accion_fecha,
        dias_sin_movimiento=servicio.dias_sin_movimiento(c), riesgo=servicio.riesgo(c),
        sin_venta=c.negocio_id is None, ultima_actividad_en=c.ultima_actividad_en)


@router.get('/casos', response_model=esq.PaginaCasos)
def listar(estado: str | None = None, responsable_id: int | None = None, pais_id: int | None = None,
           fuente: esq.Fuente | None = None, sin_asignar: bool = False, sin_venta: bool = False,
           incluir_finalizados: bool = False, texto: str | None = None, pagina: int = 1, tamano: int = 50,
           actor: Usuarios = Depends(requiere('casos.ver')), db: Session = Depends(get_db)):
    """Tablero operativo (RF-022): por estado, responsable, país, origen y riesgo.

    Lo que devuelve depende del alcance del usuario (RNF-03): quien tiene «solo
    casos asignados» ve los suyos aunque no filtre por responsable."""
    total, filas = servicio.listar(db, actor=actor, estado=estado,
                                   responsable_id=responsable_id, pais_id=pais_id,
                                   fuente=fuente, sin_asignar=sin_asignar, sin_venta=sin_venta,
                                   incluir_finalizados=incluir_finalizados, texto=texto,
                                   pagina=pagina, tamano=tamano)
    return esq.PaginaCasos(total=total, pagina=pagina, tamano=tamano,
                           items=[_salida(db, c) for c in filas])


@router.get('/casos/resumen', response_model=list[esq.ResumenEstado])
def resumen(_: Usuarios = Depends(requiere('casos.ver')), db: Session = Depends(get_db)):
    return [esq.ResumenEstado(codigo=c, nombre=n, total=t) for c, n, t in servicio.resumen_por_estado(db)]


@router.post('/casos', response_model=esq.CasoDetalle, status_code=status.HTTP_201_CREATED)
def crear(datos: esq.CasoCrear, request: Request,
          actor: Usuarios = Depends(requiere('casos.crear')), db: Session = Depends(get_db)):
    caso = servicio.crear(db, actor, datos.model_dump(exclude_unset=True), ip=ip_cliente(request))
    return detalle(caso.id, actor, db)


@router.get('/casos/{caso_id}', response_model=esq.CasoDetalle)
def detalle(caso_id: int, actor: Usuarios = Depends(requiere('casos.ver')),
            db: Session = Depends(get_db)):
    c = servicio.obtener(db, caso_id, actor=actor)
    return esq.CasoDetalle(
        **_salida(db, c).model_dump(), pais_id=c.pais_id, tipo_visa_id=c.tipo_visa_id, modalidad_id=c.modalidad_id,
        sede_id=c.sede_id, negocio_id=c.negocio_id, etapa_saas=c.etapa_saas,
        resultado_fecha=c.resultado_fecha, resultado_nota=c.resultado_nota, creado_en=c.creado_en,
        citas=[esq.CitaSalida.model_validate(x, from_attributes=True) for x in servicio.citas_de(db, c.id)],
        checklist=[esq.ItemChecklist(item_id=i.id, codigo=i.codigo, nombre=i.nombre,
                                     obligatorio=i.obligatorio, cumplido=cumplido)
                   for i, cumplido in servicio.checklist_de(db, c)],
        estados_posibles=[esq.EstadoPosible(codigo=e.codigo, nombre=e.nombre)
                          for e in servicio.destinos_posibles(db, c)])


@router.patch('/casos/{caso_id}', response_model=esq.CasoDetalle)
def editar(caso_id: int, datos: esq.CasoEditar, request: Request,
           actor: Usuarios = Depends(requiere('casos.editar')), db: Session = Depends(get_db)):
    servicio.editar(db, actor, caso_id, datos.model_dump(exclude_unset=True), ip=ip_cliente(request))
    return detalle(caso_id, actor, db)


@router.post('/casos/{caso_id}/estado', response_model=esq.CasoDetalle)
def cambiar_estado(caso_id: int, datos: esq.CambioEstado, request: Request,
                   actor: Usuarios = Depends(requiere('casos.editar')), db: Session = Depends(get_db)):
    """Avanza el trámite respetando el orden de los estados (RF-023)."""
    if datos.forzar and 'casos.excepcion' not in permisos_de_rol(db, actor.rol_id):
        raise Prohibido('Saltarse el orden de los estados solo lo puede autorizar la administradora.',
                        codigo='sin_permiso')
    cambios = datos.cambios.model_dump(exclude_unset=True) if datos.cambios else {}
    if datos.resultado:
        cambios |= {'resultado': datos.resultado, 'resultado_fecha': datos.resultado_fecha}
    servicio.cambiar_estado(db, actor, caso_id, codigo_destino=datos.codigo_destino, motivo=datos.motivo,
                            cambios=cambios, forzar=datos.forzar, ip=ip_cliente(request))
    return detalle(caso_id, actor, db)


@router.post('/casos/{caso_id}/resultado', response_model=esq.CasoDetalle)
def registrar_resultado(caso_id: int, datos: esq.ResultadoEntrada, request: Request,
                        actor: Usuarios = Depends(requiere('casos.editar')), db: Session = Depends(get_db)):
    """RF-027. El resultado se registra aunque el trámite siga abierto: una visa
    negada puede tener pendiente la entrega del pasaporte (RN-06)."""
    servicio.registrar_resultado(db, actor, caso_id, resultado=datos.resultado, fecha=datos.fecha,
                                 nota=datos.nota, ip=ip_cliente(request))
    return detalle(caso_id, actor, db)


@router.get('/casos/{caso_id}/historial', response_model=list[esq.HistorialSalida])
def historial(caso_id: int, _: Usuarios = Depends(requiere('casos.ver')), db: Session = Depends(get_db)):
    """Cada cambio del trámite, con quién lo hizo. Solo crece (RF-028).

    Los códigos y los ids se traducen aquí, contra los catálogos, para que la
    pantalla no tenga que adivinar qué es «sede_id: — → 2»."""
    filas = servicio.historial_de(db, caso_id)
    return [esq.HistorialSalida(titulo=titulo, campo=h.campo, valor_anterior=h.valor_anterior,
                                valor_nuevo=h.valor_nuevo,
                                usuario=h.usuario.nombre if h.usuario else None,
                                observacion=h.observacion, ocurrido_en=h.ocurrido_en)
            for h, titulo in zip(filas, describir(db, filas))]


@router.post('/casos/{caso_id}/citas', response_model=esq.CitaSalida, status_code=status.HTTP_201_CREATED)
def agendar_cita(caso_id: int, datos: esq.CitaCrear, request: Request,
                 actor: Usuarios = Depends(requiere('casos.editar')), db: Session = Depends(get_db)):
    """RF-024. La hora se guarda con zona horaria y se muestra en la del usuario (RN-10)."""
    cita = servicio.agendar_cita(db, actor, caso_id, datos.model_dump(), ip=ip_cliente(request))
    return esq.CitaSalida.model_validate(cita, from_attributes=True)


@router.patch('/citas/{cita_id}', response_model=esq.CitaSalida)
def actualizar_cita(cita_id: int, datos: esq.CitaEditar, request: Request,
                    actor: Usuarios = Depends(requiere('casos.editar')), db: Session = Depends(get_db)):
    cita = servicio.actualizar_cita(db, actor, cita_id, datos.model_dump(exclude_unset=True),
                                    ip=ip_cliente(request))
    return esq.CitaSalida.model_validate(cita, from_attributes=True)


@router.post('/casos/{caso_id}/checklist/{item_id}', status_code=status.HTTP_204_NO_CONTENT)
def marcar_checklist(caso_id: int, item_id: int, datos: esq.MarcarItem, request: Request,
                     actor: Usuarios = Depends(requiere('casos.editar')), db: Session = Depends(get_db)):
    servicio.marcar_item(db, actor, caso_id, item_id, cumplido=datos.cumplido,
                         observacion=datos.observacion, ip=ip_cliente(request))
