"""Casos de visa: alta, asignación, citas, estados, checklist e historial
(RF-020 a RF-028, RN-04, RN-05, RN-06).

Un caso es el trámite de **una persona**. La familia compra junta y paga junto,
pero cada quien tiene su pasaporte, su DS-160 y su resultado (decisión D-02).

Las reglas que este servicio hace cumplir, y que hoy ningún Excel puede:

- Los estados no se saltan: solo se avanza por las transiciones definidas en la
  base. Saltárselas exige permiso de administradora y un motivo, y queda como
  excepción en el historial (RF-023).
- Antes de mandar a alguien a la entrevista, el checklist obligatorio tiene que
  estar completo (RF-025, RN-05).
- Un caso activo no puede quedar sin responsable ni sin próxima acción (RN-04).
- El resultado consular y el cierre del servicio son cosas distintas: una visa
  negada puede quedar perfectamente finalizada (RN-06).
- Cada cambio queda en el historial, que solo crece (RF-028, RN-08).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import Conflicto, Invalido, NoEncontrado, Prohibido
from app.models.esquema import (Casos, CasosChecklist, CasosHistorial, ChecklistItems, Checklists,
                                Citas, EstadosOperativos, Solicitantes, TransicionesOperativas, Usuarios)
from app.services.auditoria import auditar

ESTADO_INICIAL = 'registrado'
DIAS_RIESGO_MEDIO, DIAS_RIESGO_ALTO = 3, 5
RESULTADOS = ('aprobada', 'negada', 'proceso_administrativo', 'cancelado', 'no_continuo')

CAMPOS_CASO = ('pais_id', 'tipo_visa_id', 'modalidad_id', 'sede_id', 'responsable_id', 'negocio_id',
               'proxima_accion', 'proxima_accion_fecha', 'id_externo', 'fuente')


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _historial(db: Session, caso_id: int, campo: str, anterior, nuevo, actor_id: int | None,
               observacion: str | None = None) -> None:
    """El historial solo se inserta: nunca se actualiza ni se borra (RN-08)."""
    db.add(CasosHistorial(caso_id=caso_id, campo=campo,
                          valor_anterior=None if anterior is None else str(anterior),
                          valor_nuevo=None if nuevo is None else str(nuevo),
                          usuario_id=actor_id, observacion=observacion))


def obtener(db: Session, caso_id: int) -> Casos:
    caso = db.get(Casos, caso_id, options=[selectinload(Casos.solicitante), selectinload(Casos.estado)])
    if caso is None:
        raise NoEncontrado('El trámite no existe.')
    return caso


def _estado(db: Session, codigo: str) -> EstadosOperativos:
    estado = db.scalar(select(EstadosOperativos).where(EstadosOperativos.codigo == codigo))
    if estado is None:
        raise Invalido(f'El estado «{codigo}» no existe.')
    return estado


def dias_sin_movimiento(caso: Casos) -> int:
    return (_ahora() - caso.ultima_actividad_en).days


def riesgo(caso: Casos) -> str:
    """RF-022. Un caso final no corre riesgo por quedarse quieto."""
    if caso.estado.es_final:
        return 'ninguno'
    dias = dias_sin_movimiento(caso)
    return 'alto' if dias >= DIAS_RIESGO_ALTO else 'medio' if dias >= DIAS_RIESGO_MEDIO else 'bajo'


# --------------------------------------------------------------------- alta

def crear(db: Session, actor: Usuarios, datos: dict, ip: str | None = None) -> Casos:
    solicitante = db.get(Solicitantes, datos.get('solicitante_id'))
    if solicitante is None:
        raise NoEncontrado('El solicitante no existe.')
    if not datos.get('pais_id'):
        raise Invalido('Falta el país del trámite.')

    fuente = datos.get('fuente') or ('saas' if datos.get('id_externo') else 'manual')
    caso = Casos(solicitante_id=solicitante.id, estado=_estado(db, ESTADO_INICIAL), fuente=fuente,
                 ultima_actividad_en=_ahora(),
                 **{k: v for k, v in datos.items() if k in CAMPOS_CASO and k != 'fuente'})
    db.add(caso)
    db.flush()
    _historial(db, caso.id, 'creado', None, ESTADO_INICIAL, actor.id,
               f'Trámite creado ({fuente}) para {solicitante.nombre}')
    auditar(db, operacion='insert', entidad='casos', usuario_id=actor.id, entidad_id=caso.id,
            despues={'solicitante_id': solicitante.id, 'fuente': fuente}, ip=ip)
    db.commit()
    return caso


def editar(db: Session, actor: Usuarios, caso_id: int, cambios: dict, ip: str | None = None) -> Casos:
    """Cambios de datos del caso (responsable, sede, tipo de visa, próxima acción).
    El estado no se cambia por aquí: tiene sus propias reglas."""
    caso = obtener(db, caso_id)
    for campo, valor in cambios.items():
        if campo not in CAMPOS_CASO:
            continue
        anterior = getattr(caso, campo)
        if anterior != valor:
            setattr(caso, campo, valor)
            _historial(db, caso.id, campo, anterior, valor, actor.id)
    caso.ultima_actividad_en = _ahora()
    auditar(db, operacion='update', entidad='casos', usuario_id=actor.id, entidad_id=caso.id,
            despues=cambios, ip=ip)
    db.commit()
    return caso


# ------------------------------------------------------------------ tablero

def listar(db: Session, *, estado: str | None = None, responsable_id: int | None = None,
           pais_id: int | None = None, fuente: str | None = None, sin_asignar: bool = False,
           sin_venta: bool = False, incluir_finalizados: bool = False,
           texto: str | None = None, pagina: int = 1, tamano: int = 50) -> tuple[int, list[Casos]]:
    consulta: Select = (select(Casos)
                        .join(EstadosOperativos, EstadosOperativos.id == Casos.estado_id)
                        .join(Solicitantes, Solicitantes.id == Casos.solicitante_id)
                        .options(selectinload(Casos.solicitante), selectinload(Casos.estado),
                                 selectinload(Casos.responsable), selectinload(Casos.pais)))
    if not incluir_finalizados:
        consulta = consulta.where(EstadosOperativos.es_final.is_(False))
    if estado:
        consulta = consulta.where(EstadosOperativos.codigo == estado)
    if responsable_id:
        consulta = consulta.where(Casos.responsable_id == responsable_id)
    if sin_asignar:
        consulta = consulta.where(Casos.responsable_id.is_(None))
    if sin_venta:
        consulta = consulta.where(Casos.negocio_id.is_(None))
    if pais_id:
        consulta = consulta.where(Casos.pais_id == pais_id)
    if fuente:
        consulta = consulta.where(Casos.fuente == fuente)
    if texto := (texto or '').strip():
        consulta = consulta.where(or_(
            Solicitantes.nombre_busqueda.like(func.lower(func.sin_tildes(f'%{texto}%'))),
            Casos.id_externo == texto))

    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    pagina, tamano = max(1, pagina), min(max(1, tamano), 200)
    filas = db.scalars(consulta.order_by(Casos.ultima_actividad_en)
                       .offset((pagina - 1) * tamano).limit(tamano)).unique().all()
    return total, list(filas)


def resumen_por_estado(db: Session) -> list[tuple[str, str, int]]:
    """Para las columnas del tablero: cuántos casos activos hay en cada estado."""
    filas = db.execute(
        select(EstadosOperativos.codigo, EstadosOperativos.nombre, func.count(Casos.id))
        .join(Casos, Casos.estado_id == EstadosOperativos.id, isouter=True)
        .where(EstadosOperativos.activo.is_(True), EstadosOperativos.es_final.is_(False))
        .group_by(EstadosOperativos.codigo, EstadosOperativos.nombre, EstadosOperativos.orden)
        .order_by(EstadosOperativos.orden)).all()
    return [(c, n, t) for c, n, t in filas]


# ------------------------------------------------------- máquina de estados

def destinos_posibles(db: Session, caso: Casos) -> list[EstadosOperativos]:
    return list(db.scalars(
        select(EstadosOperativos)
        .join(TransicionesOperativas, TransicionesOperativas.estado_destino_id == EstadosOperativos.id)
        .where(TransicionesOperativas.estado_origen_id == caso.estado_id,
               EstadosOperativos.activo.is_(True))
        .order_by(EstadosOperativos.orden)))


def _validar_campos(db: Session, caso: Casos, exigidos: list[str]) -> None:
    faltan = []
    for campo in exigidos:
        if campo == 'cita_fecha':
            # No es una columna: significa que tiene que haber una cita agendada
            hay = db.scalar(select(func.count()).select_from(Citas)
                            .where(Citas.caso_id == caso.id, Citas.estado != 'cancelada'))
            if not hay:
                faltan.append('una cita agendada')
        elif not getattr(caso, campo, None):
            faltan.append(campo.replace('_id', '').replace('_', ' '))
    if faltan:
        raise Invalido('Para avanzar falta registrar: ' + ', '.join(faltan), codigo='faltan_campos')


def _validar_checklist(db: Session, caso: Casos) -> None:
    pendientes = [i.nombre for i, cumplido in checklist_de(db, caso) if i.obligatorio and not cumplido]
    if pendientes:
        raise Invalido('El checklist obligatorio está incompleto: ' + ', '.join(pendientes),
                       codigo='checklist_incompleto')


def cambiar_estado(db: Session, actor: Usuarios, caso_id: int, *, codigo_destino: str,
                   motivo: str | None = None, cambios: dict | None = None, forzar: bool = False,
                   ip: str | None = None) -> Casos:
    caso = obtener(db, caso_id)
    origen, destino = caso.estado, _estado(db, codigo_destino)
    if origen.id == destino.id:
        raise Invalido('El trámite ya está en ese estado.')

    # Los datos que llegan con el cambio se aplican antes de validar: así se puede
    # registrar el resultado y pasar a «con resultado» en un solo paso.
    for campo, valor in (cambios or {}).items():
        if campo in CAMPOS_CASO or campo in ('resultado', 'resultado_fecha', 'resultado_nota'):
            anterior = getattr(caso, campo)
            if anterior != valor:
                setattr(caso, campo, valor)
                _historial(db, caso.id, campo, anterior, valor, actor.id)

    transicion = db.get(TransicionesOperativas, (origen.id, destino.id))
    if transicion is None:
        if not forzar:
            permitidos = ', '.join(e.nombre for e in destinos_posibles(db, caso)) or 'ninguno'
            raise Conflicto(f'No se puede pasar de «{origen.nombre}» a «{destino.nombre}». '
                            f'Desde aquí se puede ir a: {permitidos}.', codigo='transicion_no_permitida')
        if not motivo:
            raise Invalido('Saltarse el orden de los estados exige un motivo.', codigo='falta_motivo')
    else:
        _validar_campos(db, caso, list(transicion.campos_obligatorios or []))
        if transicion.requiere_checklist:
            _validar_checklist(db, caso)

    if destino.requiere_motivo and not motivo:
        raise Invalido(f'Pasar a «{destino.nombre}» exige un motivo.', codigo='falta_motivo')

    # RN-06: el resultado consular no es lo mismo que terminar el servicio, pero
    # no se puede cerrar un trámite sin saber en qué quedó.
    if destino.es_final and destino.codigo == 'finalizado' and not caso.resultado:
        raise Invalido('Para finalizar hay que registrar el resultado (aprobada, negada, proceso '
                       'administrativo, cancelado o no continuó).', codigo='falta_resultado')
    # RN-04: un caso que sigue abierto necesita quién lo mueve y qué sigue
    if not destino.es_final:
        if not caso.responsable_id:
            raise Invalido('Asigne un responsable antes de mover el trámite.', codigo='falta_responsable')
        if not caso.proxima_accion:
            raise Invalido('Escriba cuál es la próxima acción.', codigo='falta_proxima_accion')

    # Se asigna el objeto, no solo el id: si no, la relación ya cargada sigue
    # apuntando al estado anterior y la respuesta devolvería el estado viejo.
    caso.estado = destino
    caso.ultima_actividad_en = _ahora()
    _historial(db, caso.id, 'excepcion' if transicion is None else 'estado',
               origen.codigo, destino.codigo, actor.id, motivo)
    auditar(db, operacion='update', entidad='casos', usuario_id=actor.id, entidad_id=caso.id,
            antes={'estado': origen.codigo},
            despues={'estado': destino.codigo, 'motivo': motivo, 'excepcion': transicion is None}, ip=ip)
    db.commit()
    return caso


def registrar_resultado(db: Session, actor: Usuarios, caso_id: int, *, resultado: str,
                        fecha: date | None = None, nota: str | None = None,
                        ip: str | None = None) -> Casos:
    """RF-027. Queda registrado aunque el trámite siga abierto: una visa negada
    puede tener todavía pendiente la entrega del pasaporte (RN-06)."""
    if resultado not in RESULTADOS:
        raise Invalido(f'Resultado inválido. Opciones: {", ".join(RESULTADOS)}.')
    caso = obtener(db, caso_id)
    anterior = caso.resultado
    caso.resultado, caso.resultado_fecha, caso.resultado_nota = resultado, fecha or date.today(), nota
    caso.ultima_actividad_en = _ahora()
    _historial(db, caso.id, 'resultado', anterior, resultado, actor.id, nota)
    auditar(db, operacion='update', entidad='casos', usuario_id=actor.id, entidad_id=caso.id,
            antes={'resultado': anterior}, despues={'resultado': resultado}, ip=ip)
    db.commit()
    return caso


# --------------------------------------------------------------------- citas

def agendar_cita(db: Session, actor: Usuarios, caso_id: int, datos: dict, ip: str | None = None) -> Citas:
    caso = obtener(db, caso_id)
    cita = Citas(caso_id=caso.id, **datos)
    db.add(cita)
    db.flush()
    # Si el trámite todavía no tenía sede, la toma de la cita: es la misma sede
    # y pedirla dos veces solo hace perder tiempo.
    if cita.sede_id and not caso.sede_id:
        caso.sede_id = cita.sede_id
        _historial(db, caso.id, 'sede_id', None, cita.sede_id, actor.id, 'Tomada de la cita agendada')
    caso.ultima_actividad_en = _ahora()
    _historial(db, caso.id, f'cita_{cita.tipo}', None, str(cita.inicia_en), actor.id, datos.get('observaciones'))
    auditar(db, operacion='insert', entidad='citas', usuario_id=actor.id, entidad_id=cita.id,
            despues={'caso_id': caso.id, 'tipo': cita.tipo, 'inicia_en': cita.inicia_en.isoformat()}, ip=ip)
    db.commit()
    return cita


def actualizar_cita(db: Session, actor: Usuarios, cita_id: int, cambios: dict,
                    ip: str | None = None) -> Citas:
    cita = db.get(Citas, cita_id)
    if cita is None:
        raise NoEncontrado('La cita no existe.')
    for campo, valor in cambios.items():
        if campo in ('sede_id', 'inicia_en', 'zona_horaria', 'estado', 'observaciones'):
            anterior = getattr(cita, campo)
            if anterior != valor:
                setattr(cita, campo, valor)
                _historial(db, cita.caso_id, f'cita_{cita.tipo}_{campo}', anterior, valor, actor.id)
    auditar(db, operacion='update', entidad='citas', usuario_id=actor.id, entidad_id=cita.id,
            despues=cambios, ip=ip)
    db.commit()
    return cita


def citas_de(db: Session, caso_id: int) -> list[Citas]:
    return list(db.scalars(select(Citas).where(Citas.caso_id == caso_id).order_by(Citas.inicia_en)))


# ----------------------------------------------------------------- checklist

def checklist_de(db: Session, caso: Casos) -> list[tuple[ChecklistItems, bool]]:
    """Los documentos que aplican a este trámite, con lo que ya está cumplido.

    Se toma **el checklist más específico**, no todos los que encajan: el de
    «visa USA primera vez» manda sobre el de «renovación USA» y sobre el
    general. Si se acumularan, la persona vería «Pasaporte vigente» tres veces.
    """
    candidatos = db.scalars(select(Checklists).where(
        Checklists.activo.is_(True),
        or_(Checklists.pais_id.is_(None), Checklists.pais_id == caso.pais_id),
        or_(Checklists.tipo_visa_id.is_(None), Checklists.tipo_visa_id == caso.tipo_visa_id))).all()
    if not candidatos:
        return []
    precision = lambda c: (c.tipo_visa_id is not None) * 2 + (c.pais_id is not None)
    mejor = max(precision(c) for c in candidatos)
    aplicables = [c.id for c in candidatos if precision(c) == mejor]
    items = db.scalars(select(ChecklistItems).where(ChecklistItems.checklist_id.in_(aplicables))
                       .order_by(ChecklistItems.checklist_id, ChecklistItems.orden)).all()
    cumplidos = {c.item_id: c.cumplido for c in db.scalars(
        select(CasosChecklist).where(CasosChecklist.caso_id == caso.id))}
    return [(i, cumplidos.get(i.id, False)) for i in items]


def marcar_item(db: Session, actor: Usuarios, caso_id: int, item_id: int, *, cumplido: bool,
                observacion: str | None = None, ip: str | None = None) -> None:
    caso = obtener(db, caso_id)
    item = db.get(ChecklistItems, item_id)
    if item is None:
        raise NoEncontrado('El documento del checklist no existe.')
    fila = db.scalar(select(CasosChecklist).where(CasosChecklist.caso_id == caso.id,
                                                  CasosChecklist.item_id == item_id))
    if fila is None:
        fila = CasosChecklist(caso_id=caso.id, item_id=item_id)
        db.add(fila)
    fila.cumplido = cumplido
    fila.cumplido_en = _ahora() if cumplido else None
    fila.cumplido_por = actor.id if cumplido else None
    fila.observacion = observacion
    caso.ultima_actividad_en = _ahora()
    _historial(db, caso.id, f'checklist:{item.codigo}', None, 'cumplido' if cumplido else 'pendiente',
               actor.id, observacion)
    db.commit()


# ---------------------------------------------------------------- historial

def historial_de(db: Session, caso_id: int) -> list[CasosHistorial]:
    return list(db.scalars(select(CasosHistorial).where(CasosHistorial.caso_id == caso_id)
                           .options(selectinload(CasosHistorial.usuario))
                           .order_by(CasosHistorial.ocurrido_en.desc(), CasosHistorial.id.desc())))
