"""Documentos adjuntos a un cliente, una persona, un trámite, una venta o un pago.

La tabla existía desde el núcleo y nadie escribía en ella: no había forma de
subir un comprobante de pago ni el soporte de un trámite. Esto lo abre (RNF-04,
RF-064).

**Lo que se sube queda cifrado en disco.** Un soporte de pago trae el nombre y
la cuenta de una persona; el pasaporte escaneado trae todo. Se cifra con la
misma llave que el número de DS-160, así que quien mire el disco —o un respaldo
perdido, o un disco dado de baja— no ve nada. El precio es el mismo y está
dicho: si `CIFRADO_LLAVE` se pierde, lo cifrado no se recupera.

**Y no se guarda en un disco que se borra.** Render en el plan gratuito tiene
sistema de archivos efímero: lo que se escriba ahí desaparece en el siguiente
despliegue. Subir el pasaporte de alguien a un disco así es perderlo sin que
nadie se entere hasta que haga falta. Por eso guardar archivos exige declarar
`ALMACENAMIENTO_RUTA` a propósito: donde hay volumen de verdad se declara y
funciona; donde no, se rechaza con el motivo, y los documentos *por enlace*
—una carpeta compartida, por ejemplo— siguen sirviendo mientras tanto.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import seguridad as seg
from app.core.config import ajustes
from app.core.errores import Conflicto, Invalido, NoEncontrado, Prohibido
from app.models.esquema import (
    Casos,
    Clientes,
    Documentos,
    Gastos,
    Negocios,
    Pagos,
    Solicitantes,
    Usuarios,
)
from app.services.auditoria import auditar
from app.services.usuarios import permisos_de_rol

#: 25 MB. Un pasaporte escaneado pesa dos o tres; un PDF del consulado, menos.
#: El tope existe para que una subida no se lleve el disco ni la memoria.
MAX_BYTES = 25 * 1024 * 1024

#: Qué se deja subir, por lo que el archivo ES y no por lo que dice su nombre.
#: Cambiarle la extensión a un ejecutable es lo primero que se intenta.
FIRMAS: tuple[tuple[bytes, str, str], ...] = (
    (b'%PDF-', 'application/pdf', 'pdf'),
    (b'\xff\xd8\xff', 'image/jpeg', 'jpg'),
    (b'\x89PNG\r\n\x1a\n', 'image/png', 'png'),
    (b'GIF87a', 'image/gif', 'gif'),
    (b'GIF89a', 'image/gif', 'gif'),
)

#: A qué puede ir pegado un documento, y qué permiso hace falta para verlo.
#: El trámite va aparte porque además tiene alcance (RNF-03).
ENTIDADES: dict[str, tuple[str, str, type]] = {
    'cliente': ('clientes.ver', 'clientes.editar', Clientes),
    'solicitante': ('solicitantes.ver', 'solicitantes.editar', Solicitantes),
    'caso': ('casos.ver', 'casos.editar', Casos),
    'negocio': ('negocios.ver', 'negocios.editar', Negocios),
    'pago': ('pagos.ver', 'pagos.editar', Pagos),
    'gasto': ('gastos.ver', 'gastos.editar', Gastos),
}

#: Un documento marcado como restringido no lo ve cualquiera que pueda ver la
#: ficha. Es para el pasaporte escaneado y el DS-160 impreso: cosas que
#: identifican a la persona por completo.
#:
#: NO sirve `solicitantes.ver` para esto: lo tienen los cinco roles, incluido el
#: comercial y el de solo lectura, asi que marcar un documento como reservado no
#: habria cambiado nada. Lo tienen administradora y operaciones, que son quienes
#: hacen el tramite.
PERMISO_RESTRINGIDO = 'solicitantes.reservado'


@dataclass
class Archivo:
    """Lo que llega de la petición, ya leído."""
    nombre: str
    contenido: bytes


def raiz() -> Path | None:
    """Dónde se guardan los archivos, o None si no se declaró."""
    ruta = ajustes().almacenamiento_ruta.strip()
    return Path(ruta) if ruta else None


def se_pueden_guardar_archivos() -> bool:
    return raiz() is not None


def _mime_real(contenido: bytes) -> tuple[str, str]:
    """Mira los primeros bytes. El nombre del archivo no es evidencia de nada."""
    for firma, mime, ext in FIRMAS:
        if contenido.startswith(firma):
            return mime, ext
    raise Invalido(
        'Solo se aceptan PDF, JPG, PNG y GIF. El archivo que subió no es ninguno '
        'de esos, aunque su nombre lo diga.', codigo='tipo_no_permitido')


def _puede(db: Session, actor: Usuarios, permiso: str) -> bool:
    return permiso in permisos_de_rol(db, actor.rol_id)


def _exigir_entidad(db: Session, actor: Usuarios, entidad: str, entidad_id: int,
                    *, escribir: bool) -> None:
    """Que la cosa exista, y que esta persona pueda verla o cambiarla.

    El trámite pasa por `casos.obtener`, que aplica el alcance: si no, adjuntar
    documentos sería la puerta de atrás para ver los trámites ajenos —bastaría
    con listar los adjuntos de un número cualquiera—.
    """
    if entidad not in ENTIDADES:
        raise Invalido(f'«{entidad}» no lleva documentos. '
                       f'Opciones: {", ".join(sorted(ENTIDADES))}.')
    permiso_ver, permiso_editar, modelo = ENTIDADES[entidad]
    if not _puede(db, actor, permiso_editar if escribir else permiso_ver):
        raise Prohibido('No tiene permiso sobre esa ficha.')

    if entidad == 'caso':
        from app.services import casos as serv_casos
        serv_casos.obtener(db, entidad_id, actor=actor)   # aplica el alcance
        return
    if db.get(modelo, entidad_id) is None:
        raise NoEncontrado('Esa ficha no existe.')


def _nombre_en_disco(doc_id_provisional: str, extension: str) -> str:
    """Un nombre que no viene del cliente.

    Usar el nombre que manda el navegador es como se cuela un «../../» y se
    escribe donde no se debe. Acá el nombre lo pone el servidor; el original se
    guarda en la columna `nombre`, que es texto y no una ruta.
    """
    return f'{doc_id_provisional}.{extension}'


def subir(db: Session, actor: Usuarios, *, entidad: str, entidad_id: int,
          archivo: Archivo, tipo: str | None = None, restringido: bool = False,
          ip: str | None = None) -> Documentos:
    """Guarda el archivo cifrado y lo deja colgado de la ficha."""
    _exigir_entidad(db, actor, entidad, entidad_id, escribir=True)

    if not archivo.contenido:
        raise Invalido('El archivo llegó vacío.', codigo='archivo_vacio')
    if len(archivo.contenido) > MAX_BYTES:
        raise Invalido(
            f'El archivo pesa {len(archivo.contenido) // 1024 // 1024} MB y el tope '
            f'es {MAX_BYTES // 1024 // 1024} MB.', codigo='demasiado_grande')

    destino = raiz()
    if destino is None:
        raise Conflicto(
            'Todavía no hay dónde guardar archivos. El servidor actual borra su disco '
            'en cada despliegue, así que subir un documento sería perderlo. Mientras '
            'tanto puede adjuntarlo como enlace a una carpeta compartida.',
            codigo='sin_almacenamiento')

    mime, extension = _mime_real(archivo.contenido)
    huella = hashlib.sha256(archivo.contenido).hexdigest()

    doc = Documentos(
        entidad=entidad, entidad_id=entidad_id,
        nombre=archivo.nombre[:200], almacenamiento='local', restringido=restringido,
        tipo=tipo, mime=mime, tamano_bytes=len(archivo.contenido), sha256=huella,
        subido_por=actor.id, ruta='pendiente')
    db.add(doc)
    db.flush()                       # para tener el id antes de escribir el archivo

    relativa = _nombre_en_disco(f'{doc.id}-{secrets.token_hex(8)}', extension)
    doc.ruta = relativa
    carpeta = destino / entidad
    carpeta.mkdir(parents=True, exist_ok=True)
    # Cifrado en reposo (RNF-04): lo que queda en el disco no se puede leer.
    (carpeta / relativa).write_bytes(seg.cifrar_bytes(archivo.contenido))

    auditar(db, operacion='insert', entidad='documentos', usuario_id=actor.id,
            entidad_id=doc.id, ip=ip,
            despues={'sobre': f'{entidad}:{entidad_id}', 'mime': mime,
                     'tamano_bytes': doc.tamano_bytes, 'restringido': restringido})
    db.commit()
    return doc


def listar(db: Session, actor: Usuarios, entidad: str, entidad_id: int) -> list[Documentos]:
    """Los documentos de una ficha, sin los restringidos si no le corresponden."""
    _exigir_entidad(db, actor, entidad, entidad_id, escribir=False)
    docs = db.scalars(select(Documentos)
                      .where(Documentos.entidad == entidad,
                             Documentos.entidad_id == entidad_id)
                      .order_by(Documentos.creado_en.desc())).all()
    if _puede(db, actor, PERMISO_RESTRINGIDO):
        return list(docs)
    # Se omiten, no se muestran en gris: saber que existe un documento
    # restringido sobre alguien ya dice algo de esa persona.
    return [d for d in docs if not d.restringido]


def obtener(db: Session, actor: Usuarios, documento_id: int) -> Documentos:
    doc = db.get(Documentos, documento_id)
    if doc is None:
        raise NoEncontrado('El documento no existe.')
    _exigir_entidad(db, actor, doc.entidad, doc.entidad_id, escribir=False)
    if doc.restringido and not _puede(db, actor, PERMISO_RESTRINGIDO):
        # Lo mismo que si no existiera: decir «existe pero no es para usted» ya
        # revela que hay algo reservado sobre esa persona.
        raise NoEncontrado('El documento no existe.')
    return doc


def descargar(db: Session, actor: Usuarios, documento_id: int, *,
              ip: str | None = None) -> tuple[bytes, Documentos]:
    """El contenido, descifrado, y constancia de quién se lo llevó.

    La descarga se registra por lo mismo que las exportaciones: un archivo deja
    de estar bajo el control del sistema en cuanto sale, y lo mínimo es saber
    quién lo sacó.
    """
    doc = obtener(db, actor, documento_id)
    if doc.almacenamiento != 'local' or not doc.ruta:
        raise Invalido('Ese documento es un enlace: ábralo desde su dirección.',
                       codigo='es_enlace')

    destino = raiz()
    archivo = (destino / doc.entidad / doc.ruta) if destino else None
    if archivo is None or not archivo.exists():
        raise NoEncontrado(
            'El archivo ya no está en el disco. Si el sistema se desplegó de nuevo en '
            'un servidor sin volumen, se perdió: vuelva a subirlo.')

    contenido = seg.descifrar_bytes(archivo.read_bytes())
    if hashlib.sha256(contenido).hexdigest() != doc.sha256:
        # No es un detalle: significa que el archivo en disco ya no es el que se
        # subió. Entregarlo como si lo fuera sería lo peor que se puede hacer.
        raise Conflicto('El archivo no coincide con su huella: puede estar dañado o '
                        'haber sido cambiado. No se entrega.', codigo='huella_distinta')

    auditar(db, operacion='descargar', entidad='documentos', usuario_id=actor.id,
            entidad_id=doc.id, ip=ip,
            despues={'sobre': f'{doc.entidad}:{doc.entidad_id}',
                     'tamano_bytes': doc.tamano_bytes})
    db.commit()
    return contenido, doc


def enlazar(db: Session, actor: Usuarios, *, entidad: str, entidad_id: int, nombre: str,
            url: str, tipo: str | None = None, restringido: bool = False,
            ip: str | None = None) -> Documentos:
    """Cuelga un documento que vive en otro lado, sin copiarlo.

    Es la salida mientras no haya disco de verdad, y además sirve siempre: hay
    cosas que ya viven en una carpeta compartida y no tiene sentido duplicar.
    """
    _exigir_entidad(db, actor, entidad, entidad_id, escribir=True)
    url = url.strip()
    if not url.lower().startswith(('http://', 'https://')):
        raise Invalido('El enlace tiene que empezar por http:// o https://.',
                       codigo='enlace_invalido')

    doc = Documentos(entidad=entidad, entidad_id=entidad_id, nombre=nombre[:200],
                     almacenamiento='enlace', url=url, tipo=tipo,
                     restringido=restringido, subido_por=actor.id)
    db.add(doc)
    db.flush()
    auditar(db, operacion='insert', entidad='documentos', usuario_id=actor.id,
            entidad_id=doc.id, ip=ip,
            despues={'sobre': f'{entidad}:{entidad_id}', 'almacenamiento': 'enlace',
                     'restringido': restringido})
    db.commit()
    return doc


def eliminar(db: Session, actor: Usuarios, documento_id: int, *,
             ip: str | None = None) -> None:
    """Lo quita de la ficha y borra el archivo.

    No se puede deshacer: el archivo cifrado se borra del disco. La constancia
    de que existió y de quién lo quitó se queda en la auditoría, que es lo que
    hay que poder reconstruir.
    """
    doc = obtener(db, actor, documento_id)
    _, permiso_editar, _ = ENTIDADES[doc.entidad]
    if not _puede(db, actor, permiso_editar):
        raise Prohibido('No tiene permiso para quitar documentos de esa ficha.')

    destino = raiz()
    if doc.almacenamiento == 'local' and doc.ruta and destino is not None:
        archivo = destino / doc.entidad / doc.ruta
        archivo.unlink(missing_ok=True)

    antes = {'sobre': f'{doc.entidad}:{doc.entidad_id}', 'nombre_largo': len(doc.nombre),
             'almacenamiento': doc.almacenamiento}
    db.delete(doc)
    auditar(db, operacion='delete', entidad='documentos', usuario_id=actor.id,
            entidad_id=documento_id, antes=antes, ip=ip)
    db.commit()
