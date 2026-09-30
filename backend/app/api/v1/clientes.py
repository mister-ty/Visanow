from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, requiere
from app.db.session import get_db
from app.models.esquema import Clientes, Solicitantes, Usuarios
from app.schemas import personas as esq
from app.services import duplicados, personas

router = APIRouter(tags=['clientes y solicitantes'])


def _cliente(c: Clientes) -> esq.ClienteSalida:
    return esq.ClienteSalida.model_validate(c, from_attributes=True)


def _solicitante(s: Solicitantes) -> esq.SolicitanteSalida:
    datos = esq.SolicitanteSalida.model_validate(s, from_attributes=True)
    return datos.model_copy(update={'pasaporte': personas.pasaporte_enmascarado(s)})


# ------------------------------------------------------------------ clientes

@router.get('/clientes', response_model=esq.PaginaClientes)
def listar(texto: str | None = Query(default=None, description='Nombre, documento, teléfono o correo'),
           archivados: bool = False, pagina: int = 1, tamano: int = 25,
           _: Usuarios = Depends(requiere('clientes.ver')), db: Session = Depends(get_db)):
    total, filas = personas.listar(db, texto_busqueda=texto, incluir_archivados=archivados,
                                   pagina=pagina, tamano=tamano)
    return esq.PaginaClientes(total=total, pagina=pagina, tamano=tamano,
                              items=[_cliente(c) for c in filas])


@router.post('/clientes', response_model=esq.ClienteDetalle, status_code=status.HTTP_201_CREATED)
def crear(datos: esq.ClienteCrear, request: Request,
          actor: Usuarios = Depends(requiere('clientes.crear')), db: Session = Depends(get_db)):
    cliente = personas.crear(db, actor, datos.model_dump(exclude_unset=True), ip=ip_cliente(request))
    return detalle(cliente.id, actor, db)


@router.post('/clientes/verificar-duplicados', response_model=list[esq.CoincidenciaSalida])
def verificar_duplicados(datos: esq.VerificarDuplicados,
                         _: Usuarios = Depends(requiere('clientes.ver')), db: Session = Depends(get_db)):
    """Se consulta antes de guardar: advierte, no bloquea (RF-002)."""
    encontradas = duplicados.buscar(db, **datos.model_dump())
    return [esq.CoincidenciaSalida(**{**c.__dict__, 'explicacion': c.explicacion}) for c in encontradas]


@router.get('/clientes/{cliente_id}', response_model=esq.ClienteDetalle)
def detalle(cliente_id: int, _: Usuarios = Depends(requiere('clientes.ver')),
            db: Session = Depends(get_db)):
    cliente = personas.obtener(db, cliente_id)
    grupos = [esq.GrupoSalida(id=g.id, nombre=g.nombre, cliente_contacto_id=g.cliente_contacto_id,
                              observaciones=g.observaciones,
                              solicitantes=[_solicitante(s) for s in g.solicitantes])
              for g in personas.grupos_de(db, cliente_id)]
    return esq.ClienteDetalle(
        **_cliente(cliente).model_dump(), pais_id=cliente.pais_id, canal_id=cliente.canal_id,
        observaciones=cliente.observaciones, consentimiento_fecha=cliente.consentimiento_fecha,
        grupos=grupos,
        solicitantes=[_solicitante(s) for s in personas.solicitantes_de(db, cliente_id=cliente_id)])


@router.patch('/clientes/{cliente_id}', response_model=esq.ClienteDetalle)
def editar(cliente_id: int, datos: esq.ClienteEditar, request: Request,
           actor: Usuarios = Depends(requiere('clientes.editar')), db: Session = Depends(get_db)):
    personas.editar(db, actor, cliente_id, datos.model_dump(exclude_unset=True), ip=ip_cliente(request))
    return detalle(cliente_id, actor, db)


@router.post('/clientes/{cliente_id}/archivar', response_model=esq.ClienteSalida)
def archivar(cliente_id: int, request: Request, archivado: bool = True,
             actor: Usuarios = Depends(requiere('clientes.editar')), db: Session = Depends(get_db)):
    return _cliente(personas.archivar(db, actor, cliente_id, archivado, ip=ip_cliente(request)))


@router.get('/clientes/{cliente_id}/duplicados', response_model=list[esq.CoincidenciaSalida])
def duplicados_de(cliente_id: int, _: Usuarios = Depends(requiere('clientes.ver')),
                  db: Session = Depends(get_db)):
    cliente = personas.obtener(db, cliente_id)
    # Se comparan los índices ciegos de los pasaportes de sus solicitantes:
    # no hace falta descifrarlos para saber si otra ficha tiene el mismo.
    indices = [s.pasaporte_indice for s in personas.solicitantes_de(db, cliente_id=cliente_id)
               if s.pasaporte_indice]
    encontradas = duplicados.buscar(
        db, nombre=cliente.nombre, tipo_documento=cliente.tipo_documento,
        numero_documento=cliente.numero_documento, telefono=cliente.telefono,
        email=cliente.email, indices_pasaporte=indices, excluir_id=cliente_id)
    return [esq.CoincidenciaSalida(**{**c.__dict__, 'explicacion': c.explicacion}) for c in encontradas]


@router.post('/clientes/{cliente_id}/fusionar', response_model=esq.FusionSalida)
def fusionar(cliente_id: int, datos: esq.FusionEntrada, request: Request,
             actor: Usuarios = Depends(requiere('clientes.eliminar')), db: Session = Depends(get_db)):
    """Une dos fichas. Exige el permiso de eliminar clientes, que hoy solo tiene
    la administradora: RF-002 pide que la fusión sea autorizada."""
    return esq.FusionSalida(**duplicados.fusionar(db, actor, cliente_id, datos.absorbido_id,
                                                  datos.criterio, ip=ip_cliente(request)))


# -------------------------------------------------------- grupos y solicitantes

@router.post('/grupos', response_model=esq.GrupoSalida, status_code=status.HTTP_201_CREATED)
def crear_grupo(datos: esq.GrupoCrear, request: Request,
                actor: Usuarios = Depends(requiere('solicitantes.crear')), db: Session = Depends(get_db)):
    g = personas.crear_grupo(db, actor, **datos.model_dump(), ip=ip_cliente(request))
    return esq.GrupoSalida(id=g.id, nombre=g.nombre, cliente_contacto_id=g.cliente_contacto_id,
                           observaciones=g.observaciones, solicitantes=[])


@router.get('/solicitantes', response_model=list[esq.SolicitanteSalida])
def listar_solicitantes(cliente_id: int | None = None, grupo_id: int | None = None,
                        _: Usuarios = Depends(requiere('solicitantes.ver')), db: Session = Depends(get_db)):
    return [_solicitante(s) for s in personas.solicitantes_de(db, cliente_id=cliente_id, grupo_id=grupo_id)]


@router.get('/solicitantes/buscar', response_model=list[esq.SolicitanteSalida])
def buscar_por_pasaporte(pasaporte: str = Query(min_length=4),
                         _: Usuarios = Depends(requiere('solicitantes.ver')),
                         db: Session = Depends(get_db)):
    """Búsqueda exacta por pasaporte sobre la columna cifrada (RF-029)."""
    return [_solicitante(s) for s in personas.buscar_por_pasaporte(db, pasaporte)]


@router.post('/solicitantes', response_model=esq.SolicitanteSalida, status_code=status.HTTP_201_CREATED)
def crear_solicitante(datos: esq.SolicitanteCrear, request: Request,
                      actor: Usuarios = Depends(requiere('solicitantes.crear')),
                      db: Session = Depends(get_db)):
    return _solicitante(personas.crear_solicitante(db, actor, datos.model_dump(exclude_unset=True),
                                                   ip=ip_cliente(request)))


@router.patch('/solicitantes/{solicitante_id}', response_model=esq.SolicitanteSalida)
def editar_solicitante(solicitante_id: int, datos: esq.SolicitanteEditar, request: Request,
                       actor: Usuarios = Depends(requiere('solicitantes.editar')),
                       db: Session = Depends(get_db)):
    return _solicitante(personas.editar_solicitante(db, actor, solicitante_id,
                                                    datos.model_dump(exclude_unset=True),
                                                    ip=ip_cliente(request)))


@router.get('/solicitantes/{solicitante_id}/pasaporte', response_model=esq.PasaporteSalida)
def ver_pasaporte(solicitante_id: int, request: Request,
                  actor: Usuarios = Depends(requiere('solicitantes.ver')), db: Session = Depends(get_db)):
    """Devuelve el pasaporte completo y deja constancia de quién lo consultó (RNF-04)."""
    return esq.PasaporteSalida(solicitante_id=solicitante_id,
                               pasaporte=personas.ver_pasaporte(db, actor, solicitante_id,
                                                                ip=ip_cliente(request)))
