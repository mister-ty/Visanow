from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.services import retencion as servicio

router = APIRouter(prefix='/datos-personales', tags=['datos personales'])


class EvaluacionSalida(BaseModel):
    cliente_id: int
    nombre: str
    puede_eliminarse: bool = Field(
        description='Falso cuando hay ventas o pagos: ahí se anonimiza, no se borra')
    personas: int
    ventas: int
    pagos: int
    tramites: int
    razon: str
    advertencias: list[str] = []


class MotivoEntrada(BaseModel):
    motivo: str = Field(min_length=5, max_length=400,
                        description='Una solicitud del titular, el plazo cumplido, una orden')


class VencidoSalida(BaseModel):
    id: int
    nombre: str
    desde: date
    ultima_senal: date
    ventas: int


@router.get('/{cliente_id}/evaluar', response_model=EvaluacionSalida)
def evaluar(cliente_id: int, _: Usuarios = Depends(requiere('clientes.editar')),
            db: Session = Depends(get_db)):
    """Qué pasaría con los datos de este cliente, antes de tocar nada.

    Se consulta primero porque borrar no se puede deshacer, y quien atiende una
    solicitud tiene derecho a saber qué va a pasar.
    """
    return EvaluacionSalida(**vars(servicio.evaluar(db, cliente_id)))


@router.post('/{cliente_id}/anonimizar', response_model=EvaluacionSalida)
def anonimizar(cliente_id: int, datos: MotivoEntrada, request: Request,
               actor: Usuarios = Depends(requiere('clientes.eliminar')),
               db: Session = Depends(get_db)):
    """Quita lo que identifica a la persona y deja la contabilidad (RNF-09).

    Las ventas, los pagos y los trámites siguen ahí: son los libros de la
    empresa. Lo que desaparece es de quién eran.
    """
    return EvaluacionSalida(**vars(servicio.anonimizar(
        db, actor, cliente_id, datos.motivo, ip=ip_cliente(request))))


@router.post('/{cliente_id}/eliminar', response_model=EvaluacionSalida)
def eliminar(cliente_id: int, datos: MotivoEntrada, request: Request,
             actor: Usuarios = Depends(requiere('clientes.eliminar')),
             db: Session = Depends(get_db)):
    """Borra todo rastro. Solo si no hay nada contable que conservar.

    Con ventas o pagos se niega: borrar la contabilidad no es un derecho del
    titular ni una facultad de la empresa.
    """
    return EvaluacionSalida(**vars(servicio.eliminar(
        db, actor, cliente_id, datos.motivo, ip=ip_cliente(request))))


@router.get('/vencidos', response_model=list[VencidoSalida])
def vencidos(anios: int = servicio.ANIOS_DE_CONSERVACION,
             _: Usuarios = Depends(requiere('clientes.editar')),
             db: Session = Depends(get_db)):
    """Quiénes pasaron el plazo de conservación, para revisarlos.

    No se depura solo: un automatismo que borra datos de personas es el que un
    día se lleva lo que no debía, y acá lo que se pierde no se recupera.
    """
    return [VencidoSalida(**v) for v in servicio.vencidos(db, anios)]
