"""Clientes, grupos y solicitantes (RF-001, RF-003, RF-004).

Tres entidades distintas que en los Excel viven revueltas en una sola columna
«CLIENTE»:

- cliente: quien compra y paga. Puede comprar varias veces (RN-01).
- grupo: la familia o el grupo de viaje que hace el trámite junto. El SaaS los
  registra como una sola solicitud con un solo correo, y se cobra como una sola
  venta (respuesta de la administradora del 19/09).
- solicitante: cada persona que viaja. Tiene su propio pasaporte, su propio
  DS-160 y su propio resultado, aunque el pago sea del grupo (RF-004).

El pasaporte se guarda cifrado (RNF-04) y se busca por un índice ciego, que
permite encontrarlo sin descifrar la columna (RF-029). Verlo en claro queda
registrado en la auditoría, porque «acceso trazable» es justamente eso.
"""
from __future__ import annotations

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core import seguridad as seg
from app.core.errores import Conflicto, Invalido, NoEncontrado
from app.models.esquema import Clientes, Grupos, Solicitantes, Usuarios
from app.services.auditoria import auditar, instantanea

CAMPOS_CLIENTE = ('nombre', 'tipo_documento', 'numero_documento', 'telefono', 'email', 'ciudad',
                  'pais_id', 'canal_id', 'consentimiento', 'observaciones')
CAMPOS_SOLICITANTE = ('nombre', 'tipo_documento', 'numero_documento', 'fecha_nacimiento', 'nacionalidad',
                      'telefono', 'email', 'relacion_con_cliente', 'observaciones')


# ------------------------------------------------------------------ clientes

def _vivos() -> Select:
    return select(Clientes).where(Clientes.fusionado_en_id.is_(None))


def obtener(db: Session, cliente_id: int) -> Clientes:
    cliente = db.get(Clientes, cliente_id)
    if cliente is None:
        raise NoEncontrado('El cliente no existe.')
    if cliente.fusionado_en_id:
        raise Conflicto(f'Esta ficha se fusionó en otra (cliente {cliente.fusionado_en_id}).',
                        codigo='ficha_fusionada')
    return cliente


def listar(db: Session, *, texto_busqueda: str | None = None, incluir_archivados: bool = False,
           pagina: int = 1, tamano: int = 25) -> tuple[int, list[Clientes]]:
    """Búsqueda por nombre (sin importar tildes ni mayúsculas), documento,
    teléfono en cualquier formato o correo."""
    consulta = _vivos()
    if not incluir_archivados:
        consulta = consulta.where(Clientes.archivado.is_(False))
    if texto := (texto_busqueda or '').strip():
        digitos = ''.join(ch for ch in texto if ch.isdigit())
        condiciones = [text('clientes.nombre_busqueda like lower(sin_tildes(:patron))')
                       .bindparams(patron=f'%{texto}%')]
        if digitos:
            condiciones.append(Clientes.numero_documento == digitos)
            if len(digitos) >= 7:
                condiciones.append(text('clientes.telefono_normalizado = :tel')
                                   .bindparams(tel=digitos[-10:]))
        if '@' in texto:
            condiciones.append(Clientes.email == texto)
        consulta = consulta.where(or_(*condiciones))

    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    pagina, tamano = max(1, pagina), min(max(1, tamano), 100)
    filas = db.scalars(consulta.order_by(Clientes.nombre)
                       .offset((pagina - 1) * tamano).limit(tamano)).all()
    return total, list(filas)


def crear(db: Session, actor: Usuarios, datos: dict, ip: str | None = None) -> Clientes:
    cliente = Clientes(creado_por=actor.id, **{k: v for k, v in datos.items() if k in CAMPOS_CLIENTE})
    if cliente.consentimiento:
        cliente.consentimiento_fecha = func.now()
    db.add(cliente)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        # El índice único de documento es la última barrera: la advertencia de
        # duplicados (RF-002) ya se muestra antes, al escribir los datos.
        raise Conflicto('Ya existe un cliente con ese número de documento.', codigo='documento_duplicado')
    auditar(db, operacion='insert', entidad='clientes', usuario_id=actor.id, entidad_id=cliente.id,
            despues=instantanea(cliente), ip=ip)
    db.commit()
    return cliente


def editar(db: Session, actor: Usuarios, cliente_id: int, cambios: dict, ip: str | None = None) -> Clientes:
    cliente = obtener(db, cliente_id)
    antes = instantanea(cliente)
    for campo, valor in cambios.items():
        if campo in CAMPOS_CLIENTE:
            setattr(cliente, campo, valor)
    if cambios.get('consentimiento') and not antes.get('consentimiento'):
        cliente.consentimiento_fecha = func.now()
    cliente.actualizado_en = func.now()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflicto('Ya existe un cliente con ese número de documento.', codigo='documento_duplicado')
    auditar(db, operacion='update', entidad='clientes', usuario_id=actor.id, entidad_id=cliente.id,
            antes=antes, despues=instantanea(cliente), ip=ip)
    db.commit()
    return cliente


def archivar(db: Session, actor: Usuarios, cliente_id: int, archivar_: bool,
             ip: str | None = None) -> Clientes:
    """Archivar no borra: la ficha sale de las listas pero conserva su historia."""
    cliente = obtener(db, cliente_id)
    cliente.archivado = archivar_
    auditar(db, operacion='update', entidad='clientes', usuario_id=actor.id, entidad_id=cliente.id,
            antes={'archivado': not archivar_}, despues={'archivado': archivar_}, ip=ip)
    db.commit()
    return cliente


# -------------------------------------------------------------------- grupos

def crear_grupo(db: Session, actor: Usuarios, *, nombre: str, cliente_contacto_id: int,
                observaciones: str | None = None, ip: str | None = None) -> Grupos:
    obtener(db, cliente_contacto_id)      # valida que el contacto exista y no esté fusionado
    grupo = Grupos(nombre=nombre.strip(), cliente_contacto_id=cliente_contacto_id,
                   observaciones=observaciones)
    db.add(grupo)
    db.flush()
    auditar(db, operacion='insert', entidad='grupos', usuario_id=actor.id, entidad_id=grupo.id,
            despues=instantanea(grupo), ip=ip)
    db.commit()
    return grupo


def grupos_de(db: Session, cliente_id: int) -> list[Grupos]:
    return list(db.scalars(select(Grupos).where(Grupos.cliente_contacto_id == cliente_id)
                           .options(selectinload(Grupos.solicitantes)).order_by(Grupos.id)))


# --------------------------------------------------------------- solicitantes

def _cifrar_pasaporte(solicitante: Solicitantes, pasaporte: str | None) -> None:
    if pasaporte is None:
        return
    pasaporte = pasaporte.strip().upper()
    solicitante.pasaporte = seg.cifrar(pasaporte) if pasaporte else None
    solicitante.pasaporte_indice = seg.indice_ciego(pasaporte) if pasaporte else None


def pasaporte_enmascarado(solicitante: Solicitantes) -> str | None:
    """Lo que ve cualquiera: los últimos cuatro caracteres. El valor completo se
    pide aparte y esa consulta queda auditada."""
    if not solicitante.pasaporte:
        return None
    try:
        claro = seg.descifrar(solicitante.pasaporte)
    except ValueError:
        return '(no se pudo descifrar)'
    return '•' * max(0, len(claro) - 4) + claro[-4:]


def ver_pasaporte(db: Session, actor: Usuarios, solicitante_id: int, ip: str | None = None) -> str:
    solicitante = obtener_solicitante(db, solicitante_id)
    if not solicitante.pasaporte:
        raise NoEncontrado('El solicitante no tiene pasaporte registrado.')
    auditar(db, operacion='ver_pasaporte', entidad='solicitantes', usuario_id=actor.id,
            entidad_id=solicitante_id, ip=ip)
    db.commit()
    return seg.descifrar(solicitante.pasaporte)


def obtener_solicitante(db: Session, solicitante_id: int) -> Solicitantes:
    s = db.get(Solicitantes, solicitante_id)
    if s is None:
        raise NoEncontrado('El solicitante no existe.')
    return s


def crear_solicitante(db: Session, actor: Usuarios, datos: dict, ip: str | None = None) -> Solicitantes:
    """Cada persona que viaja. Debe colgar de un grupo o de un cliente: un
    solicitante suelto sería un trámite que no le pertenece a nadie."""
    grupo_id, cliente_id = datos.get('grupo_id'), datos.get('cliente_id')
    if not grupo_id and not cliente_id:
        raise Invalido('El solicitante debe pertenecer a un grupo o a un cliente.')
    if grupo_id and db.get(Grupos, grupo_id) is None:
        raise NoEncontrado('El grupo no existe.')
    if cliente_id:
        obtener(db, cliente_id)

    solicitante = Solicitantes(grupo_id=grupo_id, cliente_id=cliente_id,
                               **{k: v for k, v in datos.items() if k in CAMPOS_SOLICITANTE})
    _cifrar_pasaporte(solicitante, datos.get('pasaporte'))
    db.add(solicitante)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflicto('Ya hay un solicitante registrado con ese pasaporte.', codigo='pasaporte_duplicado')
    auditar(db, operacion='insert', entidad='solicitantes', usuario_id=actor.id, entidad_id=solicitante.id,
            despues=instantanea(solicitante), ip=ip)
    db.commit()
    return solicitante


def editar_solicitante(db: Session, actor: Usuarios, solicitante_id: int, cambios: dict,
                       ip: str | None = None) -> Solicitantes:
    solicitante = obtener_solicitante(db, solicitante_id)
    antes = instantanea(solicitante)
    for campo, valor in cambios.items():
        if campo in CAMPOS_SOLICITANTE:
            setattr(solicitante, campo, valor)
    if 'pasaporte' in cambios:
        _cifrar_pasaporte(solicitante, cambios['pasaporte'])
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflicto('Ya hay un solicitante registrado con ese pasaporte.', codigo='pasaporte_duplicado')
    auditar(db, operacion='update', entidad='solicitantes', usuario_id=actor.id, entidad_id=solicitante.id,
            antes=antes, despues=instantanea(solicitante), ip=ip)
    db.commit()
    return solicitante


def solicitantes_de(db: Session, *, cliente_id: int | None = None, grupo_id: int | None = None) -> list[Solicitantes]:
    consulta = select(Solicitantes).where(Solicitantes.fusionado_en_id.is_(None))
    if grupo_id:
        consulta = consulta.where(Solicitantes.grupo_id == grupo_id)
    elif cliente_id:
        # Los propios y los de sus grupos: la ficha 360° los muestra juntos
        grupos = select(Grupos.id).where(Grupos.cliente_contacto_id == cliente_id)
        consulta = consulta.where(or_(Solicitantes.cliente_id == cliente_id,
                                      Solicitantes.grupo_id.in_(grupos)))
    return list(db.scalars(consulta.order_by(Solicitantes.nombre)))


def buscar_por_pasaporte(db: Session, pasaporte: str) -> list[Solicitantes]:
    """Búsqueda exacta sobre la columna cifrada, usando el índice ciego (RF-029)."""
    return list(db.scalars(select(Solicitantes)
                           .where(Solicitantes.pasaporte_indice == seg.indice_ciego(pasaporte),
                                  Solicitantes.fusionado_en_id.is_(None))))
