"""Envío de mensajes al usuario.

Todavía no hay proveedor de correo definido. En local el enlace se escribe en el
log para poder probar el flujo completo; en cualquier otro entorno se registra
la falta de proveedor en lugar de fingir que se envió.
"""
import logging

from app.core.config import ajustes

log = logging.getLogger('visanow.notificaciones')


def enviar_recuperacion(email: str, token: str) -> None:
    enlace = f'{ajustes().url_ui}/restablecer?token={token}'
    if ajustes().es_local:
        log.warning('[LOCAL] Enlace de recuperación para %s: %s', email, enlace)
        return
    log.error('No hay proveedor de correo configurado: no se pudo enviar la recuperación a %s',
              email)
