from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.deps import ip_cliente, mfa_pendiente, usuario_actual
from app.db.session import get_db
from app.models.esquema import Usuarios
from app.schemas import auth as esq
from app.services import auth as servicio
from app.services.usuarios import permisos_de_rol

router = APIRouter(prefix='/auth', tags=['autenticación'])


@router.post('/login', response_model=esq.TokenSalida | esq.DesafioMfa)
def login(datos: esq.LoginEntrada, request: Request, db: Session = Depends(get_db)):
    """Si el usuario tiene doble factor, devuelve un desafío en vez del token:
    el token llega después, en /auth/mfa/verificar."""
    u = servicio.autenticar(db, datos.email, datos.password, ip_cliente(request))
    return servicio.emitir_desafio_mfa(u) if u.mfa_habilitado else servicio.emitir_acceso(u)


@router.post('/mfa/verificar', response_model=esq.TokenSalida)
def verificar_mfa(datos: esq.SegundoFactorEntrada, request: Request, db: Session = Depends(get_db)):
    u = servicio.verificar_segundo_factor(db, datos.token_mfa, datos.codigo, ip_cliente(request))
    return servicio.emitir_acceso(u)


@router.get('/yo', response_model=esq.YoSalida)
def yo(u: Usuarios = Depends(usuario_actual), db: Session = Depends(get_db)):
    return esq.YoSalida(
        id=u.id, nombre=u.nombre, email=u.email, rol=u.rol.codigo, alcance=u.alcance,
        permisos=sorted(permisos_de_rol(db, u.rol_id)), mfa_habilitado=u.mfa_habilitado,
        debe_cambiar_password=u.debe_cambiar_password, mfa_requerido=mfa_pendiente(u),
        ultimo_acceso=u.ultimo_acceso)


@router.post('/mfa/iniciar', response_model=esq.MfaInicioSalida)
def iniciar_mfa(u: Usuarios = Depends(usuario_actual), db: Session = Depends(get_db)):
    return servicio.iniciar_mfa(db, u)


@router.post('/mfa/confirmar', status_code=status.HTTP_204_NO_CONTENT)
def confirmar_mfa(datos: esq.CodigoEntrada, request: Request,
                  u: Usuarios = Depends(usuario_actual), db: Session = Depends(get_db)):
    servicio.confirmar_mfa(db, u, datos.codigo, ip_cliente(request))


@router.post('/cambiar-password', response_model=esq.TokenSalida)
def cambiar_password(datos: esq.CambioPasswordEntrada, request: Request,
                     u: Usuarios = Depends(usuario_actual), db: Session = Depends(get_db)):
    """Cierra todas las demás sesiones y devuelve un token nuevo para esta."""
    servicio.cambiar_password(db, u, datos.actual, datos.nueva, ip_cliente(request))
    return servicio.emitir_acceso(u)


@router.post('/recuperar', status_code=status.HTTP_202_ACCEPTED)
def recuperar(datos: esq.RecuperarEntrada, request: Request, db: Session = Depends(get_db)):
    """Responde igual exista o no el correo."""
    servicio.solicitar_recuperacion(db, datos.email, ip_cliente(request))
    return {'detalle': 'Si el correo corresponde a una cuenta activa, llegará un enlace para restablecer la contraseña.'}


@router.post('/restablecer', status_code=status.HTTP_204_NO_CONTENT)
def restablecer(datos: esq.RestablecerEntrada, request: Request, db: Session = Depends(get_db)):
    servicio.restablecer_password(db, datos.token, datos.nueva, ip_cliente(request))
