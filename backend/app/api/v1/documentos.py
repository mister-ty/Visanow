"""Documentos de una ficha: subir, listar, descargar y quitar (RNF-04, RF-064)."""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, usuario_operativo
from app.core.errores import Invalido
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.services import documentos as servicio

router = APIRouter(prefix='/documentos', tags=['documentos'])


class DocumentoSalida(BaseModel):
    id: int
    entidad: str
    entidad_id: int
    nombre: str
    almacenamiento: str
    tipo: str | None
    mime: str | None
    url: str | None
    tamano_bytes: int | None
    restringido: bool
    subido_por: int | None
    creado_en: datetime


class EstadoSalida(BaseModel):
    """Si este servidor puede guardar archivos, para que la pantalla lo diga antes."""
    se_pueden_subir: bool
    max_mb: int
    tipos: list[str]
    motivo: str | None = Field(
        default=None, description='Por qué no se puede, cuando no se puede')


class EnlaceEntrada(BaseModel):
    entidad: str
    entidad_id: int
    nombre: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=8, max_length=2000)
    tipo: str | None = None
    restringido: bool = False


def _salida(d) -> DocumentoSalida:
    return DocumentoSalida.model_validate(d, from_attributes=True)


@router.get('/estado', response_model=EstadoSalida)
def estado(_: Usuarios = Depends(usuario_operativo)):
    """La pantalla pregunta esto antes de ofrecer el botón de subir.

    Ofrecer «subir archivo» donde el archivo se va a perder es peor que no
    ofrecerlo: la persona cree que quedó guardado.
    """
    puede = servicio.se_pueden_guardar_archivos()
    return EstadoSalida(
        se_pueden_subir=puede,
        max_mb=servicio.MAX_BYTES // 1024 // 1024,
        tipos=sorted({ext for _, _, ext in servicio.FIRMAS}),
        motivo=None if puede else (
            'Este servidor borra su disco en cada despliegue, así que un archivo '
            'subido se perdería. Puede adjuntarlo como enlace mientras tanto.'))


@router.get('', response_model=list[DocumentoSalida])
def listar(entidad: str, entidad_id: int,
           actor: Usuarios = Depends(usuario_operativo), db: Session = Depends(get_db)):
    """Los documentos de una ficha. Los restringidos solo para quien corresponde."""
    return [_salida(d) for d in servicio.listar(db, actor, entidad, entidad_id)]


@router.post('', response_model=DocumentoSalida, status_code=status.HTTP_201_CREATED)
async def subir(request: Request, entidad: str = Form(...), entidad_id: int = Form(...),
                archivo: UploadFile = File(...), tipo: str | None = Form(default=None),
                restringido: bool = Form(default=False),
                actor: Usuarios = Depends(usuario_operativo),
                db: Session = Depends(get_db)):
    """Sube un archivo y lo deja cifrado en disco.

    Se lee entero en memoria a propósito: el tope son 25 MB y hay que calcular
    la huella y cifrarlo de todos modos, así que no gana nada con ir por partes
    y sí se complica el poder rechazarlo antes de escribir nada.
    """
    contenido = await archivo.read()
    if len(contenido) > servicio.MAX_BYTES:
        raise Invalido(
            f'El archivo supera los {servicio.MAX_BYTES // 1024 // 1024} MB.',
            codigo='demasiado_grande')

    doc = servicio.subir(
        db, actor, entidad=entidad, entidad_id=entidad_id,
        archivo=servicio.Archivo(nombre=archivo.filename or 'documento',
                                 contenido=contenido),
        tipo=tipo, restringido=restringido, ip=ip_cliente(request))
    return _salida(doc)


@router.post('/enlace', response_model=DocumentoSalida, status_code=status.HTTP_201_CREATED)
def enlazar(datos: EnlaceEntrada, request: Request,
            actor: Usuarios = Depends(usuario_operativo), db: Session = Depends(get_db)):
    """Cuelga un documento que ya vive en otro lado, sin copiarlo."""
    doc = servicio.enlazar(db, actor, entidad=datos.entidad, entidad_id=datos.entidad_id,
                           nombre=datos.nombre, url=datos.url, tipo=datos.tipo,
                           restringido=datos.restringido, ip=ip_cliente(request))
    return _salida(doc)


@router.get('/{documento_id}/contenido')
def descargar(documento_id: int, request: Request,
              actor: Usuarios = Depends(usuario_operativo), db: Session = Depends(get_db)):
    """El archivo. Queda registrado quién se lo llevó.

    Siempre como adjunto y nunca en línea: un SVG o un HTML servido en línea se
    ejecuta en el navegador de quien lo abre, con la sesión de esa persona.
    """
    contenido, doc = servicio.descargar(db, actor, documento_id, ip=ip_cliente(request))
    # El nombre se limpia: viene de quien subió el archivo, y de ahí sale a una
    # cabecera. Las comillas y los saltos de línea parten la cabecera en dos.
    seguro = ''.join(c for c in doc.nombre if c.isalnum() or c in ' .-_()')[:120] or 'documento'
    return Response(contenido, media_type=doc.mime or 'application/octet-stream',
                    headers={'Content-Disposition': f'attachment; filename="{seguro}"',
                             'X-Content-Type-Options': 'nosniff'})


@router.delete('/{documento_id}', status_code=status.HTTP_204_NO_CONTENT)
def eliminar(documento_id: int, request: Request,
             actor: Usuarios = Depends(usuario_operativo), db: Session = Depends(get_db)):
    """Lo quita de la ficha y borra el archivo. No se puede deshacer."""
    servicio.eliminar(db, actor, documento_id, ip=ip_cliente(request))
