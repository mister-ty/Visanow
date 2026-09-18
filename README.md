# visanow

CRM y sistema integral de gestión de VisaNow — MVP 1.

La documentación del proyecto (cronograma, requerimientos, diseño, migración)
vive en la carpeta padre. Este repositorio es solo el código.

## Arrancar en local

```bash
cp .env.example .env          # y llena DB_PASSWORD, APP_SECRET y CIFRADO_LLAVE
docker compose up -d db
python -m venv .venv && .venv/Scripts/activate      # Linux/Mac: source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
python -m alembic upgrade head
python -m app.seed
```

**El puerto de la base en el host es el 5435, no el 5432.** En la máquina de
desarrollo hay tres PostgreSQL nativos de Windows y uno ocupa el 5432: si se deja
el puerto por defecto, las conexiones llegan a la base equivocada y fallan con un
error de autenticación que parece de contraseña. Se cambia con `DB_PUERTO_HOST`.

## Esquema

El esquema se gobierna por SQL, no por `autogenerate` de Alembic: Alembic no
reproduce la columna generada `monto_neto`, los índices parciales ni las vistas.

| Archivo | Qué trae |
|---|---|
| `db/schema/001_nucleo.sql` | Las 27 tablas del núcleo |
| `db/schema/002_brechas.sql` | 23 tablas que los requerimientos exigen y el núcleo no tenía |
| `db/schema/003_correcciones.sql` | 7 defectos que dejaban entrar datos malos en silencio |

Total: 50 tablas, 2 vistas, 102 índices, 46 restricciones CHECK, 98 llaves foráneas.

## Reglas que no se rompen

1. **El saldo nunca es una columna.** Sale de `v_estado_financiero`.
2. **Los pagos son filas, no columnas.** Nunca `abono_1`, `abono_2`.
3. **El historial solo crece.** `casos_historial` no se actualiza ni se borra.
4. **Los routers no calculan nada.** El cálculo vive en `services/`, porque se
   necesita desde la API, desde la importación del SaaS y desde la migración.
5. **Los estados viven en la base de datos**, no en un `enum` de Python.
6. **Nada de `.xlsx` en el repositorio.** Los archivos fuente tienen pasaportes y
   credenciales de portales consulares: están fuera a propósito y el `.gitignore`
   los bloquea.
