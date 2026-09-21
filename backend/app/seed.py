"""Siembra los catálogos del sistema.

Los valores no se inventan: salen de los archivos de VisaNow y de la lista de
precios que envió la administradora el 19/09/2026, traducidos con el
diccionario de homologación de la actividad 0.5
(05_Migracion/Diccionario_Homologacion.md).

Es idempotente: se puede correr las veces que haga falta.

    python -m app.seed
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import unicodedata

import psycopg

RAIZ = pathlib.Path(__file__).resolve().parents[2]


def cargar_env() -> None:
    env = RAIZ / '.env'
    if not env.exists():
        sys.exit(f'Falta {env}. Cópialo de .env.example y llénalo.')
    for linea in env.read_text(encoding='utf-8').splitlines():
        linea = linea.split('#')[0].strip()
        if '=' in linea:
            k, _, v = linea.partition('=')
            os.environ.setdefault(k.strip(), v.strip())


def norm(valor) -> str:
    s = unicodedata.normalize('NFKD', str(valor)).encode('ascii', 'ignore').decode()
    return ' '.join(s.lower().split())


# --------------------------------------------------------------------------
# Catálogos fijos: definidos por la especificación, no por los datos
# --------------------------------------------------------------------------

ROLES = [
    ('administradora', 'Administradora / CEO'),
    ('comercial',      'Comercial'),
    ('operaciones',    'Operaciones'),
    ('finanzas',       'Finanzas'),
    ('apoyo_externo',  'Apoyo externo'),
    ('solo_lectura',   'Solo lectura'),
]

# Permisos por módulo. El criterio de aceptación 9 exige que operaciones
# no pueda editar reglas de comisión ni valores conciliados.
MODULOS = ['clientes', 'solicitantes', 'oportunidades', 'negocios', 'casos',
           'pagos', 'ajustes', 'gastos', 'comisiones', 'catalogos',
           'usuarios', 'alertas', 'tableros', 'importacion', 'auditoria']
ACCIONES = ['ver', 'crear', 'editar', 'eliminar', 'exportar']

# Qué puede hacer cada rol, por módulo. 'todo' = las cinco acciones.
MATRIZ = {
    'administradora': {m: 'todo' for m in MODULOS},
    'comercial': {
        'clientes': ['ver', 'crear', 'editar'], 'solicitantes': ['ver', 'crear', 'editar'],
        'oportunidades': 'todo', 'negocios': ['ver', 'crear', 'editar'],
        'casos': ['ver'], 'pagos': ['ver'], 'alertas': ['ver', 'editar'],
        'tableros': ['ver'], 'catalogos': ['ver'],
    },
    'operaciones': {
        'clientes': ['ver', 'crear', 'editar'], 'solicitantes': ['ver', 'crear', 'editar'],
        'casos': 'todo', 'oportunidades': ['ver'], 'negocios': ['ver'],
        'pagos': ['ver'],                      # ver sí, editar no
        'importacion': ['ver', 'crear'], 'alertas': ['ver', 'editar'],
        'tableros': ['ver'], 'catalogos': ['ver'],
    },
    'finanzas': {
        'clientes': ['ver'], 'negocios': ['ver', 'editar'], 'casos': ['ver'],
        'pagos': 'todo', 'ajustes': 'todo', 'gastos': 'todo',
        'comisiones': ['ver', 'crear', 'editar', 'exportar'],
        'alertas': ['ver', 'editar'], 'tableros': ['ver', 'exportar'], 'catalogos': ['ver'],
    },
    'apoyo_externo': {'casos': ['ver', 'editar'], 'solicitantes': ['ver'], 'alertas': ['ver']},
    'solo_lectura': {m: ['ver'] for m in MODULOS},
}

MODALIDADES = [
    ('primera_vez', 'Primera vez'),
    ('renovacion',  'Renovación'),
    ('grupal',      'Grupal / familiar'),
    ('menores',     'Menores de edad'),
]

MOTIVOS_PERDIDA = [
    ('precio',       'Precio'),
    ('no_respondio', 'No respondió'),
    ('aplazo',       'Aplazó el trámite'),
    ('no_califica',  'No califica'),
    ('competencia',  'Se fue con la competencia'),
    ('otro',         'Otro'),
]

MEDIOS_PAGO = [
    ('transferencia', 'Transferencia bancaria'),
    ('nequi',         'Nequi'),
    ('daviplata',     'Daviplata'),
    ('efectivo',      'Efectivo'),
    ('tarjeta',       'Tarjeta'),
    ('pasarela',      'Pasarela de pago'),
]

# Las 13 alertas de la sección 9 de la especificación (RF-062).
# anticipacion_valor negativo = el disparo es DESPUÉS del evento.
# repeticiones = a los cuántos días se vuelve a avisar.
# (codigo, nombre, entidad, valor, unidad, repeticiones, rol, severidad)
ALERTAS = [
    ('lead_sin_contacto',       'Lead sin primer contacto',       'oportunidad',  2, 'horas',        [],        'comercial',      'alta'),
    ('oport_sin_accion',        'Oportunidad sin próxima acción', 'oportunidad',  0, 'horas',        [],        'comercial',      'media'),
    ('cliente_sin_info',        'Cliente sin enviar información', 'caso',        -3, 'dias',         [7,14,21], 'operaciones',    'media'),
    ('caso_sin_movimiento',     'Caso sin movimiento',            'caso',        -5, 'dias_habiles', [],        'operaciones',    'alta'),
    ('pago_inicial_pendiente',  'Pago inicial pendiente',         'negocio',      0, 'dias',         [],        'finanzas',       'alta'),
    ('saldo_por_vencer',        'Saldo próximo a vencer',         'negocio',      3, 'dias',         [],        'finanzas',       'media'),
    ('saldo_vencido',           'Saldo vencido',                  'negocio',     -1, 'dias',         [7,15],    'finanzas',       'alta'),
    ('cita_cas',                'Cita CAS / biometría',           'cita',         7, 'dias',         [1],       'operaciones',    'alta'),
    ('preparacion_pendiente',   'Preparación pendiente',          'cita',         7, 'dias',         [],        'operaciones',    'media'),
    ('entrevista_proxima',      'Entrevista / radicación',        'cita',         7, 'dias',         [1],       'operaciones',    'alta'),
    ('resultado_no_registrado', 'Resultado no registrado',        'cita',        -2, 'dias',         [],        'operaciones',    'media'),
    ('pasaporte_por_entregar',  'Pasaporte por recoger o enviar', 'caso',        -2, 'dias',         [],        'operaciones',    'media'),
    ('sync_saas_fallida',       'Sincronización SaaS fallida',    'importacion', -1, 'dias',         [],        'administradora', 'alta'),
]


# --------------------------------------------------------------------------
# Catálogos extraídos de los archivos fuente
# --------------------------------------------------------------------------

# Catálogo de servicios de VisaNow: lista de precios que envió la administradora
# el 19/09/2026 (hoja PRECIOS de CUENTAS VISANOW en Google Sheets). Cierra D-11.
#
# (código, nombre, país ISO2, tipo, crea casos, tasa consular valor, moneda, nota)
#   tipo 'recaudo_terceros': plata del consulado que VisaNow recauda; no es ingreso.
#   crea casos = False: el servicio es un complemento de otra venta (preparación,
#   envío, actualización del DS-160) o no es un trámite de visa (análisis, pasaporte).
FECHA_LISTA_PRECIOS = '2026-09-19'
SERVICIOS = [
    ('asesoria_usa',              'Asesoría USA',                     'US', 'honorario', True,  185,    'USD', None),
    ('asesoria_adelanto',         'Asesoría USA + adelanto (Premium)', 'US', 'honorario', True,  185,    'USD', None),
    ('adelantos',                 'Adelanto de cita',                 'US', 'honorario', True,  None,   None,  None),
    ('renovacion',                'Renovación',                       'US', 'honorario', True,  185,    'USD', None),
    ('renovacion_completa',       'Renovación completa',              'US', 'honorario', True,  185,    'USD', None),
    ('renovacion_premium',        'Renovación premium',               'US', 'honorario', True,  185,    'USD', None),
    ('analisis_perfil',           'Análisis de perfil',               None, 'honorario', False, None,   None,  None),
    ('visa_usa_ninos',            'Visa USA niños',                   'US', 'honorario', True,  185,    'USD', None),
    ('pasaporte',                 'Trámite de pasaporte',             'CO', 'honorario', False, None,   None,  None),
    ('act_ds160',                 'Actualización de DS-160',          'US', 'honorario', False, None,   None,  None),
    ('preparacion_entrevista',    'Preparación para la entrevista',   'US', 'honorario', False, None,   None,  None),
    ('recoleccion_envio',         'Recolección / envío de documentos', None, 'honorario', False, None,  None,  None),
    ('visa_clientes_internacional', 'Visa USA clientes internacionales', 'US', 'honorario', True, 185,  'USD', None),
    ('visa_canada',               'Visa Canadá',                      'CA', 'honorario', True,  185,    'CAD', None),
    ('visa_uk',                   'Visa Reino Unido',                 'GB', 'honorario', True,  135,    'GBP', None),
    ('visa_australia',            'Visa Australia',                   'AU', 'honorario', True,  250,    'AUD', None),
    ('visa_japon',                'Visa Japón',                       'JP', 'honorario', True,  0,      'COP', 'Gratis para colombianos'),
    ('visa_china_estandar',       'Visa China estándar',              'CN', 'honorario', True,  311000, 'COP', None),
    ('visa_china_premium',        'Visa China premium',               'CN', 'honorario', True,  311000, 'COP', None),
    ('visa_china_negocios',       'Visa China negocios',              'CN', 'honorario', True,  None,   None,
     'Según la lista: 3270000 (una entrada) (2 entry 374.000). POR CONFIRMAR'),
    ('visa_china_internacional',  'Visa China clientes internacionales', 'CN', 'honorario', True, None, None, None),
    ('visa_vietnam',              'Visa Vietnam',                     'VN', 'honorario', True,  25,     'USD', None),
    ('visa_canada_dubai',         'Visa Canadá desde Dubái',          'CA', 'honorario', True,  185,    'CAD', None),
    ('entrega_documentos_ninos',  'Entrega de documentos niños',      'US', 'honorario', True,  0,      'COP', None),
    ('visa_premium_ninos',        'Visa premium niños',               'US', 'honorario', True,  185,    'USD', None),
    ('pago_visa',                 'Pago de tasa consular',            None, 'recaudo_terceros', False, None, None,
     'Se cobra aparte de la asesoría. Es plata del consulado: no cuenta como venta ni como base de comisión.'),
]

# Tarifas de la lista del 19/09/2026. (código, personas, valor, modalidad)
#   modalidad 'total': el valor es por todo el grupo de ese tamaño.
# Solo se cargan los escalones inequívocos: cuando la columna «V MINIMO / 2 +»
# es MAYOR que el precio individual es el precio total para 2 personas; cuando
# es MENOR, la columna significa «valor mínimo» o «precio por persona» y la
# lista no dice cuál. Esos casos van a VALORES_MINIMOS y quedan por confirmar.
TARIFAS = [
    ('asesoria_usa', 1, 600000, 'total'), ('asesoria_usa', 3, 1500000, 'total'),
    ('asesoria_adelanto', 1, 1200000, 'total'), ('asesoria_adelanto', 2, 2200000, 'total'),
    ('asesoria_adelanto', 3, 3300000, 'total'), ('asesoria_adelanto', 4, 4400000, 'total'),
    ('adelantos', 1, 700000, 'total'), ('adelantos', 2, 1200000, 'total'),
    ('adelantos', 3, 1700000, 'total'), ('adelantos', 4, 2300000, 'total'),
    ('renovacion', 1, 500000, 'total'), ('renovacion', 2, 800000, 'total'),
    ('renovacion', 3, 1200000, 'total'), ('renovacion', 4, 2000000, 'total'),
    ('renovacion_completa', 1, 900000, 'total'), ('renovacion_completa', 2, 1600000, 'total'),
    ('renovacion_completa', 3, 2000000, 'total'), ('renovacion_completa', 4, 3100000, 'total'),
    # La lista dice $33.000.000 para 3 personas: error de digitación de $3.300.000. POR CONFIRMAR
    ('renovacion_premium', 1, 1200000, 'total'), ('renovacion_premium', 2, 2200000, 'total'),
    ('renovacion_premium', 3, 3300000, 'total'), ('renovacion_premium', 4, 4400000, 'total'),
    ('analisis_perfil', 1, 80000, 'total'),
    ('visa_usa_ninos', 1, 500000, 'total'), ('visa_usa_ninos', 2, 800000, 'total'),
    ('pasaporte', 1, 120000, 'total'), ('pasaporte', 2, 200000, 'total'),
    ('act_ds160', 1, 250000, 'total'), ('act_ds160', 2, 450000, 'total'),
    ('preparacion_entrevista', 1, 280000, 'total'),
    ('recoleccion_envio', 1, 120000, 'total'), ('recoleccion_envio', 2, 180000, 'total'),
    ('visa_clientes_internacional', 1, 1100000, 'total'), ('visa_clientes_internacional', 2, 2000000, 'total'),
    ('visa_clientes_internacional', 3, 2900000, 'total'), ('visa_clientes_internacional', 4, 3900000, 'total'),
    ('visa_canada', 1, 600000, 'total'),
    ('visa_uk', 1, 600000, 'total'),
    ('visa_australia', 1, 600000, 'total'),
    ('visa_japon', 1, 600000, 'total'),
    # 3 personas: la lista dice «400.00». No se carga hasta confirmar. POR CONFIRMAR
    ('visa_china_estandar', 1, 460000, 'total'), ('visa_china_estandar', 2, 850000, 'total'),
    ('visa_china_premium', 1, 800000, 'total'),
    ('visa_china_negocios', 1, 500000, 'total'), ('visa_china_negocios', 2, 960000, 'total'),
    ('visa_china_internacional', 1, 600000, 'total'), ('visa_china_internacional', 2, 1150000, 'total'),
    ('visa_vietnam', 1, 350000, 'total'), ('visa_vietnam', 2, 680000, 'total'),
    ('visa_canada_dubai', 1, 700000, 'total'), ('visa_canada_dubai', 2, 1300000, 'total'),
    ('entrega_documentos_ninos', 1, 350000, 'total'),
    # La lista dice $440.000 para 4 personas: error de digitación de $4.400.000. POR CONFIRMAR
    ('visa_premium_ninos', 1, 1200000, 'total'), ('visa_premium_ninos', 2, 2200000, 'total'),
    ('visa_premium_ninos', 3, 3300000, 'total'), ('visa_premium_ninos', 4, 4400000, 'total'),
]

# Columna «V MINIMO / 2 +» cuando es menor que el precio individual. Se guarda como
# valor mínimo de negociación del precio individual (no se inventa un precio de
# grupo). Si resulta ser «precio por persona para 2 o más», se convierte en
# escalón desde la administración. POR CONFIRMAR con la administradora.
VALORES_MINIMOS = {
    'asesoria_usa': 550000, 'preparacion_entrevista': 230000, 'visa_canada': 480000,
    'visa_uk': 480000, 'visa_australia': 500000, 'visa_japon': 280000,
    'visa_china_premium': 700000, 'entrega_documentos_ninos': 300000,
}

# Códigos del catálogo provisional que se sembró antes de tener la lista real.
# Se desactivan (no se borran: la trazabilidad no se pierde).
SERVICIOS_PROVISIONALES = ['usa_premium', 'usa_estandar', 'busqueda_cita_serv', 'pago_consular',
                           'envio_documentos', 'representacion', 'actualizacion_ds160',
                           'visa_china', 'visa_schengen']

# Parámetros del negocio, editables desde la administración
PARAMETROS = [
    ('cartera.plazo_saldo_dias', 30,
     'Días desde la venta para pagar el saldo. Pasado este plazo el saldo está en mora. '
     'Respuesta de la administradora del 19/09/2026: el saldo se paga al agendar la cita y, '
     'si no se ha pagado al mes, está en mora.'),
    ('cartera.anticipos_porcentaje', [20, 80],
     'Porcentajes de anticipo con que el cliente puede iniciar el trámite.'),
    ('login.max_intentos', 5, 'Intentos fallidos antes de bloquear la cuenta (informativo: se '
                              'configura en el servidor).'),
]

CANALES = [
    ('recomendado', 'Recomendación'),
    ('instagram',   'Instagram'),
    ('influencer',  'Influencer'),
    ('tiktok',      'TikTok'),
    ('publicidad',  'Publicidad pagada'),
    ('no_aplica',   'No aplica'),
]

CATEGORIAS_GASTO = [
    ('mensajeria',   'Mensajería y envíos'),
    ('publicidad',   'Publicidad'),
    ('honorarios',   'Honorarios de apoyo'),
    ('diseno',       'Diseño'),
    ('tasas',        'Tasas y pagos consulares'),
    ('operativo',    'Gasto operativo'),
    ('otro',         'Otro'),
]

# Transiciones permitidas entre los 16 estados operativos.
# La tabla existía en el esquema y nunca se sembró: sin esto, RF-023
# (transiciones controladas) no tiene contra qué validar.
TRANSICIONES = [
    ('registrado',            'esperando_info'),
    ('registrado',            'excepcion'),
    ('esperando_info',        'info_incompleta'),
    ('esperando_info',        'info_en_revision'),
    ('esperando_info',        'excepcion'),
    ('info_incompleta',       'esperando_info'),
    ('info_incompleta',       'info_en_revision'),
    ('info_incompleta',       'excepcion'),
    ('info_en_revision',      'formulario_elaborando'),
    ('info_en_revision',      'info_incompleta'),
    ('info_en_revision',      'excepcion'),
    ('formulario_elaborando', 'formulario_enviado'),
    ('formulario_elaborando', 'excepcion'),
    ('formulario_enviado',    'pago_consular_pend'),
    ('formulario_enviado',    'formulario_elaborando'),
    ('pago_consular_pend',    'busqueda_cita'),
    ('pago_consular_pend',    'excepcion'),
    ('busqueda_cita',         'cita_confirmada'),
    ('busqueda_cita',         'excepcion'),
    ('cita_confirmada',       'preparacion'),
    ('cita_confirmada',       'checklist'),
    ('cita_confirmada',       'busqueda_cita'),      # reprogramación
    ('preparacion',           'checklist'),
    ('preparacion',           'esperando_resultado'),
    ('checklist',             'esperando_resultado'),
    ('checklist',             'preparacion'),
    ('esperando_resultado',   'con_resultado'),
    ('con_resultado',         'entrega_documento'),
    ('con_resultado',         'finalizado'),
    ('entrega_documento',     'finalizado'),
]

# Transiciones que exigen checklist completo antes de avanzar (RN-05).
CON_CHECKLIST = {('checklist', 'esperando_resultado'), ('preparacion', 'esperando_resultado')}

# Campos obligatorios por transición (RF-023).
OBLIGATORIOS = {
    ('busqueda_cita', 'cita_confirmada'):     ['cita_fecha', 'sede_id'],
    ('esperando_resultado', 'con_resultado'): ['resultado', 'resultado_fecha'],
    ('con_resultado', 'finalizado'):          ['resultado'],
}


def paises_desde_datos(cur) -> None:
    """Países observados en las hojas 'País de la Cita' y '_Listas'."""
    NOMBRE = {
        'CO': 'Colombia', 'AE': 'Emiratos Árabes Unidos', 'ES': 'España', 'AT': 'Austria',
        'MX': 'México', 'FR': 'Francia', 'PA': 'Panamá', 'CN': 'China', 'VE': 'Venezuela',
        'AR': 'Argentina', 'PT': 'Portugal', 'AU': 'Australia', 'IT': 'Italia',
        'DE': 'Alemania', 'BE': 'Bélgica', 'PL': 'Polonia', 'GB': 'Reino Unido',
        'HU': 'Hungría', 'RO': 'Rumania', 'US': 'Estados Unidos', 'CA': 'Canadá',
        'JP': 'Japón', 'VN': 'Vietnam',
    }
    for iso, nombre in NOMBRE.items():
        cur.execute("""insert into paises (iso2, nombre) values (%s, %s)
                       on conflict (iso2) do nothing""", (iso, nombre))
    return len(NOMBRE)


def sembrar_catalogo(cur) -> tuple[int, int, int]:
    """Servicios, tarifas y valores mínimos de la lista del 19/09/2026.
    Las tarifas anteriores de un mismo servicio se cierran un día antes de la
    lista nueva: el historial de precios se conserva (RN-07)."""
    for codigo, nombre, pais, tipo, crea, tasa, moneda, nota in SERVICIOS:
        cur.execute("""
            insert into servicios (codigo, nombre, pais_id, tipo, crea_casos,
                                   tasa_consular_valor, tasa_consular_moneda, tasa_consular_nota, activo)
            values (%s, %s, (select id from paises where iso2 = %s), %s, %s, %s, %s, %s, true)
            on conflict (codigo) do update set
              nombre = excluded.nombre, pais_id = excluded.pais_id, tipo = excluded.tipo,
              crea_casos = excluded.crea_casos, tasa_consular_valor = excluded.tasa_consular_valor,
              tasa_consular_moneda = excluded.tasa_consular_moneda,
              tasa_consular_nota = excluded.tasa_consular_nota, activo = true""",
                    (codigo, nombre, pais, tipo, crea, tasa, moneda, nota))
    cur.execute('update servicios set activo = false where codigo = any(%s)', (SERVICIOS_PROVISIONALES,))
    retirados = cur.rowcount

    cur.execute("""update tarifas set vigente_hasta = %s::date - 1
                   where vigente_hasta is null and vigente_desde < %s::date""",
                (FECHA_LISTA_PRECIOS, FECHA_LISTA_PRECIOS))
    for codigo, personas, valor, modalidad in TARIFAS:
        minimo = VALORES_MINIMOS.get(codigo) if personas == 1 else None
        cur.execute("""
            insert into tarifas (servicio_id, personas, valor, modalidad, valor_minimo, moneda, vigente_desde)
            select id, %s, %s, %s, %s, 'COP', %s::date from servicios where codigo = %s
            on conflict (servicio_id, personas, vigente_desde) do update set
              valor = excluded.valor, modalidad = excluded.modalidad,
              valor_minimo = excluded.valor_minimo""",
                    (personas, valor, modalidad, minimo, FECHA_LISTA_PRECIOS, codigo))
    return len(SERVICIOS), len(TARIFAS), retirados


def sembrar_parametros(cur) -> int:
    for clave, valor, descripcion in PARAMETROS:
        # Solo si no existe: si la administradora ya lo cambió, no se pisa
        cur.execute("""insert into parametros (clave, valor, descripcion) values (%s, %s::jsonb, %s)
                       on conflict (clave) do nothing""", (clave, json.dumps(valor), descripcion))
    return len(PARAMETROS)


def main() -> None:
    cargar_env()
    url = os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://')
    with psycopg.connect(url) as con:
        cur = con.cursor()

        for codigo, nombre in ROLES:
            cur.execute("insert into roles (codigo, nombre) values (%s,%s) "
                        "on conflict (codigo) do nothing", (codigo, nombre))
        print(f'  roles                 {len(ROLES)}')

        n = 0
        for modulo in MODULOS:
            for accion in ACCIONES:
                cur.execute("""insert into permisos (codigo, nombre, modulo)
                               values (%s,%s,%s) on conflict (codigo) do nothing""",
                            (f'{modulo}.{accion}', f'{accion.capitalize()} {modulo}', modulo))
                n += 1
        print(f'  permisos              {n}')

        cur.execute('delete from roles_permisos')
        n = 0
        for rol, modulos in MATRIZ.items():
            for modulo, acciones in modulos.items():
                for accion in (ACCIONES if acciones == 'todo' else acciones):
                    cur.execute("""insert into roles_permisos (rol_id, permiso_id)
                                   select r.id, p.id from roles r, permisos p
                                   where r.codigo=%s and p.codigo=%s
                                   on conflict do nothing""", (rol, f'{modulo}.{accion}'))
                    n += cur.rowcount
        print(f'  roles_permisos        {n}')

        print(f'  paises                {paises_desde_datos(cur)}')

        for codigo, nombre in MODALIDADES:
            cur.execute("insert into modalidades (codigo,nombre) values (%s,%s) "
                        "on conflict (codigo) do nothing", (codigo, nombre))
        print(f'  modalidades           {len(MODALIDADES)}')

        servicios, tarifas, retirados = sembrar_catalogo(cur)
        print(f'  servicios             {servicios}  (lista de precios del {FECHA_LISTA_PRECIOS}; '
              f'{retirados} provisionales desactivados)')
        print(f'  tarifas               {tarifas}')
        print(f'  parametros            {sembrar_parametros(cur)}')

        for codigo, nombre in CANALES:
            cur.execute("insert into canales (codigo,nombre) values (%s,%s) "
                        "on conflict (codigo) do nothing", (codigo, nombre))
        print(f'  canales               {len(CANALES)}')

        for codigo, nombre in MOTIVOS_PERDIDA:
            cur.execute("insert into motivos_perdida (codigo,nombre) values (%s,%s) "
                        "on conflict (codigo) do nothing", (codigo, nombre))
        print(f'  motivos_perdida       {len(MOTIVOS_PERDIDA)}')

        for codigo, nombre in MEDIOS_PAGO:
            cur.execute("insert into medios_pago (codigo,nombre) values (%s,%s) "
                        "on conflict (codigo) do nothing", (codigo, nombre))
        print(f'  medios_pago           {len(MEDIOS_PAGO)}')

        for banco in ('Bancolombia', 'Davivienda', 'Nequi'):
            cur.execute("""insert into bancos_cuentas (banco) select %s
                           where not exists (select 1 from bancos_cuentas where banco=%s)""",
                        (banco, banco))
        print('  bancos_cuentas        3')

        for codigo, nombre in CATEGORIAS_GASTO:
            cur.execute("insert into categorias_gasto (codigo,nombre) values (%s,%s) "
                        "on conflict (codigo) do nothing", (codigo, nombre))
        print(f'  categorias_gasto      {len(CATEGORIAS_GASTO)}')

        n = 0
        for origen, destino in TRANSICIONES:
            cur.execute("""insert into transiciones_operativas
                             (estado_origen_id, estado_destino_id, requiere_checklist, campos_obligatorios)
                           select o.id, d.id, %s, %s::jsonb
                           from estados_operativos o, estados_operativos d
                           where o.codigo=%s and d.codigo=%s
                           on conflict do nothing""",
                        ((origen, destino) in CON_CHECKLIST,
                         json.dumps(OBLIGATORIOS.get((origen, destino), [])),
                         origen, destino))
            n += cur.rowcount
        print(f'  transiciones          {n}')

        try:
            n = 0
            for codigo, nombre, entidad, valor, unidad, reps, rol, sev in ALERTAS:
                cur.execute("""insert into alertas_tipos
                                 (codigo, nombre, entidad, anticipacion_valor,
                                  anticipacion_unidad, repeticiones, destinatario_rol_id,
                                  canal, severidad)
                               select %s,%s,%s,%s,%s,%s::jsonb, r.id, 'interna', %s
                               from roles r where r.codigo = %s
                               on conflict (codigo) do nothing""",
                            (codigo, nombre, entidad, valor, unidad,
                             json.dumps(reps), sev, rol))
                n += cur.rowcount
            print(f'  alertas_tipos         {n}')
        except psycopg.errors.UndefinedTable:
            con.rollback()
            print('  alertas_tipos         (tabla con otro nombre, revisar 002_brechas.sql)')
        except psycopg.errors.UndefinedColumn as e:
            con.rollback()
            print(f'  alertas_tipos         (columnas distintas: {str(e).splitlines()[0][:60]})')

        con.commit()
    print('\nSeed completo.')


if __name__ == '__main__':
    main()
