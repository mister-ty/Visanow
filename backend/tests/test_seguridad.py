"""Que nada vuelva a quedar legible con la llave anonima (RNF-10).

Supabase publica el esquema `public` por internet con PostgREST. La llave
anonima va en el codigo del navegador y no es secreta, asi que todo lo que ese
rol pueda leer es publico.

Estas pruebas existen porque el hueco ya se abrio una vez, y de la forma menos
evidente: la migracion 0015 cerro las 56 tablas con RLS, pero las VISTAS se
quedaron por fuera. Una vista en PostgreSQL corre por omision con los permisos
de quien la creo, no de quien pregunta, asi que `v_estado_financiero` y
`v_cartera` seguian devolviendo las 477 ventas y los 65 millones de cartera.
Las tablas cerradas y la puerta de al lado abierta.
"""
import pytest
from sqlalchemy import text


def test_toda_tabla_del_esquema_publico_tiene_rls(db):
    abiertas = [f for (f,) in db.execute(text("""
        select c.relname
          from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind = 'r'
           and not c.relrowsecurity
         order by c.relname"""))]
    assert not abiertas, (
        'Estas tablas quedarian legibles con la llave anonima de Supabase: '
        + ', '.join(abiertas)
        + '. Agregue `alter table <tabla> enable row level security` a la migracion '
          'que las creo.')


def test_toda_vista_corre_con_los_permisos_de_quien_pregunta(db):
    """Sin `security_invoker`, una vista se salta el RLS de sus tablas.

    Es el defecto que ya paso: no basta con cerrar las tablas.
    """
    sin_invoker = [f for (f,) in db.execute(text("""
        select c.relname
          from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind = 'v'
           and coalesce((select option_value from pg_options_to_table(c.reloptions)
                          where option_name = 'security_invoker'), 'false') <> 'true'
         order by c.relname"""))]
    assert not sin_invoker, (
        'Estas vistas se saltan el RLS de sus tablas y quedarian legibles con la llave '
        'anonima: ' + ', '.join(sin_invoker)
        + '. Agregue `alter view <vista> set (security_invoker = true)`.')


def test_ninguna_tabla_tiene_politicas_que_abran_la_api(db):
    """RLS activa pero con una politica permisiva es lo mismo que nada.

    VisaNow no usa la API de Supabase: habla con PostgreSQL por conexion directa.
    Asi que no deberia existir ninguna politica, y si aparece una es que alguien
    abrio algo sin querer.
    """
    politicas = [f'{t}: {p}' for t, p in db.execute(text("""
        select tablename, policyname from pg_policies
         where schemaname = 'public' order by tablename"""))]
    assert not politicas, ('Hay politicas de RLS en public y no deberia haber ninguna: '
                           + '; '.join(politicas))


#: Los dos roles con los que PostgREST atiende a quien llega de internet.
PUBLICOS = ('anon', 'authenticated')


def test_los_roles_publicos_de_supabase_no_pueden_leer_nada(db):
    """Que el candado no dependa solo de que no haya politicas (migracion 0028).

    RLS activa sin politicas ya deja a estos roles sin ver una fila, y eso es
    comportamiento definido de PostgreSQL. Pero Supabase les concede `grant all`
    sobre el esquema entero y lo deja como privilegio por omision, asi que cada
    tabla nueva nace con el permiso puesto. Con eso, olvidar un `enable row
    level security` en una migracion no es un descuido: es publicar 895
    pasaportes. La 0028 les quita el permiso para que hagan falta DOS errores.
    """
    existen = [r for (r,) in db.execute(text(
        'select rolname from pg_roles where rolname = any(:roles)'),
        {'roles': list(PUBLICOS)})]
    if not existen:
        pytest.skip(
            'anon y authenticated los crea Supabase y no existen en la base local, '
            'asi que aqui no hay nada que comprobar. Esto se verifica contra '
            'produccion; la migracion 0028 explica por que y se salta sola si el '
            'rol no esta. Se avisa en vez de pasar en verde: una prueba que se '
            'cumple sin comprobar es peor que una que falta.')

    con_permiso = [f'{rol} -> {tabla}' for rol, tabla in db.execute(text("""
        select r.rolname, c.relname
          from pg_roles r
          cross join pg_class c
          join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind = 'r'
           and r.rolname = any(:roles)
           and has_table_privilege(r.rolname, c.oid, 'select')
         order by r.rolname, c.relname"""), {'roles': existen})]
    assert not con_permiso, (
        'Estos roles publicos de Supabase pueden leer estas tablas. Hoy no ven '
        'filas porque no hay politicas de RLS, pero el dia que falte un `enable '
        'row level security` quedan legibles por internet: ' + '; '.join(con_permiso[:20]))


def test_una_tabla_nueva_no_nace_con_el_permiso_puesto(db):
    """La mitad de la 0028 que de verdad hace el trabajo, probada en local.

    Lo que importa no es quitar el permiso de hoy -eso se vuelve a poner solo-
    sino quitar el privilegio POR OMISION, que es lo que hace que cada tabla
    nueva nazca abierta. Como anon y authenticated no existen en la base local,
    esto se prueba con un rol desechable montado igual que lo monta Supabase.

    La primera afirmacion es la que impide que la prueba sea de adorno: antes de
    comprobar que el arreglo funciona, comprueba que el montaje reproduce de
    verdad el problema.
    """
    db.execute(text('drop role if exists rol_publico_desechable'))
    db.execute(text('create role rol_publico_desechable nologin'))
    db.execute(text('grant usage on schema public to rol_publico_desechable'))
    db.execute(text('alter default privileges in schema public '
                    'grant all on tables to rol_publico_desechable'))

    db.execute(text('create table tabla_antes_del_arreglo (id int)'))
    assert db.scalar(text("select has_table_privilege('rol_publico_desechable', "
                          "'tabla_antes_del_arreglo', 'select')")) is True, (
        'el montaje no reproduce lo que hace Supabase, asi que lo de abajo no '
        'probaria nada')

    # Y esto es lo que hace la migracion 0028.
    db.execute(text('revoke all on all tables in schema public '
                    'from rol_publico_desechable'))
    db.execute(text('alter default privileges in schema public '
                    'revoke all on tables from rol_publico_desechable'))
    db.execute(text('create table tabla_despues_del_arreglo (id int)'))

    assert db.scalar(text("select has_table_privilege('rol_publico_desechable', "
                          "'tabla_antes_del_arreglo', 'select')")) is False, (
        'no se le quito el permiso a las tablas que ya existian')
    assert db.scalar(text("select has_table_privilege('rol_publico_desechable', "
                          "'tabla_despues_del_arreglo', 'select')")) is False, (
        'una tabla creada DESPUES sigue naciendo con el permiso: falta el '
        '`alter default privileges ... revoke`, que es la mitad que importa')


def test_las_funciones_tienen_search_path_fijo(db):
    """Una funcion sin `search_path` resuelve nombres contra un esquema que el
    llamante puede controlar. En `auditoria_inalterable` importa de verdad: es
    la que impide modificar la auditoria (RNF-05)."""
    sueltas = [f for (f,) in db.execute(text("""
        select p.proname
          from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and p.prokind = 'f'
           -- Solo las nuestras: citext, pg_trgm y unaccent instalan las suyas en
           -- public y no son nuestras para andar modificandolas.
           and not exists (select 1 from pg_depend d
                            where d.objid = p.oid and d.deptype = 'e')
           and not exists (select 1 from unnest(coalesce(p.proconfig, '{}'))
                            as c(x) where x like 'search_path=%')
         order by p.proname"""))]
    assert not sueltas, ('Estas funciones no tienen search_path fijo: '
                         + ', '.join(sueltas)
                         + '. Agregue `alter function <f> set search_path = pg_catalog, public`.')


# --------------------------- lo que la auditoria puede y no puede guardar

#: Columnas de las tablas con datos personales que NO identifican a nadie y por
#: eso si se escriben completas en la auditoria. Es una lista a proposito: si
#: manana alguien agrega una columna, la prueba de abajo falla y hay que decidir
#: de que lado va. Una columna nueva con el telefono de la persona que se cuele
#: sin que nadie lo note es exactamente lo que esta prueba existe para impedir.
NO_IDENTIFICAN = {
    'clientes': {
        'id', 'tipo_documento', 'ciudad', 'pais_id', 'canal_id', 'consentimiento',
        'consentimiento_fecha', 'archivado', 'creado_por', 'creado_en', 'actualizado_en',
        'ultimo_contacto_en', 'origen_archivo', 'origen_hoja', 'origen_fila',
        'migrado_en', 'fusionado_en_id'},
    'solicitantes': {
        'id', 'grupo_id', 'cliente_id', 'tipo_documento', 'nacionalidad',
        'relacion_con_cliente', 'creado_en', 'origen_archivo', 'origen_hoja',
        'origen_fila', 'migrado_en', 'fusionado_en_id'},
    'casos': {
        'id', 'negocio_id', 'solicitante_id', 'pais_id', 'tipo_visa_id', 'modalidad_id',
        'sede_id', 'fuente', 'id_externo', 'sincronizado_en', 'estado_id',
        'responsable_id', 'resultado', 'resultado_fecha', 'ultima_actividad_en',
        'creado_en', 'origen_archivo', 'origen_hoja', 'origen_fila', 'migrado_en',
        'ds160_enviado_en', 'busqueda_citas', 'etapa_saas', 'proxima_accion',
        'proxima_accion_fecha'},
    'usuarios': {
        'id', 'password_hash', 'rol_id', 'activo', 'mfa_habilitado', 'mfa_secreto',
        'ultimo_acceso', 'creado_en', 'alcance', 'intentos_fallidos', 'bloqueado_hasta',
        'password_cambiado_en', 'debe_cambiar_password'},
    'grupos': {
        # «familiar» o «de viaje» no dice nada de nadie: es una clasificacion
        # del grupo, no de las personas. El NOMBRE si, porque es el apellido de
        # una familia, y por eso ese va oculto.
        'id', 'cliente_contacto_id', 'tipo', 'creado_en', 'origen_archivo', 'origen_hoja',
        'origen_fila'},
    # --- Las entidades que entraron al enmascarado el 15/10. Lo que lleva texto
    # de una persona quedo en DATOS_PERSONALES; esto es lo demas, revisado
    # columna por columna. Dos que vale aclarar porque el nombre engana:
    # `actividades.direccion` es «entrante» o «saliente», no una direccion de
    # casa; y `conflictos_sincronizacion.campo` es el NOMBRE del campo en
    # disputa, no su valor -los dos valores si se enmascaran-.
    'actividades': {
        'id', 'entidad', 'entidad_id', 'tipo', 'direccion', 'documento_id',
        'ocurrido_en', 'creado_en', 'usuario_id', 'origen_archivo', 'origen_hoja',
        'origen_fila'},
    'pagos': {
        'id', 'negocio_id', 'fecha', 'monto_bruto', 'monto_neto', 'costo_medio',
        'moneda', 'estado', 'medio_pago_id', 'banco_cuenta_id', 'registrado_por',
        'creado_en', 'migrado_en', 'origen_archivo', 'origen_hoja', 'origen_fila'},
    'tareas': {
        'id', 'responsable_id', 'prioridad', 'estado', 'origen', 'caso_id',
        'negocio_id', 'oportunidad_id', 'cliente_id', 'vence_en', 'cerrada_en',
        'creado_en', 'creado_por'},
    'documentos': {
        'id', 'entidad', 'entidad_id', 'tipo', 'almacenamiento', 'mime', 'sha256',
        'tamano_bytes', 'restringido', 'subido_por', 'creado_en'},
    'movimientos_banco': {
        'id', 'banco', 'banco_cuenta_id', 'fecha', 'valor', 'moneda', 'estado',
        'huella', 'pago_id', 'duplicado_de_id', 'conciliado_en', 'conciliado_por',
        'creado_en', 'origen_archivo', 'origen_hoja', 'origen_fila'},
    'negocios': {
        'id', 'cliente_id', 'grupo_id', 'oportunidad_id', 'servicio_id', 'canal_id',
        'vendedor_id', 'cantidad_solicitantes', 'valor_lista', 'valor_pactado',
        'descuento', 'moneda', 'fecha_venta', 'negocio_principal_id', 'creado_en',
        'migrado_en', 'origen_archivo', 'origen_hoja', 'origen_fila'},
    'oportunidades': {
        'id', 'cliente_id', 'servicio_id', 'pais_id', 'canal_id', 'campania',
        'campania_id', 'asesor_id', 'estado_id', 'valor_estimado',
        'motivo_perdida_id', 'referido_por_cliente_id', 'proxima_accion_fecha',
        'ultimo_contacto_en', 'cerrado_en', 'creado_en'},
    'citas': {
        'id', 'caso_id', 'tipo', 'sede_id', 'inicia_en', 'zona_horaria', 'estado',
        'creado_en', 'origen_archivo', 'origen_hoja', 'origen_fila'},
    'gastos': {
        'id', 'caso_id', 'negocio_id', 'categoria_id', 'proveedor_id', 'fecha',
        'monto', 'moneda', 'estado', 'medio_pago_id', 'banco_cuenta_id',
        'registrado_por', 'creado_en'},
    'alertas': {
        'id', 'tipo_id', 'estado', 'caso_id', 'negocio_id', 'oportunidad_id',
        'cita_id', 'tarea_id', 'destinatario_id', 'generada_en', 'vence_en',
        'pospuesta_hasta', 'resuelta_en', 'resuelta_por'},
    'conflictos_sincronizacion': {
        'id', 'importacion_id', 'caso_id', 'campo', 'estado', 'detectado_en',
        'resuelto_en', 'resuelto_por'},
    'importaciones': {
        'id', 'origen', 'archivo_sha256', 'estado', 'filas_totales', 'nuevos',
        'actualizados', 'sin_cambios', 'rechazados', 'conflictos', 'iniciada_en',
        'aplicada_en', 'ejecutada_por'},
    'liquidaciones_comision': {
        'id', 'vendedor_id', 'periodo', 'cantidad', 'total', 'estado', 'creada_en',
        'liquidada_por', 'pagada_en'},
    'cuotas_negocio': {
        'id', 'negocio_id', 'numero', 'monto', 'fecha_pactada', 'creado_en',
        'origen_archivo', 'origen_hoja', 'origen_fila'},
    'ajustes_negocio': {
        'id', 'negocio_id', 'tipo', 'monto', 'fecha', 'autorizado_por', 'creado_en'},
    # Y las que se declararon con el conjunto vacio en DATOS_PERSONALES: no
    # llevan nada de nadie, pero sus columnas tambien hay que clasificarlas.
    'comisiones': {
        'id', 'negocio_id', 'vendedor_id', 'periodo', 'base_calculo', 'monto',
        'regla_id', 'regla_aplicada', 'estado', 'liquidacion_id', 'creado_en'},
    'casos_colaboradores': {'caso_id', 'usuario_id', 'agregado_en', 'agregado_por'},
    'roles_permisos': {'rol_id', 'permiso_id'},
    # Son plantillas, con marcadores de posicion: el cuerpo no es de nadie.
    'plantillas_mensaje': {
        'id', 'evento', 'nombre', 'canal', 'asunto', 'cuerpo', 'activa', 'creada_en',
        'creada_por', 'actualizada_en'},
    'alertas_tipos': {
        'id', 'codigo', 'nombre', 'entidad', 'anticipacion_valor',
        'anticipacion_unidad', 'repeticiones', 'canal', 'severidad', 'activo',
        'destinatario_rol_id'},
}


def test_toda_columna_de_una_tabla_con_datos_personales_esta_clasificada(db):
    """Cada columna esta o en la lista de lo que se oculta o en la de lo que no
    identifica. Ninguna puede quedar sin decidir.

    La auditoria es inalterable: lo que entre ahi sobrevive a cualquier
    anonimizacion posterior. Una columna nueva que se cuele sin clasificar se
    empieza a guardar en claro y ya no se puede sacar.
    """
    from app.services.auditoria import DATOS_PERSONALES

    for tabla, ocultas in DATOS_PERSONALES.items():
        reales = {r[0] for r in db.execute(text(
            'select column_name from information_schema.columns where table_name = :t'),
            {'t': tabla})}
        assert reales, f'la tabla {tabla} no existe'
        clasificadas = ocultas | NO_IDENTIFICAN.get(tabla, set())
        sin_decidir = reales - clasificadas
        assert not sin_decidir, (
            f'en «{tabla}» hay columnas sin clasificar: {sorted(sin_decidir)}. '
            f'Decida si identifican a alguien -y van a DATOS_PERSONALES en '
            f'app/services/auditoria.py- o no -y van a NO_IDENTIFICAN aca-.')
        fantasmas = ocultas - reales
        assert not fantasmas, (
            f'«{tabla}» oculta columnas que ya no existen: {sorted(fantasmas)}')


def test_una_variable_pegada_con_salto_de_linea_no_tumba_el_arranque():
    """El primer despliegue en Render murio por esto.

    El DATABASE_URL se pego en el formulario con un salto de linea al final, y
    Postgres contesto:

        FATAL: database "postgres
        " does not exist

    -la comilla de cierre en el renglon siguiente es todo el sintoma-. Pegar una
    cadena en un formulario web y que se cuele el retorno es lo mas normal del
    mundo; que eso tumbe el despliegue con un error que nadie puede leer, no.

    Un valor con espacios de sobra nunca es el que se quiso poner, asi que
    recortarlo no esconde ningun error de verdad.
    """
    from app.core.config import Ajustes

    sucio = Ajustes(
        app_secret='  ' + 'x' * 40 + '\n',
        database_url='postgresql+psycopg://u:p@host:5432/postgres\n',
        cifrado_llave='y' * 44 + '\r\n',
        cors_origins=' https://visanow.vercel.app \n',
        url_ui='https://visanow.vercel.app\r\n',
    )
    assert sucio.database_url.endswith('/postgres'), repr(sucio.database_url)
    assert sucio.app_secret == 'x' * 40
    assert sucio.cifrado_llave == 'y' * 44
    assert sucio.url_ui == 'https://visanow.vercel.app'
    assert sucio.origenes_cors == ['https://visanow.vercel.app']


def test_salud_dice_que_version_esta_corriendo(cliente, monkeypatch):
    """Despues de desplegar la pregunta siempre es «¿ya quedo lo que subi o
    sigue lo de antes?». Sin esto hay que ir al tablero del proveedor."""
    monkeypatch.setenv('RENDER_GIT_COMMIT', '8a99bfe1234567890abcdef')
    d = cliente.get('/salud').json()
    assert d['estado'] == 'ok'
    assert d['version'] == '8a99bfe', d
    assert d['migracion'], 'y en que migracion quedo la base'

    monkeypatch.delenv('RENDER_GIT_COMMIT')
    assert cliente.get('/salud').json()['version'] == 'desconocida', (
        'fuera de Render no se inventa una version')


# ------------------- lo que entra en la auditoria se queda para siempre

def test_toda_entidad_que_se_audita_esta_declarada_en_el_enmascarado():
    """La auditoria no se puede borrar, asi que un dato personal que entra se queda.

    `sin_datos_personales` enmascara POR ENTIDAD, y el diccionario tenia cinco
    cuando se auditan veintiocho. Las que faltaban volcaban la fila entera:
    `actividades` guardaba el cuerpo de lo que se le dijo al cliente, `pagos` el
    nombre de quien consigno con su observacion y su referencia. Un trigger
    impide modificar esa tabla (RNF-05), que es justo lo que hace que esto no se
    pueda arreglar despues.

    Esta prueba no decide que se enmascara: exige que alguien lo haya DECIDIDO.
    Una entidad nueva, aunque se declare con el conjunto vacio, obliga a mirar
    sus columnas; sin esto, una tabla nueva filtra sola y nadie se entera.
    """
    import pathlib
    import re

    from app.services.auditoria import DATOS_PERSONALES

    #: Los documentos se auditan nombrando la entidad de la que cuelgan, en
    #: singular. No son tablas: se resuelven a la suya.
    ALIAS = {'cliente': 'clientes', 'solicitante': 'solicitantes',
             'caso': 'casos', 'negocio': 'negocios'}

    app_dir = pathlib.Path(__file__).resolve().parents[1] / 'app'
    auditadas = set()
    for archivo in sorted(app_dir.rglob('*.py')):
        if 'migracion' in archivo.parts:   # herramienta de una sola corrida
            continue
        texto = archivo.read_text(encoding='utf-8')
        for m in re.finditer(r"""entidad=['"]([a-z_]+)['"]""", texto):
            auditadas.add(ALIAS.get(m.group(1), m.group(1)))

    assert auditadas, 'no se encontro ninguna llamada a auditar; la prueba no mira nada'
    sin_declarar = sorted(auditadas - set(DATOS_PERSONALES))
    assert not sin_declarar, (
        f'Estas entidades se auditan y nadie decidio que se les enmascara: '
        f'{sin_declarar}. Revise sus columnas de texto y agreguelas a '
        f'DATOS_PERSONALES en app/services/auditoria.py, con el conjunto vacio '
        f'si de verdad no llevan datos de nadie.')
