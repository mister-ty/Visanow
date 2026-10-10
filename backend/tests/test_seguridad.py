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
        'id', 'cliente_contacto_id', 'creado_en', 'origen_archivo', 'origen_hoja',
        'origen_fila'},
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
