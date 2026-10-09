from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Importaciones, Usuarios
from app.schemas import saas as esq
from app.services import saas as serv

router = APIRouter(prefix='/saas', tags=['importación del SaaS'])


def _importacion(imp: Importaciones, filas=None) -> esq.ImportacionSalida:
    return esq.ImportacionSalida(
        id=imp.id, origen=imp.origen, archivo_nombre=imp.archivo_nombre,
        filas_totales=imp.filas_totales, nuevos=imp.nuevos, actualizados=imp.actualizados,
        sin_cambios=imp.sin_cambios, conflictos=imp.conflictos, rechazados=imp.rechazados,
        estado=imp.estado, iniciada_en=imp.iniciada_en, aplicada_en=imp.aplicada_en,
        filas=[esq.FilaSalida(fila_numero=f.fila_numero, id_externo=f.id_externo,
                              resultado=f.resultado, caso_id=f.caso_id, detalle=f.detalle)
               for f in (filas or [])])


@router.post('/previsualizar', response_model=esq.ImportacionSalida,
             status_code=status.HTTP_201_CREATED)
def previsualizar(datos: esq.PrevisualizarEntrada, request: Request,
                  actor: Usuarios = Depends(requiere('importacion.crear')),
                  db: Session = Depends(get_db)):
    """Clasifica el export sin tocar un solo trámite (RF-033).

    Devuelve cada solicitud con su veredicto: nueva, actualizada, sin cambio,
    en conflicto o rechazada. Nada cambia hasta que alguien aplique. Importar a
    ciegas sobre datos de clientes reales no se puede deshacer.
    """
    imp = serv.previsualizar(db, actor, [f.model_dump() for f in datos.filas],
                             archivo=datos.archivo, ip=ip_cliente(request))
    return _importacion(imp, serv.filas_de(db, imp.id))


@router.post('/importaciones/{importacion_id}/aplicar', response_model=esq.AplicarSalida)
def aplicar(importacion_id: int, request: Request,
            actor: Usuarios = Depends(requiere('importacion.crear')),
            db: Session = Depends(get_db)):
    """Ejecuta una previsualización ya vista (RF-032).

    Idempotente por el número de solicitud: volver a aplicar el mismo archivo no
    crea nada. Las filas «nuevo» no crean el trámite solas, porque el export no
    dice de forma confiable de qué persona es: se vinculan a mano.
    """
    return esq.AplicarSalida(**serv.aplicar(db, actor, importacion_id, ip=ip_cliente(request)))


@router.post('/importaciones/{importacion_id}/descartar', response_model=esq.ImportacionSalida)
def descartar(importacion_id: int, request: Request,
              actor: Usuarios = Depends(requiere('importacion.crear')),
              db: Session = Depends(get_db)):
    return _importacion(serv.descartar(db, actor, importacion_id, ip=ip_cliente(request)))


@router.get('/importaciones', response_model=list[esq.ImportacionSalida])
def listar(limite: int = 20, _: Usuarios = Depends(requiere('importacion.ver')),
           db: Session = Depends(get_db)):
    return [_importacion(i) for i in serv.importaciones(db, limite)]


@router.get('/importaciones/{importacion_id}', response_model=esq.ImportacionSalida)
def ver(importacion_id: int, resultado: esq.Resultado | None = None,
        _: Usuarios = Depends(requiere('importacion.ver')), db: Session = Depends(get_db)):
    from app.core.errores import NoEncontrado
    imp = db.get(Importaciones, importacion_id)
    if imp is None:
        raise NoEncontrado('La importación no existe.')
    return _importacion(imp, serv.filas_de(db, importacion_id, resultado))


@router.post('/vincular', response_model=esq.CandidatoSalida)
def vincular(datos: esq.VincularEntrada, request: Request,
             actor: Usuarios = Depends(requiere('importacion.crear')),
             db: Session = Depends(get_db)):
    """Le pone a un trámite existente su número de solicitud (RF-036).

    Es el camino de las filas «nuevo»: una persona reconoce de quién es y lo
    amarra. De ahí en adelante las importaciones lo actualizan solas.
    """
    caso = serv.vincular(db, actor, datos.caso_id, datos.numero_solicitud,
                         ip=ip_cliente(request))
    return esq.CandidatoSalida(caso_id=caso.id,
                               solicitante=caso.solicitante.nombre if caso.solicitante else '',
                               fuente=caso.fuente)


@router.get('/candidatos', response_model=list[esq.CandidatoSalida])
def candidatos(numero_solicitud: str, nombre: str | None = None, limite: int = 10,
               _: Usuarios = Depends(requiere('importacion.ver')),
               db: Session = Depends(get_db)):
    """Trámites que podrían ser esa solicitud. Sugiere; no decide."""
    return [esq.CandidatoSalida(**c) for c in serv.candidatos(db, numero_solicitud, nombre,
                                                              limite)]


@router.get('/estado', response_model=esq.EstadoSincronizacion)
def estado(_: Usuarios = Depends(requiere('importacion.ver')), db: Session = Depends(get_db)):
    """Cuándo fue la última vez que esto funcionó (RF-035)."""
    return esq.EstadoSincronizacion(**serv.estado(db))


@router.get('/conflictos', response_model=list[esq.ConflictoSalida])
def conflictos(_: Usuarios = Depends(requiere('importacion.ver')),
               db: Session = Depends(get_db)):
    """Lo que el sistema no decide solo: dos valores distintos para un campo."""
    return [esq.ConflictoSalida(
        id=c.id, caso_id=c.caso_id, campo=c.campo, valor_visanow=c.valor_visanow,
        valor_saas=c.valor_saas, estado=c.estado, detectado_en=c.detectado_en)
        for c in serv.conflictos_abiertos(db)]


@router.post('/conflictos/{conflicto_id}/resolver', response_model=esq.ConflictoSalida)
def resolver(conflicto_id: int, datos: esq.ResolverEntrada, request: Request,
             actor: Usuarios = Depends(requiere('importacion.crear')),
             db: Session = Depends(get_db)):
    """Quién gana: lo de VisaNow, lo del SaaS, o se ignora."""
    c = serv.resolver_conflicto(db, actor, conflicto_id, datos.decision,
                                ip=ip_cliente(request))
    return esq.ConflictoSalida(
        id=c.id, caso_id=c.caso_id, campo=c.campo, valor_visanow=c.valor_visanow,
        valor_saas=c.valor_saas, estado=c.estado, detectado_en=c.detectado_en)
