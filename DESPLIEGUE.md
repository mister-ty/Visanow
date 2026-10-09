# Despliegue de VisaNow CRM

Entrada a produccion: 16/10/2026. Arquitectura: **frontend en Vercel**, **API + PostgreSQL + Caddy (HTTPS) en un servidor con Docker**.

> **Ensayado el 08/10/2026** en el portatil de desarrollo: imagen construida, contenedores arriba contra una base vacia, las 14 migraciones desde cero, seed, primer usuario y el ingreso completo (contrasena temporal, cambio, doble factor y rutas de negocio). Lo unico que NO se ha probado es Caddy con un dominio real, porque aqui no hay IP publica.
>
> El ensayo encontro dos cosas que impedian arrancar en produccion y ya estan corregidas:
>
> 1. `app/services/saas.py` importaba el diccionario de homologacion desde `app/migracion`, que queda fuera de la imagen a proposito. La API no levantaba: `ModuleNotFoundError: No module named 'app.migracion'`. El diccionario se movio a `app/core/homologacion.py`, que es donde corresponde: es conocimiento del catalogo, no maquinaria de migracion.
> 2. `app/seed.py` exigia un archivo `.env` que en produccion no existe —la configuracion viene por variables de entorno—, asi que el paso 6 fallaba y la base quedaba migrada y vacia, sin roles ni permisos, sin que nadie pudiera entrar.
>
> Tambien faltaba `.env.prod.example`, que el paso 4 manda copiar. Ya esta.

## Donde alojar la API (precios aproximados, verificar vigentes)

| Opcion | Costo aprox. | Para quien |
|---|---|---|
| **VPS con Docker** (Hetzner CX22, DigitalOcean/Vultr 2 GB) | USD 5 a 12 al mes | **Recomendada.** Control total, la base queda en el mismo servidor. Hay que hacer los respaldos. Es lo que describe este documento. |
| **Railway o Render** (API) + PostgreSQL administrado | USD 15 a 30 al mes | Sin administrar servidor; la base trae respaldos. Mas caro; el disco de archivos es un costo extra. |
| **Fly.io** + Postgres administrado | USD 15 a 35 al mes | Similar a la anterior; mas piezas que configurar. |

Elegir una region cercana a Colombia (Miami/Virginia) para la latencia. Vercel: el plan Hobby no permite uso comercial; usar **Pro (USD 20 al mes por usuario)**.

## Pasos (VPS Ubuntu 24.04)

1. **Servidor.** Crear el VPS, apuntar un registro DNS `A` (ej. `api.tudominio.com`) a su IP. Abrir solo los puertos 22, 80 y 443 (`ufw allow 22,80,443/tcp && ufw enable`).
2. **Docker.** `curl -fsSL https://get.docker.com | sh`
3. **Codigo.** `git clone <repositorio> /opt/visanow && cd /opt/visanow`
4. **Configuracion.** `cp .env.prod.example .env.prod && chmod 600 .env.prod`, y llenar cada variable (los comandos para generar secretos estan en el archivo). Guardar `CIFRADO_LLAVE` tambien fuera del servidor: sin ella no se pueden leer los datos cifrados.
5. **Subir.** `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`
6. **Base de datos y primer usuario** (una sola vez):
   ```bash
   docker compose -f docker-compose.prod.yml exec api python -m alembic upgrade head
   docker compose -f docker-compose.prod.yml exec api python -m app.seed
   docker compose -f docker-compose.prod.yml exec api python -m app.crear_admin --nombre "Nombre" --email correo@dominio.com
   ```
   Cada despliegue posterior que traiga migraciones repite solo `alembic upgrade head`.
7. **Ensayo.** `curl https://api.tudominio.com/salud` debe responder `{"estado":"ok","entorno":"produccion"}`. Entrar con la administradora y completar el doble factor.
8. **Frontend en Vercel.** Importar el repositorio con *Root Directory* = `ui`. Variable de entorno `VITE_API_URL=https://api.tudominio.com` (sin barra final). El `vercel.json` ya trae las cabeceras de seguridad y la reescritura a `index.html`. Asignar el dominio `crm.tudominio.com` y ponerlo en `URL_UI` del `.env.prod`; luego `docker compose ... up -d` para que la API acepte ese origen (CORS).

## Respaldos (no negociable)

Cron diario en el servidor, copiando fuera de el (almacenamiento de objetos o otro servidor):

```bash
0 2 * * * cd /opt/visanow && docker compose -f docker-compose.prod.yml exec -T db pg_dump -U visanow visanow | gzip > /var/backups/visanow-$(date +\%F).sql.gz
```

Guardar 14 dias como minimo y **probar una restauracion** antes de la salida: `gunzip -c respaldo.sql.gz | docker compose ... exec -T db psql -U visanow visanow`. El volumen `archivos` (comprobantes) tambien se respalda.

## Actualizar

```bash
cd /opt/visanow && git pull && docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml exec api python -m alembic upgrade head   # si hay migraciones nuevas
```

## Notas

- La API en produccion no expone `/docs` ni `/openapi.json` (solo con `APP_ENV=local`).
- El servidor corre en UTC; las fechas se guardan con zona y el negocio las muestra en America/Bogota.
- `backend/app/migracion/` queda fuera de la imagen a proposito: depende de archivos Excel con datos personales. La carga inicial de datos se corre desde la maquina que los tiene, apuntando `DATABASE_URL` a la base de produccion por tunel SSH.
- `apscheduler` figura en `requirements.txt` pero hoy el codigo no programa ninguna tarea. Si se agrega una, bajar `--workers` a 1 en el `Dockerfile` o se ejecutaria dos veces.
