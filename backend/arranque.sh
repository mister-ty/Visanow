#!/bin/sh
# Arranque de la API. Migra, siembra y, si se le pide, crea la primera
# administradora; después entrega el proceso a uvicorn.
#
# Esto existe porque en Render el plan gratuito no da consola: no hay dónde
# correr `alembic upgrade head` a mano, así que si no se hace aquí la base queda
# sin tablas y la API responde 500 a todo sin decir por qué.
#
# Las tres operaciones son idempotentes, así que arrancar cien veces es igual
# que arrancar una. Y van ANTES de uvicorn a propósito: uvicorn bifurca sus
# trabajadores después, así que la migración corre una sola vez y no dos
# procesos compitiendo por la misma tabla.
set -e

# Sin esto, la falta de DATABASE_URL sale como un traceback de treinta lineas de
# alembic que termina en KeyError, y no le dice a nadie que hacer. Es el error
# mas probable del primer despliegue: el blueprint la deja en blanco a proposito
# porque lleva la clave de la base.
if [ -z "$DATABASE_URL" ]; then
  echo "[arranque] FALTA LA VARIABLE DATABASE_URL."
  echo "[arranque]"
  echo "[arranque] Es la cadena de conexion de la base. En Render se pone en"
  echo "[arranque] Environment > Environment Variables, con la clave DATABASE_URL."
  echo "[arranque] Si la base es Supabase, use la del Session pooler (puerto 5432),"
  echo "[arranque] no la de transacciones, y cambie el prefijo postgresql:// por"
  echo "[arranque] postgresql+psycopg://"
  exit 1
fi

echo "[arranque] migrando la base..."
python -m alembic upgrade head

echo "[arranque] sembrando el catálogo..."
python -m app.seed

# La primera administradora solo si se pidió por variable de entorno. La
# contraseña temporal sale en el log: es la única forma de entregarla cuando no
# hay consola, y por eso conviene quitar la variable y volver a desplegar
# después del primer ingreso.
if [ -n "$ADMIN_INICIAL_EMAIL" ]; then
  echo "[arranque] primera administradora..."
  python -m app.crear_admin \
      --nombre "${ADMIN_INICIAL_NOMBRE:-Administradora}" \
      --email "$ADMIN_INICIAL_EMAIL" \
    || echo "[arranque] ya existe una administradora: no se crea otra."
fi

# Render entrega el puerto en PORT; el compose del VPS no la define y usa 8000.
PUERTO="${PORT:-8000}"
# Un trabajador por defecto: en el plan gratuito de Render hay 512 MB y dos
# trabajadores se quedan sin memoria a mitad de una consulta grande.
TRABAJADORES="${WEB_CONCURRENCY:-1}"

echo "[arranque] uvicorn en el puerto $PUERTO con $TRABAJADORES trabajador(es)"
exec uvicorn app.main:app \
    --host 0.0.0.0 --port "$PUERTO" \
    --proxy-headers --forwarded-allow-ips '*' \
    --workers "$TRABAJADORES"
