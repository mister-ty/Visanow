# Imagen de la API. Se construye desde la raiz del repositorio porque la
# migracion 0001 lee db/schema/ (esta a dos niveles por encima de alembic/).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    # El servidor corre en UTC; el negocio, en Bogota. Las fechas se guardan con zona.
    TZ=UTC

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY db db

# No corre como root: si alguien explota la API, no es dueno del contenedor
RUN useradd --system --create-home visanow && mkdir -p /app/almacenamiento \
    && chown -R visanow /app
USER visanow

WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/salud').status==200 else 1)"

# --proxy-headers: detras de Caddy la IP real del cliente viene en X-Forwarded-For
# y es la que se guarda en la auditoria y en el bloqueo por intentos.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "2"]
