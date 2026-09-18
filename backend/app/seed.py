"""Siembra los catálogos del sistema.

Los valores no se inventan: salen de los propios archivos de VisaNow, traducidos
con el diccionario de homologación de la actividad 0.5
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

SERVICIOS = [
    ('usa_premium',            'Asesoría USA Premium'),
    ('usa_estandar',           'Asesoría USA Estándar'),
    ('renovacion',             'Renovación'),
    ('analisis_perfil',        'Análisis de perfil'),
    ('preparacion_entrevista', 'Preparación para la entrevista'),
    ('busqueda_cita_serv',     'Adelanto / búsqueda de cita'),
    ('pago_consular',          'Pago de tasa consular'),
    ('pasaporte',              'Trámite de pasaporte'),
    ('envio_documentos',       'Envío y recolección de documentos'),
    ('representacion',         'Representación'),
    ('actualizacion_ds160',    'Actualización de DS-160'),
    ('visa_china',             'Visa China'),
    ('visa_uk',                'Visa Reino Unido'),
    ('visa_canada',            'Visa Canadá'),
    ('visa_australia',         'Visa Australia'),
    ('visa_schengen',          'Visa Schengen'),
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
    }
    for iso, nombre in NOMBRE.items():
        cur.execute("""insert into paises (iso2, nombre) values (%s, %s)
                       on conflict (iso2) do nothing""", (iso, nombre))
    return len(NOMBRE)


def tarifas_desde_excel(cur) -> int:
    """Lee las hojas PRECIOS y ' PRECIOS' de CUENTAS VISANOW y siembra tarifas."""
    ruta = RAIZ / os.environ.get('DATOS_FUENTE', '../02_Datos_Fuente') / 'CUENTAS VISANOW.xlsx'
    if not ruta.exists():
        print(f'  ! No se encontró {ruta.name}: las tarifas quedan sin sembrar.')
        return 0
    import warnings
    warnings.filterwarnings('ignore')
    import openpyxl

    MAPA = {
        'premium': 'usa_premium', 'asesoria premium': 'usa_premium',
        'usa visa': 'usa_estandar', 'usa estandar': 'usa_estandar',
        'asesoria estandar': 'usa_estandar', 'servicio estandar': 'usa_estandar',
        'renovacion': 'renovacion', 'renovacion premium': 'renovacion',
        'analisis de perfil': 'analisis_perfil', 'analisis': 'analisis_perfil',
        'preparacion entrevista': 'preparacion_entrevista', 'preparacion entre': 'preparacion_entrevista',
        'adelanto': 'busqueda_cita_serv', 'pago visa': 'pago_consular',
        'pasaporte': 'pasaporte', 'envio docu': 'envio_documentos',
        'visa china': 'visa_china', 'visa uk': 'visa_uk',
        'visa canada': 'visa_canada', 'visa australia': 'visa_australia',
    }
    wb = openpyxl.load_workbook(ruta, data_only=True)
    vistos, n = set(), 0
    for hoja in ('PRECIOS', ' PRECIOS'):
        if hoja not in wb.sheetnames:
            continue
        ws = wb[hoja]
        for fila in ws.iter_rows(min_row=2, values_only=True):
            if not fila or fila[0] is None:
                continue
            codigo = MAPA.get(norm(fila[0]))
            valor = fila[1] if len(fila) > 1 else None
            if not codigo or codigo in vistos or not isinstance(valor, (int, float)) or valor <= 0:
                continue
            cur.execute("""insert into tarifas (servicio_id, valor, moneda, vigente_desde)
                           select id, %s, 'COP', date '2026-01-01' from servicios where codigo = %s
                           and not exists (select 1 from tarifas t
                                           where t.servicio_id = servicios.id)""",
                        (round(float(valor), 2), codigo))
            if cur.rowcount:
                vistos.add(codigo)
                n += 1
    wb.close()
    return n


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

        for codigo, nombre in SERVICIOS:
            cur.execute("insert into servicios (codigo,nombre) values (%s,%s) "
                        "on conflict (codigo) do nothing", (codigo, nombre))
        print(f'  servicios             {len(SERVICIOS)}')

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

        print(f'  tarifas               {tarifas_desde_excel(cur)}  (desde CUENTAS VISANOW.xlsx)')
        con.commit()
    print('\nSeed completo.')


if __name__ == '__main__':
    main()
