"""Detección y fusión de duplicados de clientes (RF-002, RN-08).

Por qué importa: en los archivos actuales hay 971 menciones de cliente para unas
570 personas reales. Si esos duplicados entran al sistema nuevo, el saldo de un
cliente queda repartido entre dos fichas y la cartera deja de cuadrar.

Cómo se decide la confianza. No todos los parecidos valen lo mismo, y el correo
es el caso claro: la administradora confirmó que **una familia se registra con un
solo correo**, así que dos personas con el mismo correo suelen ser padre e hijo,
no un duplicado. Marcarlo como duplicado alto llevaría a fusionar a dos personas
distintas, que es un daño peor que dejar un duplicado sin detectar.

Lo que de verdad separa un duplicado de un familiar es el **nombre de pila**:
los parientes comparten apellidos, teléfono y correo, pero no se llaman igual.
Por eso el nombre de pila se compara aparte y manda sobre las demás señales.

    alta   documento o pasaporte igual (son de una sola persona)
           mismo nombre de pila + (teléfono o correo igual, o nombre casi idéntico)
    media  mismo nombre de pila + nombre parecido
    baja   nombre de pila distinto: probablemente un familiar, no un duplicado
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text, update
from sqlalchemy.orm import Session

from app.core import seguridad as seg
from app.core.errores import Conflicto, Invalido, NoEncontrado
from app.models.esquema import (Actividades, Clientes, Documentos, Fusiones, Grupos,
                                MigracionFilas, Negocios, Oportunidades, Solicitantes, Tareas,
                                Usuarios)
from app.services.auditoria import auditar, instantanea

PARECIDO_MINIMO = 0.35      # por debajo de esto no se muestra
PARECIDO_ALTO = 0.80        # prácticamente el mismo nombre
PARECIDO_MEDIO = 0.55
PILA_MINIMA = 0.60          # por debajo, el nombre de pila es otro

ETIQUETAS = {
    'documento': 'mismo número de documento',
    'pasaporte': 'mismo pasaporte',
    'telefono': 'mismo teléfono',
    'email': 'mismo correo',
    'nombre': 'nombre parecido',
}


@dataclass
class Coincidencia:
    cliente_id: int
    nombre: str
    confianza: str
    criterios: list[str] = field(default_factory=list)
    parecido_nombre: float = 0.0
    archivado: bool = False
    posible_familiar: bool = False

    @property
    def explicacion(self) -> str:
        texto = ' · '.join(ETIQUETAS[c] for c in self.criterios)
        if self.posible_familiar:
            texto += ' — el nombre de pila es distinto: puede ser un familiar, no la misma persona'
        return texto


_CONSULTA = text("""
    select c.id, c.nombre, c.archivado,
           (cast(:documento as text) is not null
             and c.numero_documento = cast(:documento as text))                        as por_documento,
           (cast(:telefono as text) is not null
             and c.telefono_normalizado = cast(:telefono as text))                     as por_telefono,
           (cast(:email as citext) is not null and c.email = cast(:email as citext))   as por_email,
           coalesce(similarity(c.nombre_busqueda,
                               lower(sin_tildes(cast(:nombre as text)))), 0)           as parecido,
           coalesce(similarity(split_part(c.nombre_busqueda, ' ', 1),
                               split_part(lower(sin_tildes(cast(:nombre as text))), ' ', 1)), 0) as parecido_pila
    from clientes c
    where c.fusionado_en_id is null
      and (cast(:excluir as bigint) is null or c.id <> cast(:excluir as bigint))
      and ( c.numero_documento = cast(:documento as text)
         or c.telefono_normalizado = cast(:telefono as text)
         or c.email = cast(:email as citext)
         or c.nombre_busqueda % lower(sin_tildes(cast(:nombre as text))) )
    limit 50
""")


def _confianza(por_documento: bool, por_telefono: bool, por_email: bool,
               parecido: float, parecido_pila: float) -> str:
    # El documento identifica a una sola persona: no se comparte en familia
    if por_documento:
        return 'alta'
    # Nombre de pila distinto: comparten apellido, teléfono o correo, pero no son
    # la misma persona. Se avisa, sin proponer una fusión.
    if parecido_pila < PILA_MINIMA:
        return 'baja'
    if parecido >= PARECIDO_ALTO or por_telefono or por_email:
        return 'alta'
    return 'media' if parecido >= PARECIDO_MEDIO else 'baja'


def buscar(db: Session, *, nombre: str, tipo_documento: str | None = None,
           numero_documento: str | None = None, telefono: str | None = None,
           email: str | None = None, pasaporte: str | None = None,
           indices_pasaporte: list[str] | None = None,
           excluir_id: int | None = None) -> list[Coincidencia]:
    """Posibles duplicados de una persona. No bloquea nada: advierte (RF-002)."""
    telefono_normal = ''.join(ch for ch in (telefono or '') if ch.isdigit())[-10:] or None
    filas = db.execute(_CONSULTA, {
        'nombre': nombre or '', 'documento': (numero_documento or '').strip() or None,
        'telefono': telefono_normal, 'email': (email or '').strip().lower() or None,
        'excluir': excluir_id,
    }).mappings().all()

    encontradas: dict[int, Coincidencia] = {}
    for f in filas:
        criterios = [c for c, activo in (('documento', f['por_documento']), ('telefono', f['por_telefono']),
                                         ('email', f['por_email'])) if activo]
        if f['parecido'] >= PARECIDO_MINIMO:
            criterios.append('nombre')
        if not criterios:
            continue
        familiar = (f['parecido_pila'] < PILA_MINIMA
                    and (f['por_telefono'] or f['por_email'] or f['parecido'] >= PARECIDO_MINIMO)
                    and not f['por_documento'])
        encontradas[f['id']] = Coincidencia(
            cliente_id=f['id'], nombre=f['nombre'], archivado=f['archivado'],
            parecido_nombre=round(float(f['parecido']), 2), criterios=criterios, posible_familiar=familiar,
            confianza=_confianza(f['por_documento'], f['por_telefono'], f['por_email'],
                                 f['parecido'], f['parecido_pila']))

    # El pasaporte vive en los solicitantes y está cifrado: se busca por su
    # índice ciego, que permite la comparación exacta sin descifrar la columna.
    indices = list(indices_pasaporte or [])
    if pasaporte:
        indices.append(seg.indice_ciego(pasaporte))
    if indices:
        for cliente_id, nombre_cliente, archivado in db.execute(text("""
            select distinct c.id, c.nombre, c.archivado
            from solicitantes s
            join clientes c on c.id = coalesce(s.cliente_id,
                                               (select g.cliente_contacto_id from grupos g where g.id = s.grupo_id))
            where s.pasaporte_indice = any(cast(:indices as text[])) and s.fusionado_en_id is null
              and c.fusionado_en_id is null
              and (cast(:excluir as bigint) is null or c.id <> cast(:excluir as bigint))
        """), {'indices': indices, 'excluir': excluir_id}):
            c = encontradas.get(cliente_id) or Coincidencia(cliente_id=cliente_id, nombre=nombre_cliente,
                                                            confianza='alta', archivado=archivado)
            if 'pasaporte' not in c.criterios:
                c.criterios.insert(0, 'pasaporte')
            c.confianza, c.posible_familiar = 'alta', False
            encontradas[cliente_id] = c

    orden = {'alta': 0, 'media': 1, 'baja': 2}
    return sorted(encontradas.values(), key=lambda c: (orden[c.confianza], -c.parecido_nombre))


# --------------------------------------------------------------------- fusión

# Todo lo que apunta a un cliente. Si mañana aparece otra tabla con cliente_id y
# no entra a esta lista, la fusión dejaría registros apuntando a una ficha
# archivada: por eso la prueba de fusión compara esta lista contra las llaves
# foráneas reales de la base.
REFERENCIAS = [
    (Grupos, 'cliente_contacto_id'),
    (Solicitantes, 'cliente_id'),
    (Oportunidades, 'cliente_id'),
    (Oportunidades, 'referido_por_cliente_id'),
    (Negocios, 'cliente_id'),
    (Tareas, 'cliente_id'),
    # La traza de la migración también sigue a la ficha que queda: si no, el
    # registro «esta fila del Excel creó a este cliente» apuntaría a una ficha
    # archivada y se perdería de dónde salió el dato.
    (MigracionFilas, 'cliente_id'),
]
POLIMORFICAS = [Actividades, Documentos]

# Campos que se completan en la ficha que queda, si venían vacíos
COMPLETABLES = ('telefono', 'email', 'ciudad', 'pais_id', 'canal_id', 'observaciones')


def fusionar(db: Session, actor: Usuarios, conservado_id: int, absorbido_id: int,
             criterio: str, ip: str | None = None) -> dict:
    """Une dos fichas en una. Queda registro completo de lo absorbido (tabla
    fusiones, con copia íntegra) para poder reconstruir qué se unió y por qué."""
    if conservado_id == absorbido_id:
        raise Invalido('No se puede fusionar una ficha consigo misma.')
    conservado = db.get(Clientes, conservado_id)
    absorbido = db.get(Clientes, absorbido_id)
    if conservado is None or absorbido is None:
        raise NoEncontrado('Alguna de las dos fichas no existe.')
    for c in (conservado, absorbido):
        if c.fusionado_en_id is not None:
            raise Conflicto(f'La ficha de {c.nombre} ya fue fusionada en otra.', codigo='ya_fusionado')

    copia = instantanea(absorbido)
    movidos: dict[str, int] = {}

    # El documento se copia y se libera en la ficha absorbida: si quedara en las
    # dos, chocaría con el índice único de documento. Queda en la copia íntegra.
    if not conservado.numero_documento and absorbido.numero_documento:
        tipo, numero = absorbido.tipo_documento, absorbido.numero_documento
        absorbido.tipo_documento = absorbido.numero_documento = None
        db.flush()      # se libera primero: si el documento quedara un instante
                        # en las dos fichas, el índice único rechazaría el cambio
        conservado.tipo_documento, conservado.numero_documento = tipo, numero
    for campo in COMPLETABLES:
        if not getattr(conservado, campo) and getattr(absorbido, campo):
            setattr(conservado, campo, getattr(absorbido, campo))

    for modelo, columna in REFERENCIAS:
        resultado = db.execute(update(modelo).where(getattr(modelo, columna) == absorbido_id)
                               .values({columna: conservado_id}))
        if resultado.rowcount:
            movidos[modelo.__tablename__] = movidos.get(modelo.__tablename__, 0) + resultado.rowcount
    for modelo in POLIMORFICAS:
        resultado = db.execute(update(modelo)
                               .where(modelo.entidad == 'cliente', modelo.entidad_id == absorbido_id)
                               .values(entidad_id=conservado_id))
        if resultado.rowcount:
            movidos[modelo.__tablename__] = resultado.rowcount

    absorbido.fusionado_en_id = conservado_id
    absorbido.archivado = True
    db.add(Fusiones(entidad='cliente', id_conservado=conservado_id, id_absorbido=absorbido_id,
                    criterio=criterio, snapshot=copia, autorizado_por=actor.id))
    auditar(db, operacion='fusion', entidad='clientes', usuario_id=actor.id, entidad_id=conservado_id,
            antes={'absorbido_id': absorbido_id, 'nombre': absorbido.nombre},
            despues={'criterio': criterio, 'movidos': movidos}, ip=ip)
    db.commit()
    return {'conservado_id': conservado_id, 'absorbido_id': absorbido_id, 'movidos': movidos}
