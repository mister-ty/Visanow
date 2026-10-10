"""Envío de correo al usuario (RNF-02).

Va por SMTP y con la biblioteca estándar, a propósito: VisaNow ya tiene cuentas
de correo, SMTP lo habla cualquier proveedor, y no hace falta una dependencia
nueva ni una llave de un servicio más. Funciona igual en Render hoy y en el VPS
después.

**Si no hay proveedor configurado, no se finge que se envió.** La petición de
recuperación sigue respondiendo lo mismo exista o no la cuenta —si no, delataría
quién tiene cuenta—, pero en el log queda un error con todas las letras y el
arranque avisa. Un sistema que dice «le enviamos un correo» cuando no envió nada
deja a la persona esperando algo que no va a llegar.

Mientras no haya proveedor hay salida: la administradora restablece la
contraseña desde *Usuarios* y entrega la temporal. Es la misma puerta, solo que
atendida.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import ajustes

log = logging.getLogger('visanow.notificaciones')


def hay_proveedor() -> bool:
    """Si el envío está configurado. Lo consulta el arranque para avisar."""
    a = ajustes()
    return bool(a.smtp_host and a.smtp_desde)


def _remitente() -> str:
    a = ajustes()
    return a.smtp_desde or (a.smtp_usuario or 'no-responder@visanow.co')


def enviar(destino: str, asunto: str, cuerpo: str) -> bool:
    """Manda el correo. Devuelve si salió, y nunca levanta hacia arriba.

    Que falle el correo no puede tumbar la operación que lo pidió: quien pide
    recuperar su contraseña recibe la misma respuesta salga o no el mensaje, y
    lo que queda es el registro del fallo para que alguien lo mire.
    """
    if not hay_proveedor():
        log.error('No hay proveedor de correo configurado (SMTP_HOST y SMTP_DESDE): '
                  'no se envió «%s». Mientras tanto, la administradora puede '
                  'restablecer la contraseña desde Usuarios.', asunto)
        return False

    a = ajustes()
    mensaje = EmailMessage()
    mensaje['From'] = _remitente()
    mensaje['To'] = destino
    mensaje['Subject'] = asunto
    mensaje.set_content(cuerpo)

    # check_hostname y verify_mode van explícitos aunque create_default_context
    # ya los deja así: que la validación del certificado dependa de un valor por
    # omisión es justo lo que nadie revisa cuando cambia.
    contexto = ssl.create_default_context()
    contexto.check_hostname = True
    contexto.verify_mode = ssl.CERT_REQUIRED

    try:
        if a.smtp_ssl:
            cliente = smtplib.SMTP_SSL(a.smtp_host, a.smtp_puerto, timeout=a.smtp_timeout,
                                       context=contexto)
        else:
            cliente = smtplib.SMTP(a.smtp_host, a.smtp_puerto, timeout=a.smtp_timeout)
        with cliente as servidor:
            if a.smtp_tls and not a.smtp_ssl:
                servidor.starttls(context=contexto)
            if a.smtp_usuario:
                servidor.login(a.smtp_usuario, a.smtp_password)
            servidor.send_message(mensaje)
    except Exception as e:
        # El texto del error puede traer la dirección; el asunto no lleva datos
        # de nadie, así que se registra ese y el tipo de fallo, no el cuerpo.
        log.error('No se pudo enviar «%s»: %s: %s', asunto, type(e).__name__, e)
        return False

    log.info('Correo enviado: «%s»', asunto)
    return True


def enviar_recuperacion(email: str, token: str, minutos: int) -> bool:
    """El enlace para volver a entrar.

    Los minutos entran por parámetro y no se importan de `auth`: `auth` ya
    importa este módulo, y leerlo de vuelta sería un círculo. Además así el
    número que dice el correo es forzosamente el mismo que aplica el servicio
    que lo manda, en vez de dos constantes que un día se separan.

    En local se escribe también en el log, para poder seguir el flujo completo
    sin montar un servidor de correo.
    """
    enlace = f'{ajustes().url_ui}/restablecer?token={token}'
    if ajustes().es_local:
        log.warning('[LOCAL] Enlace de recuperación para %s: %s', email, enlace)

    return enviar(email, 'Recupere su acceso a VisaNow', f"""Alguien pidió restablecer la contraseña de esta cuenta en VisaNow.

Para ponerle una nueva, abra este enlace:

{enlace}

El enlace sirve una sola vez y vence en {minutos} minutos. Si ya venció, puede
pedir otro desde la pantalla de ingreso.

Si no fue usted, no haga nada: la contraseña actual sigue funcionando y nadie
entró a la cuenta. Si le sigue llegando este correo sin haberlo pedido, avísele
a la administradora.

VisaNow
""")
