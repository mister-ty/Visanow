"""Punto de entrada de la API.

    uvicorn app.main:app --reload
"""
import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin import montar_admin
from app.api.v1 import (auth, casos, catalogos, clientes, fichas, oportunidades,
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


for modulo in (auth, casos, catalogos, clientes, fichas, oportunidades, usuarios,
               ventas):
    app.include_router(modulo.router, prefix='/api/v1')

montar_admin(app)


@app.get('/salud', tags=['sistema'])
def salud(db: Session = Depends(get_db)):
    db.execute(text('select 1'))
    return {'estado': 'ok', 'entorno': ajustes().app_env}
