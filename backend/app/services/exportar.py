"""Exportar listas a Excel o CSV, según quién pregunta (RF-075, RNF-07).

Exportar es la forma más fácil de sacar datos de un sistema, y por eso es donde
los controles se suelen olvidar: la pantalla esconde los montos a quien no debe
verlos, y después el botón de «descargar» los entrega en un archivo. Acá no.

**Las columnas se filtran por permiso, no solo las filas.** Cada recurso declara
qué columnas son sensibles y qué permiso hace falta para verlas. Quien no lo
tiene recibe el archivo sin esas columnas, no un error: operaciones necesita la
lista de trámites para trabajar, lo que no necesita es cuánto pagó cada cliente.

**El alcance se aplica igual que en la pantalla** (RNF-03). Quien solo ve sus
trámites exporta sus trámites.

**Queda registrado quién exportó qué** (RNF-07). Un archivo con 866 personas
sale del sistema y deja de estar bajo su control: lo mínimo es saber quién lo
sacó, cuándo, con qué filtros y cuántas filas. La tabla `exportaciones` existe
desde el núcleo y hasta hoy nadie escribía en ella.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import permisos_de_rol
from app.core.errores import Conflicto, Invalido, Prohibido
from app.models.esquema import Exportaciones, Usuarios

BOGOTA = ZoneInfo('America/Bogota')
FORMATOS = ('xlsx', 'csv')
# Una exportacion sin tope es una forma de vaciar la base en una peticion. Con
# 866 personas hoy no se nota; el tope es para el dia que si.
MAX_FILAS = 50_000


@dataclass
class Columna:
    """Una columna del archivo. `permiso` la vuelve condicional."""
    campo: str
    titulo: str
    permiso: str | None = None


@dataclass
class Recurso:
    """Qué se puede exportar y con qué llave."""
    nombre: str
    permiso: str
    sql: str
    columnas: list[Columna]
    # Cómo se limita cuando el usuario no lo ve todo. None = no aplica alcance.
    filtro_alcance: str | None = None
    sensible: bool = True
    field_orden: str = field(default='1')


# El `:alcance` de cada consulta se reemplaza por la condición o por `true`.
RECURSOS: dict[str, Recurso] = {
    'clientes': Recurso(
        nombre='clientes', permiso='clientes.exportar',
        sql="""select c.id, c.nombre, c.tipo_documento, c.numero_documento, c.telefono,
                      c.email::text as email, c.ciudad, ca.nombre as canal,
                      c.creado_en::date as creado
                 from clientes c left join canales ca on ca.id = c.canal_id
                where c.fusionado_en_id is null and c.archivado = false
                order by c.nombre""",
        columnas=[
            Columna('id', 'ID'), Columna('nombre', 'Cliente'),
            Columna('tipo_documento', 'Tipo doc.'),
            Columna('numero_documento', 'Documento', 'clientes.ver'),
            Columna('telefono', 'Teléfono'), Columna('email', 'Correo'),
            Columna('ciudad', 'Ciudad'), Columna('canal', 'Canal'),
            Columna('creado', 'Creado')]),

    'solicitantes': Recurso(
        nombre='solicitantes', permiso='solicitantes.exportar',
        sql="""select s.id, s.nombre, c.nombre as cliente, s.tipo_documento,
                      s.numero_documento, s.pasaporte, s.fecha_nacimiento,
                      s.nacionalidad, s.telefono, s.email::text as email
                 from solicitantes s left join clientes c on c.id = s.cliente_id
                where s.fusionado_en_id is null
                order by s.nombre""",
        columnas=[
            Columna('id', 'ID'), Columna('nombre', 'Solicitante'),
            Columna('cliente', 'Cliente'), Columna('tipo_documento', 'Tipo doc.'),
            Columna('numero_documento', 'Documento', 'solicitantes.ver'),
            # El pasaporte es el dato mas sensible que guarda el sistema.
            Columna('pasaporte', 'Pasaporte', 'solicitantes.exportar'),
            Columna('fecha_nacimiento', 'Nacimiento'),
            Columna('nacionalidad', 'Nacionalidad'),
            Columna('telefono', 'Teléfono'), Columna('email', 'Correo')]),

    'casos': Recurso(
        nombre='casos', permiso='casos.exportar',
        sql="""select ca.id, so.nombre as solicitante, cl.nombre as cliente,
                      p.nombre as pais, eo.nombre as estado, u.nombre as responsable,
                      ca.proxima_accion, ca.proxima_accion_fecha, ca.resultado,
                      ca.ultima_actividad_en::date as ultima_actividad,
                      n.valor_pactado
                 from casos ca
                 join solicitantes so on so.id = ca.solicitante_id
                 join estados_operativos eo on eo.id = ca.estado_id
                 join paises p on p.id = ca.pais_id
                 left join negocios n on n.id = ca.negocio_id
                 left join clientes cl on cl.id = n.cliente_id
                 left join usuarios u on u.id = ca.responsable_id
                where :alcance
                order by ca.id""",
        filtro_alcance='ca.responsable_id = :actor',
        columnas=[
            Columna('id', 'Trámite'), Columna('solicitante', 'Solicitante'),
            Columna('cliente', 'Cliente'), Columna('pais', 'País'),
            Columna('estado', 'Estado'), Columna('responsable', 'Responsable'),
            Columna('proxima_accion', 'Próxima acción'),
            Columna('proxima_accion_fecha', 'Para cuándo'),
            Columna('resultado', 'Resultado'),
            Columna('ultima_actividad', 'Última actividad'),
            Columna('valor_pactado', 'Valor de la venta', 'pagos.ver')]),

    'cartera': Recurso(
        nombre='cartera', permiso='pagos.exportar',
        sql="""select n.id as venta, c.nombre as cliente, s.nombre as servicio,
                      n.fecha_venta, v.valor_pactado, v.total_pagado, v.saldo,
                      v.vencido, v.por_vencer, v.dias_mora, u.nombre as vendedor
                 from v_cartera v
                 join negocios n on n.id = v.negocio_id
                 join clientes c on c.id = n.cliente_id
                 join servicios s on s.id = n.servicio_id
                 left join usuarios u on u.id = n.vendedor_id
                where v.saldo > 0
                order by v.dias_mora desc, v.saldo desc""",
        columnas=[
            Columna('venta', 'Venta'), Columna('cliente', 'Cliente'),
            Columna('servicio', 'Servicio'), Columna('fecha_venta', 'Fecha'),
            Columna('valor_pactado', 'Valor'), Columna('total_pagado', 'Pagado'),
            Columna('saldo', 'Saldo'), Columna('vencido', 'Vencido'),
            Columna('por_vencer', 'Por vencer'), Columna('dias_mora', 'Días de mora'),
            Columna('vendedor', 'Vendedor')]),

    'pagos': Recurso(
        nombre='pagos', permiso='pagos.exportar',
        sql="""select p.id, p.fecha, c.nombre as cliente, p.negocio_id as venta,
                      p.monto_bruto, p.monto_neto, p.moneda, mp.nombre as medio,
                      p.referencia, p.estado
                 from pagos p
                 left join negocios n on n.id = p.negocio_id
                 left join clientes c on c.id = n.cliente_id
                 left join medios_pago mp on mp.id = p.medio_pago_id
                order by p.fecha desc, p.id desc""",
        columnas=[
            Columna('id', 'ID'), Columna('fecha', 'Fecha'),
            Columna('cliente', 'Cliente'), Columna('venta', 'Venta'),
            Columna('monto_bruto', 'Monto'), Columna('monto_neto', 'Neto'),
            Columna('moneda', 'Moneda'), Columna('medio', 'Medio de pago'),
            Columna('referencia', 'Referencia'), Columna('estado', 'Estado')]),

    'comisiones': Recurso(
        nombre='comisiones', permiso='comisiones.exportar',
        sql="""select co.id, u.nombre as vendedor, co.periodo, co.negocio_id as venta,
                      c.nombre as cliente, co.base_calculo, co.monto, co.estado,
                      (co.regla_aplicada->>'porcentaje_aplicado') as porcentaje,
                      (co.regla_aplicada->>'explicacion') as explicacion
                 from comisiones co
                 join usuarios u on u.id = co.vendedor_id
                 left join negocios n on n.id = co.negocio_id
                 left join clientes c on c.id = n.cliente_id
                order by co.periodo desc, u.nombre, co.id""",
        columnas=[
            Columna('id', 'ID'), Columna('vendedor', 'Vendedor'),
            Columna('periodo', 'Periodo'), Columna('venta', 'Venta'),
            Columna('cliente', 'Cliente'), Columna('base_calculo', 'Base'),
            Columna('monto', 'Comisión'), Columna('estado', 'Estado'),
            Columna('porcentaje', '%'), Columna('explicacion', 'Por qué')]),
}


def disponibles(db: Session, actor: Usuarios) -> list[str]:
    """Qué puede exportar quien pregunta. La pantalla no muestra lo que no puede."""
    tiene = permisos_de_rol(db, actor.rol_id)
    return sorted(n for n, r in RECURSOS.items() if r.permiso in tiene)


def _columnas_visibles(db: Session, actor: Usuarios, recurso: Recurso) -> list[Columna]:
    tiene = permisos_de_rol(db, actor.rol_id)
    return [c for c in recurso.columnas if c.permiso is None or c.permiso in tiene]


def _filas(db: Session, actor: Usuarios, recurso: Recurso,
           columnas: list[Columna]) -> list[list]:
    sql, p = recurso.sql, {}
    if ':alcance' in sql:
        if recurso.filtro_alcance and actor.alcance != 'todos':
            sql = sql.replace(':alcance', recurso.filtro_alcance)
            p['actor'] = actor.id
        else:
            sql = sql.replace(':alcance', 'true')
    crudas = db.execute(text(sql), p).mappings().all()
    if len(crudas) > MAX_FILAS:
        raise Conflicto(
            f'La consulta trae {len(crudas):,} filas y el tope por archivo es de '
            f'{MAX_FILAS:,}. Filtre antes de exportar.'.replace(',', '.'),
            'demasiadas_filas')
    nombres = [c.campo for c in columnas]
    return [[_inerte(fila.get(n)) for n in nombres] for fila in crudas]


def _inerte(v):
    """Neutraliza lo que Excel y Sheets ejecutarian al abrir el archivo.

    Una celda que empieza por «=», «+», «-» o «@» es una formula, y se ejecuta
    en el computador de quien abre la descarga, no en el servidor. El dato entra
    por el nombre de un cliente, que lo escribe cualquiera. La comilla delante
    es lo que Excel entiende como «esto es texto» y no se ve al abrirlo.
    """
    if isinstance(v, str) and v[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + v
    return v


def _a_csv(titulos: list[str], filas: list[list]) -> bytes:
    """Con BOM para que Excel en español abra bien las tildes."""
    sal = io.StringIO()
    w = csv.writer(sal, delimiter=';')
    w.writerow(titulos)
    w.writerows(filas)
    return ('﻿' + sal.getvalue()).encode('utf-8')


def _a_xlsx(nombre: str, titulos: list[str], filas: list[list]) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = nombre[:31]
    hoja.append(titulos)
    for fila in filas:
        hoja.append([float(v) if hasattr(v, 'quantize') else v for v in fila])
    hoja.freeze_panes = 'A2'
    sal = io.BytesIO()
    libro.save(sal)
    return sal.getvalue()


def generar(db: Session, actor: Usuarios, recurso_nombre: str, formato: str = 'xlsx',
            ip: str | None = None) -> tuple[bytes, str, int, list[str]]:
    """El archivo, su nombre, cuántas filas lleva y qué columnas se omitieron.

    Lo último importa: quien exporta tiene derecho a saber que el archivo no
    trae todo, en vez de descubrirlo cuando le falta una columna.
    """
    recurso = RECURSOS.get(recurso_nombre)
    if recurso is None:
        raise Invalido(f'No se puede exportar «{recurso_nombre}». '
                       f'Opciones: {", ".join(sorted(RECURSOS))}.')
    if formato not in FORMATOS:
        raise Invalido(f'Formato inválido. Opciones: {", ".join(FORMATOS)}.')
    if recurso.permiso not in permisos_de_rol(db, actor.rol_id):
        raise Prohibido(f'Su rol no puede exportar {recurso_nombre}.',
                        codigo='sin_permiso')

    columnas = _columnas_visibles(db, actor, recurso)
    omitidas = [c.titulo for c in recurso.columnas if c not in columnas]
    filas = _filas(db, actor, recurso, columnas)
    titulos = [c.titulo for c in columnas]

    cuerpo = (_a_csv(titulos, filas) if formato == 'csv'
              else _a_xlsx(recurso.nombre, titulos, filas))
    sello = dt.datetime.now(BOGOTA).strftime('%Y-%m-%d')
    archivo = f'{recurso.nombre}-{sello}.{formato}'

    # RNF-07: queda dicho quién sacó qué. Un archivo con 866 personas deja de
    # estar bajo el control del sistema en cuanto se descarga.
    db.add(Exportaciones(
        usuario_id=actor.id, recurso=recurso.nombre, formato=formato,
        filtros=json.loads(json.dumps({'columnas': titulos, 'omitidas': omitidas,
                                       'alcance': actor.alcance})),
        filas=len(filas), ip=ip))
    db.commit()
    return cuerpo, archivo, len(filas), omitidas


def historial(db: Session, limite: int = 50) -> list[dict]:
    """Quién exportó qué y cuándo. Es lo que se mira cuando algo se filtró."""
    return [dict(f) for f in db.execute(text("""
        select e.id, u.nombre as usuario, e.recurso, e.formato, e.filas,
               host(e.ip) as ip, e.ocurrido_en, e.filtros
          from exportaciones e join usuarios u on u.id = e.usuario_id
         order by e.ocurrido_en desc limit :n"""), {'n': limite}).mappings()]
