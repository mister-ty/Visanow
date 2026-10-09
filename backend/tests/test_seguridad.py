"""Que una tabla nueva no vuelva a abrir la puerta (RNF-10).

Supabase publica el esquema `public` por internet con PostgREST. Una tabla sin
«row level security» queda legible con la llave anonima, que va en el codigo del
navegador y no es secreta. La migracion 0015 cerro las que existian ese dia;
esta prueba se encarga de las que vengan despues, que es donde se cuela el
descuido: nada falla, nadie se entera, y los datos quedan a la vista.
"""
from sqlalchemy import text

# `alembic_version` no tiene datos de nadie: solo dice en que migracion va la
# base. No vale la pena cerrarla y dejarla fuera hace la intencion explicita.
SIN_RLS_A_PROPOSITO = {'alembic_version'}


def test_toda_tabla_del_esquema_publico_tiene_rls(db):
    abiertas = [f for (f,) in db.execute(text("""
        select c.relname
          from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind = 'r'
           and not c.relrowsecurity
         order by c.relname"""))]
    sobran = sorted(set(abiertas) - SIN_RLS_A_PROPOSITO)
    assert not sobran, (
        'Estas tablas quedarian legibles con la llave anonima de Supabase: '
        + ', '.join(sobran)
        + '. Agregue `alter table <tabla> enable row level security` a la migracion '
          'que las creo.')


def test_ninguna_tabla_tiene_politicas_que_abran_la_api(db):
    """RLS activa pero con una politica permisiva es lo mismo que nada.

    VisaNow no usa la API de Supabase: habla con PostgreSQL por conexion directa.
    Asi que no deberia existir ninguna politica, y si aparece una es que alguien
    abrio algo sin querer.
    """
    politicas = [f'{e}.{t}: {p}' for e, t, p in db.execute(text("""
        select schemaname, tablename, policyname from pg_policies
         where schemaname = 'public' order by tablename"""))]
    assert not politicas, ('Hay politicas de RLS en public y no deberia haber ninguna: '
                           + '; '.join(politicas))
