"""Catálogos de solo lectura para llenar los desplegables de la aplicación.

Van todos en una sola llamada: son listas cortas que casi no cambian y así el
frontend las pide una vez. Se administran en /admin, no aquí.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import requiere
from app.db.session import get_db
from app.models.esquema import (Canales, EstadosComerciales, EstadosOperativos, Modalidades,
                                Paises, Sedes, Servicios, TiposVisa, Usuarios)

router = APIRouter(tags=['catálogos'])


class Opcion(BaseModel):
    id: int
    nombre: str
    codigo: str | None = None
    pais_id: int | None = None


class Catalogos(BaseModel):
    paises: list[Opcion]
    canales: list[Opcion]
    tipos_visa: list[Opcion]
    sedes: list[Opcion]
    modalidades: list[Opcion]
    servicios: list[Opcion]
    estados_operativos: list[Opcion]
    estados_comerciales: list[Opcion]


@router.get('/catalogos', response_model=Catalogos)
def catalogos(_: Usuarios = Depends(requiere('catalogos.ver')), db: Session = Depends(get_db)):
    def opciones(modelo, *, activos: bool = False, con_pais: bool = False, orden=None):
        consulta = select(modelo)
        if activos:
            consulta = consulta.where(modelo.activo.is_(True))
        return [Opcion(id=x.id, nombre=x.nombre, codigo=getattr(x, 'codigo', None),
                       pais_id=getattr(x, 'pais_id', None) if con_pais else None)
                for x in db.scalars(consulta.order_by(orden if orden is not None else modelo.nombre))]

    return Catalogos(
        paises=opciones(Paises),
        # Por dónde llegó el cliente. RF-001 lo pide en la ficha y era el único
        # campo suyo sin catálogo expuesto: la ficha guardaba el id y la pantalla
        # no tenía con qué convertirlo en un nombre.
        canales=opciones(Canales, activos=True),
        tipos_visa=opciones(TiposVisa, activos=True, con_pais=True),
        sedes=opciones(Sedes, con_pais=True),
        modalidades=opciones(Modalidades),
        servicios=opciones(Servicios, activos=True),
        estados_operativos=opciones(EstadosOperativos, activos=True, orden=EstadosOperativos.orden),
        estados_comerciales=opciones(EstadosComerciales, activos=True, orden=EstadosComerciales.orden),
    )
