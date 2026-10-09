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
RUN chmod +x backend/arranque.sh
COPY db db

# No corre como root: si alguien explota la API, no es dueno del contenedor
RUN useradd --system --create-home visanow && mkdir -p /app/almacenamiento \
    && chown -R visanow /app
USER visanow

WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/salud').status==200 else 1)"

# El arranque migra, siembra y despues entrega el proceso a uvicorn. Va en un
# script y no aqui porque el plan gratuito de Render no da consola: si las
# migraciones no corren solas, la base queda sin tablas y no hay donde hacerlas.
# El script pasa --proxy-headers: detras de un proxy la IP real del cliente viene
# en X-Forwarded-For, y es la que se guarda en la auditoria y en el bloqueo por
# intentos fallidos.
CMD ["/app/backend/arranque.sh"]
