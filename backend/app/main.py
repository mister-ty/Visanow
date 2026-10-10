"""Punto de entrada de la API.

    uvicorn app.main:app --reload
"""
import logging
import os

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin import montar_admin
from app.api.v1 import (auditoria, auth, casos, catalogos, clientes, conciliacion, costos,
                        exportar, fichas,
                        oportunidades, pagos, plantillas, retencion, saas, tableros,
                        trabajo,
                        usuarios, ventas)
from app.core.config import ajustes
from app.core.errores import ErrorDominio
from app.db.session import get_db

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')

_local = ajustes().es_local
app = FastAPI(
    title='VisaNow API', version='0.1.0',
    # La documentación interactiva expone el contrato completo: solo en local
    docs_url='/docs' if _local else None, redoc_url=None,
    openapi_url='/openapi.json' if _local else None,
)
app.add_middleware(CORSMiddleware, allow_origins=ajustes().origenes_cors, allow_credentials=True,
                   allow_methods=['*'], allow_headers=['*'])


@app.exception_handler(ErrorDominio)
def _error_dominio(_: Request, e: ErrorDominio) -> JSONResponse:
    return JSONResponse(status_code=e.http, content={'detalle': e.mensaje, 'codigo': e.codigo})


@app.exception_handler(RequestValidationError)
def _error_validacion(_: Request, e: RequestValidationError) -> JSONResponse:
    errores = [{'campo': '.'.join(str(p) for p in err['loc'][1:]), 'mensaje': err['msg']}
               for err in e.errors()]
    return JSONResponse(status_code=422, content={'detalle': 'Datos inválidos.',
                                                  'codigo': 'validacion', 'errores': errores})


for modulo in (auditoria, auth, casos, catalogos, clientes, conciliacion, costos,
               exportar, fichas,
               oportunidades, pagos, plantillas, retencion, saas, tableros, trabajo,
               usuarios,
               ventas):
    app.include_router(modulo.router, prefix='/api/v1')

montar_admin(app)


@app.get('/salud', tags=['sistema'])
def salud(db: Session = Depends(get_db)):
    """Que la aplicacion responde, que alcanza la base, y QUE VERSION es.

    Lo ultimo no es un adorno. Despues de desplegar, la pregunta siempre es «¿ya
    quedo lo que acabo de subir o sigue lo de antes?», y sin esto hay que ir a
    buscarlo al tablero del proveedor. `RENDER_GIT_COMMIT` la pone Render sola;
    fuera de Render no existe y sale «desconocida», que es la respuesta honesta.

    No revela nada: el repositorio y sus commits ya se saben.
    """
    db.execute(text('select 1'))
    commit = os.environ.get('RENDER_GIT_COMMIT') or os.environ.get('GIT_COMMIT')
    return {
        'estado': 'ok',
        'entorno': ajustes().app_env,
        'version': commit[:7] if commit else 'desconocida',
        'migracion': db.execute(text('select version_num from alembic_version')).scalar(),
    }
