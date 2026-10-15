"""Quitarle el permiso de lectura a los roles públicos de Supabase (RNF-10).

Hoy la base de producción está cerrada, y lo verifiqué entrando como `anon`
—que es exactamente lo que hace la API pública de Supabase— dentro de una
transacción que después descarté: `clientes` devolvió 0 de 895, `solicitantes` 0
y `usuarios` 0. Así que no hay un hueco abierto; esta migración es sobre por qué
está cerrado.

Está cerrado por una sola cosa: las tablas tienen RLS activo y **ninguna
política**. Un rol sujeto a RLS sin ninguna política que lo autorice no ve una
fila, y eso es comportamiento definido de PostgreSQL, no suerte. Pero el permiso
de SELECT sí está concedido: Supabase le da `grant all` sobre todo el esquema
`public` a `anon` y a `authenticated`, y además lo deja puesto como privilegio
por omisión, de modo que **cada tabla nueva lo hereda sola**.

Eso deja el sistema a un descuido de la catástrofe. Alcanza con que una
migración futura cree una tabla y se olvide del `enable row level security`
—dos líneas que es fácil no escribir— para que esa tabla quede legible por
internet con la llave anónima, que va en el navegador y no es secreta. Ya pasó
una variante: la 0015 cerró las 56 tablas y dejó las VISTAS afuera, y
`v_estado_financiero` siguió devolviendo las 477 ventas y los 65 millones de
cartera. Las tablas cerradas y la puerta de al lado abierta.

Hay una prueba que vigila el olvido (`test_toda_tabla_del_esquema_publico_tiene_rls`)
y está bien que exista. Pero una prueba es la primera barrera, no la única: lo
que hace esta migración es que el olvido deje de ser catastrófico. Sin el
permiso, una tabla sin RLS tampoco se lee. Pasa de «un error y son 895
pasaportes públicos» a «hacen falta dos errores independientes».

No rompe nada: la aplicación se conecta como `postgres`, que tiene `bypassrls`, y
en este proyecto no se usa nada de Supabase aparte de PostgreSQL —ni Auth, ni
Storage, ni Realtime, ni Edge Functions, y el frontend no trae `supabase-js`, va
contra la API de FastAPI por `VITE_API_URL`—. `anon` y `authenticated` no los usa
nadie.

Una cosa que no hace, y conviene decirla porque la primera versión la tenía y
era mentira: no le quita a estos roles el `usage` sobre el esquema `public`. Ese
permiso no lo tienen a título propio, lo tienen porque está concedido a `PUBLIC`
—o sea a todo el mundo—, así que un `revoke ... from anon` no se lo saca y
quedaría una línea que parece hacer algo y no hace nada. Tampoco hace falta:
entrar al esquema sin permiso sobre ninguna tabla no sirve para leer nada.
Verificado contra producción con esta misma migración: después de aplicarla
`anon` sigue entrando al esquema y pasa de poder leer 59 tablas a cero.

**Esto no se puede comprobar en la base local**, y conviene decirlo: `anon` y
`authenticated` son roles que crea Supabase y no existen en PostgreSQL de serie.
Por eso todo va dentro de un bloque que primero pregunta si el rol existe: en
desarrollo no hace nada y no falla, en Supabase hace el trabajo. La prueba
correspondiente se salta explícitamente en local en vez de pasar en falso, y el
estado real se verifica contra producción.

Revision ID: 0028_cerrar_los_roles_publicos
Revises: 0027_indice_pagos_por_negocio
Create Date: 2026-10-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0028_cerrar_los_roles_publicos'
down_revision: Union[str, None] = '0027_indice_pagos_por_negocio'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Los dos roles con los que PostgREST atiende a quien llega de internet: `anon`
#: sin sesión y `authenticated` con una sesión de Supabase Auth, que acá no se
#: usa. Ninguno de los dos tiene nada que hacer en esta base.
PUBLICOS = ('anon', 'authenticated')


def upgrade() -> None:
    for rol in PUBLICOS:
        # `if exists` sobre el rol, no sobre las tablas: en la base local estos
        # roles no existen y un `revoke` suelto fallaría con «role does not
        # exist», que dejaría la migración sin poder correr en desarrollo.
        op.execute(f"""
            do $$
            begin
              if exists (select 1 from pg_roles where rolname = '{rol}') then
                revoke all on all tables     in schema public from {rol};
                revoke all on all sequences  in schema public from {rol};
                revoke all on all routines   in schema public from {rol};

                -- Y lo que de verdad importa: que las tablas que se creen de
                -- aquí en adelante no vuelvan a nacer con el permiso puesto.
                -- Sin esto, la próxima migración que cree una tabla reabre el
                -- agujero sola, sin que nadie escriba un grant.
                alter default privileges in schema public revoke all on tables    from {rol};
                alter default privileges in schema public revoke all on sequences from {rol};
                alter default privileges in schema public revoke all on routines  from {rol};
              end if;
            end $$;
        """)


def downgrade() -> None:
    # Se devuelve lo que Supabase pone por omisión, para que bajar y volver a
    # subir deje la base como estaba y no como esta migración quiera.
    for rol in PUBLICOS:
        op.execute(f"""
            do $$
            begin
              if exists (select 1 from pg_roles where rolname = '{rol}') then
                grant all on all tables     in schema public to {rol};
                grant all on all sequences  in schema public to {rol};
                grant all on all routines   in schema public to {rol};
                alter default privileges in schema public grant all on tables    to {rol};
                alter default privileges in schema public grant all on sequences to {rol};
                alter default privileges in schema public grant all on routines  to {rol};
              end if;
            end $$;
        """)
