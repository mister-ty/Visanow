"""Las tablas de traducción de la actividad 0.5.

Vienen de `05_Migracion/Diccionario_Homologacion.md`, que se generó midiendo los
valores reales de los tres libros: 140 escrituras distintas para lo que en el
sistema nuevo son unas pocas decenas de códigos.

Están aquí, en código, y no leyendo el Markdown, porque el diccionario es el
documento que se le muestra a VisaNow y esto es lo que ejecuta la máquina: si
alguien edita el documento, la migración no cambia sola. Cuando el diccionario
cambie, se cambia aquí y se anota en el mismo commit.

Lo que el diccionario dejó sin resolver queda como `None` a propósito: significa
«no sé qué es esto», y la fila termina en el reporte de excepciones en vez de
entrar con un valor inventado.
"""
from __future__ import annotations

from app.migracion.normalizacion import sin_tildes


def _clave(bruto: str) -> str:
    return ' '.join(sin_tildes(bruto).lower().split())


def _tabla(pares: dict[str, str | None]) -> dict[str, str | None]:
    return {_clave(k): v for k, v in pares.items()}


# ------------------------------------------------------------ estados del trámite

ESTADOS = _tabla({
    'Listo': 'finalizado', 'ZZfinalizado': 'finalizado', 'FINALIZADO': 'finalizado',
    'f16-finalizado': 'finalizado', 'finalizado': 'finalizado',
    'Esperando formulario': 'formulario_elaborando',
    'DS-160 en tramite': 'formulario_elaborando', '5-pendiente DS-160': 'formulario_elaborando',
    'DS-160 listo': 'formulario_enviado', '6-DS-160 listo': 'formulario_enviado',
    'Espera cliente': 'esperando_info', 'cliente no ha enviado': 'esperando_info',
    '3-espera info cliente': 'esperando_info', 'Recolectando información': 'esperando_info',
    'preparacion': 'preparacion', '9-preparacion': 'preparacion',
    'cita confirmada': 'cita_confirmada', '9-cita confirmada': 'cita_confirmada',
    'PROGRESO': 'info_en_revision', 'Trabajando': 'info_en_revision',
    '4-formulario recibido': 'info_en_revision', 'Documentos recibidos': 'info_en_revision',
    'ANALISIS': 'info_en_revision',
    'pago visa': 'pago_consular_pend', '7-pago visa': 'pago_consular_pend',
    'espera resultado': 'esperando_resultado',
    'PDT ENTRE': 'entrega_documento', 'PDTE ENTRE': 'entrega_documento', 'PDT': 'entrega_documento',
    '15-recoleccion visa': 'entrega_documento', 'recoleccion visa': 'entrega_documento',
    '8-adelanto': 'busqueda_cita', 'adelanto': 'busqueda_cita',
    'PENDIENTE': 'registrado',
    '11-documentacion cita': 'checklist',
})

# ------------------------------------------------------------- resultado consular

RESULTADOS = _tabla({
    'APROBADA': 'aprobada', 'VISA APROBADA': 'aprobada', 'APROBADA/ OFRECER RECOGIDA': 'aprobada',
    'NEGADA': 'negada', 'VISA NEGADA': 'negada', 'NEGADO': 'negada',
    'FINALIZADO/ NEGADO': 'negada',
    'NO CONTINUO': 'no_continuo',
    'PROCESO ADMI -': 'proceso_administrativo',
    'N/A': None,
})

# Valores que la columna «Resultado» trae sin ser un resultado consular: son
# notas del embudo comercial o estados de gestión. Van a la cronología, no al
# resultado del trámite (el diccionario lo explica en la sección de ADELANTOS).
RESULTADO_ES_NOTA = {_clave(x) for x in (
    'HECHO', 'POSIBLES INTERESADOS', 'ADELANTADO', 'NO ES CLIENTE', 'ADELANTO',
    'OFRECER ADELANTO', 'GRUPO DE 3- A LA ESPERA DE UN VIAJE', 'DESPUES DEL 20 DE MAYO',
)}

# --------------------------------------------------------------------- servicios

SERVICIOS = _tabla({
    'PREMIUM': 'asesoria_adelanto', 'ASESORIA PREMIUM': 'asesoria_adelanto',
    'ASESORIA Y ADELANTO': 'asesoria_adelanto', 'ASESORIA + ADELANTO': 'asesoria_adelanto',
    'ASESORIA + ADELAN': 'asesoria_adelanto', 'ASESORIA+ ADELANTO': 'asesoria_adelanto',
    'asesoria - adelanto': 'asesoria_adelanto', 'ASESORIA Y ADELANTAMIENTO': 'asesoria_adelanto',
    'VISA 1RA VEZ': 'asesoria_usa', 'USA VISA': 'asesoria_usa', 'ASESORIA': 'asesoria_usa',
    'USA ESTANDAR': 'asesoria_usa', 'ASESORIA ESTANDAR': 'asesoria_usa',
    'SERVICIO ESTANDAR': 'asesoria_usa',
    'ENVIO DOCU': 'recoleccion_envio', 'ENVIO DE VISA': 'recoleccion_envio',
    'RECOLECCION': 'recoleccion_envio',
    'PAGO VISA': 'pago_visa', 'PAGO DE VISA': 'pago_visa',
    'ADELANTO': 'adelantos', 'ADELANTAMIENTO': 'adelantos',
    'ANALISIS DE PERFIL': 'analisis_perfil', 'ANALISIS': 'analisis_perfil',
    'ANALISIS DE PERFILR': 'analisis_perfil',
    'RENOVACION': 'renovacion', 'RENOVACION PREMIUM': 'renovacion_premium',
    'PASAPORTE': 'pasaporte', 'PAGO PASAPORTE': 'pasaporte', 'PASAPORTE 2': 'pasaporte',
    'PRIMER PAGO PASAPORTE': 'pasaporte', 'pasaporte (primer pago)': 'pasaporte',
    'VISA UK': 'visa_uk', 'VISA CANADA': 'visa_canada', 'VISA CANADÁ (2 VISAS)': 'visa_canada',
    'PREPARACION ENTRE': 'preparacion_entrevista', 'PREPARACION': 'preparacion_entrevista',
    'PREPARACION ENTREVISTA': 'preparacion_entrevista',
    'ACTUALIZACION DS160': 'act_ds160', 'ACT FORMULARIO': 'act_ds160',
    'VISA AUSTRALIA': 'visa_australia', 'ASESORIA NIÑOS': 'visa_usa_ninos',
})

# ----------------------------------------------------------------------- canales

CANALES = _tabla({
    'Recomendacion': 'recomendado', 'RECOMEN': 'recomendado',
    'Instagram': 'instagram', 'Influencer': 'influencer', 'Tiktok': 'tiktok',
    'Publicidad': 'publicidad', 'NO APLICA': 'no_aplica',
})

# -------------------------------------------------------------------- vendedores

VENDEDORES = _tabla({
    'Angie': 'angie', 'ANGY': 'angie', 'Angie lorena': 'angie', 'Angie Lima': 'angie',
    'Angie lima': 'angie', 'Amgie': 'angie', 'Angisita la más linda': 'angie',
    'Amgisita': 'angie', 'Angisita': 'angie',
    'LAU': 'laura', 'YAS': 'yasmin',
    'NA': None,
})

# La columna «MEDIO» de las hojas de venta NO es medio de pago: sus valores son
# RECOMEN, INSTAGRAM, PUBLICIDAD, NO APLICA, INFLUENCER y TIKTOK. Es el canal
# por el que llegó el cliente. El medio de pago real vive en «BANCO».
MEDIO_ES_CANAL = True


def traducir(tabla: dict[str, str | None], bruto: str | None) -> tuple[str | None, str | None]:
    """Devuelve (código, problema). Si el valor no está en la tabla, el problema
    lo dice con el texto original para poder agregarlo al diccionario."""
    if not bruto:
        return None, None
    clave = _clave(bruto)
    if clave in tabla:
        return tabla[clave], None
    return None, f'«{bruto.strip()[:40]}» no está en el diccionario de homologación'


def estado(bruto: str | None) -> tuple[str | None, str | None]:
    return traducir(ESTADOS, bruto)


def resultado(bruto: str | None) -> tuple[str | None, str | None]:
    """El resultado consular. Si el valor es en realidad una nota comercial, lo
    dice para que se guarde en la cronología y no como resultado."""
    if bruto and _clave(bruto) in RESULTADO_ES_NOTA:
        return None, 'nota'
    return traducir(RESULTADOS, bruto)


def servicio(bruto: str | None) -> tuple[str | None, str | None]:
    return traducir(SERVICIOS, bruto)


def canal(bruto: str | None) -> tuple[str | None, str | None]:
    return traducir(CANALES, bruto)


def vendedor(bruto: str | None) -> tuple[str | None, str | None]:
    return traducir(VENDEDORES, bruto)
