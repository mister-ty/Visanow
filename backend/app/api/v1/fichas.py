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
                                                    'DS-160, n.º de solicitud del SaaS o '
                                                    'referencia de pago'),
           actor: Usuarios = Depends(requiere('clientes.ver')), db: Session = Depends(get_db)):
    """Una sola caja de búsqueda para todo el sistema (RF-029).

    Quién busca va al servicio, porque la respuesta depende de eso: el alcance
    del usuario y sus permisos deciden qué trámites y qué pagos puede encontrar
    (RNF-03).
    """
    return [esq.ResultadoBusqueda(**r.__dict__)
            for r in fichas.buscar_global(db, q, actor=actor)]


@router.get('/clientes/{cliente_id}/ficha', response_model=esq.Ficha360)
def ficha_360(cliente_id: int, actor: Usuarios = Depends(requiere('clientes.ver')),
              db: Session = Depends(get_db)):
    """RF-005: todo lo del cliente en una sola pantalla.

    Las nueve cosas que pide el requisito: oportunidades, ventas, trámites,
    pagos, saldo, tareas, alertas, documentos y cronología. Antes había dos, y
    lo demás estaba repartido entre siete pantallas distintas.
    """
    from app.api.v1.clientes import detalle as detalle_cliente
    from app.api.v1.casos import _salida as caso_salida

    cliente = personas.obtener(db, cliente_id)
    puede = permisos_de_rol(db, actor.rol_id)

    # Cada bloque con SU permiso. La ficha responde todo junto, asi que
    # mezclarlos seria entregarle a operaciones los montos que la administradora
    # dijo el 29/09 que no debe ver. Y el campo `ve_*` existe para que la
    # pantalla distinga «no hay» de «no le corresponde»: confundirlos hace creer
    # que un cliente no tiene ventas cuando lo que pasa es que no se le muestran.
    ve_tramites = 'casos.ver' in puede
    ve_oportunidades = 'oportunidades.ver' in puede
    ve_montos = 'pagos.ver' in puede
    ve_al_dia = ve_montos or 'pagos.estado' in puede
    ve_ventas = 'negocios.ver' in puede
    ve_trabajo = 'alertas.ver' in puede
    ve_reservados = 'solicitantes.reservado' in puede

    tramites = fichas.tramites_de(db, cliente_id) if ve_tramites else []
    citas = fichas.proximas_citas(db, cliente_id) if ve_tramites else []
    personas_totales = len(fichas.solicitantes_ids(db, cliente_id))
    ahora = datetime.now(timezone.utc)

    ventas = fichas.ventas_de(db, cliente_id) if ve_ventas else []
    dinero = esq.DineroEnFicha(
        ve_montos=ve_montos,
        al_dia=fichas.esta_al_dia(db, cliente_id) if ve_al_dia else None,
        ventas=[esq.VentaEnFicha(**v) for v in ventas] if ve_ventas else [],
        pagos=[esq.PagoEnFicha(**p) for p in fichas.pagos_de(db, cliente_id)] if ve_montos else [],
        total_pactado=sum(v['valor_pactado'] for v in ventas) if ve_montos else None,
        total_pagado=sum(v['pagado'] for v in ventas) if ve_montos else None,
        saldo=sum(v['saldo'] for v in ventas) if ve_montos else None)
    # Sin permiso de montos, la venta se ve pero sin cifras: saber que el
    # cliente compro el premium no es saber cuanto pago.
    if ve_ventas and not ve_montos:
        dinero.ventas = [v.model_copy(update={'valor_pactado': 0, 'pagado': 0, 'saldo': 0})
                         for v in dinero.ventas]

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
        oportunidades=[esq.OportunidadEnFicha(**o)
                       for o in fichas.oportunidades_de(db, cliente_id)] if ve_oportunidades else [],
        dinero=dinero,
        tareas=[esq.TareaEnFicha(**t) for t in fichas.tareas_de(db, cliente_id)] if ve_trabajo else [],
        alertas=[esq.AlertaEnFicha(**a) for a in fichas.alertas_de(db, cliente_id)] if ve_trabajo else [],
        documentos=[esq.DocumentoEnFicha(**d) for d in
                    fichas.documentos_de(db, cliente_id, ve_reservados=ve_reservados)],
        ve_tramites=ve_tramites,
        ve_oportunidades=ve_oportunidades,
        ve_trabajo=ve_trabajo)


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
