from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.schemas import plantillas as esq
from app.services import plantillas as servicio

router = APIRouter(prefix='/plantillas', tags=['plantillas de mensajes'])


@router.get('/catalogo', response_model=esq.CatalogoPlantillas)
def catalogo(_: Usuarios = Depends(requiere('casos.ver'))):
    """Eventos y variables disponibles, para armar la plantilla sin adivinar nombres."""
    return esq.CatalogoPlantillas(
        eventos=[esq.EventoSalida(clave=k, nombre=v) for k, v in servicio.EVENTOS.items()],
        variables=[esq.VariableSalida(clave=k, descripcion=v) for k, v in servicio.VARIABLES.items()])


@router.get('', response_model=list[esq.PlantillaSalida])
def listar(evento: str | None = None,
           incluir_inactivas: bool = Query(default=False),
           actor: Usuarios = Depends(requiere('casos.ver')), db: Session = Depends(get_db)):
    return servicio.listar(db, evento=evento, solo_activas=not incluir_inactivas)


@router.post('', response_model=esq.PlantillaSalida, status_code=status.HTTP_201_CREATED)
def crear(datos: esq.PlantillaCrear, request: Request,
          actor: Usuarios = Depends(requiere('catalogos.editar')), db: Session = Depends(get_db)):
    return servicio.crear(db, actor, datos.model_dump(), ip=ip_cliente(request))


@router.patch('/{plantilla_id}', response_model=esq.PlantillaSalida)
def editar(plantilla_id: int, datos: esq.PlantillaEditar, request: Request,
           actor: Usuarios = Depends(requiere('catalogos.editar')), db: Session = Depends(get_db)):
    return servicio.editar(db, actor, plantilla_id, datos.model_dump(exclude_unset=True),
                           ip=ip_cliente(request))


@router.post('/{plantilla_id}/generar', response_model=esq.RenderSalida)
def generar(plantilla_id: int, datos: esq.RenderEntrada,
            actor: Usuarios = Depends(requiere('casos.ver')), db: Session = Depends(get_db)):
    """Llena la plantilla con los datos del trámite o la venta (RF-063).

    No envía nada: devuelve el texto para copiarlo o abrirlo en WhatsApp o correo.
    """
    return servicio.generar(db, actor, plantilla_id, caso_id=datos.caso_id,
                            negocio_id=datos.negocio_id)
