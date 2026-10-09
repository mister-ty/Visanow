import datetime as dt

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Alertas, AlertasTipos, Tareas, Usuarios
from app.schemas import trabajo as esq
from app.services import alertas as serv_alertas
from app.services import tareas as serv_tareas

router = APIRouter(tags=['tareas y alertas'])


def _tarea(t: Tareas) -> esq.TareaSalida:
    ahora = dt.datetime.now(serv_tareas.BOGOTA)
    return esq.TareaSalida(
        id=t.id, titulo=t.titulo, descripcion=t.descripcion, estado=t.estado,
        prioridad=t.prioridad, vence_en=t.vence_en,
        vencida=bool(t.vence_en and t.vence_en < ahora and t.estado in serv_tareas.ABIERTAS),
        caso_id=t.caso_id, negocio_id=t.negocio_id, oportunidad_id=t.oportunidad_id,
        cliente_id=t.cliente_id, cliente=t.cliente.nombre if t.cliente else None,
        responsable_id=t.responsable_id,
        responsable=t.responsable.nombre if t.responsable else None,
        origen=t.origen, cerrada_en=t.cerrada_en, creado_en=t.creado_en)


def _alerta(a: Alertas) -> esq.AlertaSalida:
    return esq.AlertaSalida(
        id=a.id, tipo=a.tipo.codigo, tipo_nombre=a.tipo.nombre, severidad=a.tipo.severidad,
        mensaje=a.mensaje, estado=a.estado, caso_id=a.caso_id, negocio_id=a.negocio_id,
        oportunidad_id=a.oportunidad_id, cita_id=a.cita_id,
        destinatario_id=a.destinatario_id, vence_en=a.vence_en,
        pospuesta_hasta=a.pospuesta_hasta, generada_en=a.generada_en,
        resuelta_en=a.resuelta_en)


# ------------------------------------------------------------------- tareas

@router.post('/tareas', response_model=esq.TareaSalida, status_code=status.HTTP_201_CREATED)
def crear_tarea(datos: esq.TareaCrear, request: Request,
                actor: Usuarios = Depends(requiere('alertas.crear')),
                db: Session = Depends(get_db)):
    """Una tarea con responsable, vencimiento y prioridad (RF-060).

    Siempre cuelga de un cliente, una venta, una oportunidad o un trámite: una
    tarea suelta no se puede retomar tres semanas después.
    """
    return _tarea(serv_tareas.crear(db, actor, datos.model_dump(exclude_unset=True),
                                    ip=ip_cliente(request)))


@router.get('/tareas', response_model=esq.PaginaTareas)
def listar_tareas(responsable_id: int | None = None, estado: esq.EstadoTarea | None = None,
                  prioridad: esq.Prioridad | None = None, caso_id: int | None = None,
                  negocio_id: int | None = None, cliente_id: int | None = None,
                  solo_abiertas: bool = True, vencidas: bool = False,
                  pagina: int = 1, tamano: int = 50,
                  actor: Usuarios = Depends(requiere('alertas.ver')),
                  db: Session = Depends(get_db)):
    """Lo urgente arriba: primero por prioridad y después por vencimiento."""
    total, filas = serv_tareas.listar(
        db, actor=actor, responsable_id=responsable_id, estado=estado, prioridad=prioridad,
        caso_id=caso_id, negocio_id=negocio_id, cliente_id=cliente_id,
        solo_abiertas=solo_abiertas, vencidas=vencidas, pagina=pagina, tamano=tamano)
    return esq.PaginaTareas(total=total, pagina=pagina, tamano=tamano,
                            items=[_tarea(t) for t in filas])


@router.get('/tareas/resumen', response_model=esq.ResumenTareas)
def resumen_tareas(actor: Usuarios = Depends(requiere('alertas.ver')),
                   db: Session = Depends(get_db)):
    """Cuántas tiene encima quien pregunta."""
    return esq.ResumenTareas(**serv_tareas.resumen(db, actor))


@router.patch('/tareas/{tarea_id}', response_model=esq.TareaSalida)
def cambiar_tarea(tarea_id: int, cambios: esq.TareaCambiar, request: Request,
                  actor: Usuarios = Depends(requiere('alertas.editar')),
                  db: Session = Depends(get_db)):
    """Mueve estado, responsable, prioridad o vencimiento.

    Cerrarla deja la fecha de cierre: lo que se hizo y lo que se decidió no
    hacer son las dos mitades de la misma historia.
    """
    return _tarea(serv_tareas.cambiar(db, actor, tarea_id,
                                      cambios.model_dump(exclude_unset=True),
                                      ip=ip_cliente(request)))


# ------------------------------------------------------------------ alertas

@router.post('/alertas/generar', response_model=esq.GenerarSalida)
def generar(datos: esq.GenerarEntrada, request: Request,
            actor: Usuarios = Depends(requiere('alertas.crear')),
            db: Session = Depends(get_db)):
    """Recorre la matriz configurada y crea lo que falte (RF-061, RF-062).

    Se puede correr cada hora: la clave de deduplicación impide que la misma
    alerta aparezca sesenta veces, y una ya resuelta no vuelve a nacer.
    """
    return esq.GenerarSalida(**serv_alertas.generar(db, actor, codigos=datos.codigos,
                                                    ip=ip_cliente(request)))


@router.get('/alertas', response_model=esq.PaginaAlertas)
def bandeja(estado: esq.EstadoAlerta | None = None, severidad: esq.Severidad | None = None,
            solo_abiertas: bool = True, pagina: int = 1, tamano: int = 50,
            actor: Usuarios = Depends(requiere('alertas.ver')),
            db: Session = Depends(get_db)):
    """La bandeja, lo grave primero. Una pospuesta vuelve al cumplirse su plazo."""
    total, filas = serv_alertas.bandeja(db, actor=actor, estado=estado, severidad=severidad,
                                        solo_abiertas=solo_abiertas, pagina=pagina,
                                        tamano=tamano)
    return esq.PaginaAlertas(total=total, pagina=pagina, tamano=tamano,
                             items=[_alerta(a) for a in filas])


@router.get('/alertas/resumen', response_model=esq.ResumenAlertas)
def resumen_alertas(actor: Usuarios = Depends(requiere('alertas.ver')),
                    db: Session = Depends(get_db)):
    return esq.ResumenAlertas(**serv_alertas.resumen(db, actor))


@router.get('/alertas/tipos', response_model=list[esq.TipoAlertaSalida])
def tipos(_: Usuarios = Depends(requiere('alertas.ver')), db: Session = Depends(get_db)):
    """La matriz configurable (RF-062), con cuáles ya tienen regla."""
    return [esq.TipoAlertaSalida(
        id=t.id, codigo=t.codigo, nombre=t.nombre, entidad=t.entidad,
        anticipacion_valor=t.anticipacion_valor, anticipacion_unidad=t.anticipacion_unidad,
        repeticiones=list(t.repeticiones or []), severidad=t.severidad, canal=t.canal,
        activo=t.activo, tiene_regla=t.codigo in serv_alertas.REGLAS)
        for t in db.scalars(select(AlertasTipos).order_by(AlertasTipos.id))]


@router.patch('/alertas/{alerta_id}', response_model=esq.AlertaSalida)
def cambiar_alerta(alerta_id: int, datos: esq.CambiarAlerta, request: Request,
                   actor: Usuarios = Depends(requiere('alertas.editar')),
                   db: Session = Depends(get_db)):
    """Vista, resuelta o pospuesta (RF-061).

    Posponer exige hasta cuándo: una alerta pospuesta «para después» no vuelve
    nunca, y lo que no vuelve es lo mismo que no existió.
    """
    return _alerta(serv_alertas.cambiar_estado(db, actor, alerta_id, datos.estado,
                                               hasta=datos.hasta, ip=ip_cliente(request)))
