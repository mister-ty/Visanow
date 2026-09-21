"""Administración de catálogos y configuración (actividad 2.2, sección 12 de la especificación).

Montada en /admin. Solo entra quien tenga el permiso catalogos.editar (hoy, la
administradora) y siempre con doble factor.

Tres reglas:
- Cada cambio queda en la auditoría, con valor anterior y nuevo, en la misma
  transacción que el cambio. Lo hacen los eventos de la sesión exclusiva del
  panel, no cada vista: una vista nueva queda auditada sin acordarse de hacerlo.
- Nada se borra. Lo que se retira se desactiva: borrar un servicio o un país
  rompería las ventas y los casos que lo usan.
- Los códigos no se editan después de creados: la homologación y el código del
  sistema los usan como llave.
"""
from __future__ import annotations

import re
import types
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import CheckConstraint, event, inspect
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from app.core.config import ajustes
from app.core.errores import ErrorDominio
from app.db.session import SesionLocal, motor
from app.models import esquema as m
from app.services import auth as servicio_auth
from app.services.auditoria import NUNCA_AUDITAR, _a_json, instantanea
from app.services.usuarios import permisos_de_rol

PERMISO = 'catalogos.editar'
DURACION_SESION_HORAS = 8

# Quién está haciendo el cambio. Lo fija la autenticación en cada solicitud y lo
# lee la auditoría; viaja al hilo de trabajo porque anyio copia el contexto.
_actor: ContextVar[tuple[int | None, str | None]] = ContextVar('actor_admin', default=(None, None))


# ------------------------------------------------------------------ auditoría

SesionAdmin = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


def _cambios(objeto) -> tuple[dict, dict]:
    antes, despues = {}, {}
    for atributo in inspect(objeto).mapper.column_attrs:
        if atributo.key in NUNCA_AUDITAR:
            continue
        historia = inspect(objeto).attrs[atributo.key].history
        if historia.has_changes():
            antes[atributo.key] = _a_json(historia.deleted[0]) if historia.deleted else None
            despues[atributo.key] = _a_json(historia.added[0]) if historia.added else None
    return antes, despues


def _id_de(objeto) -> int | None:
    pk = inspect(objeto).identity
    return pk[0] if pk and len(pk) == 1 and isinstance(pk[0], int) else None


@event.listens_for(SesionAdmin, 'before_flush')
def _auditar_cambios(sesion: Session, *_):
    usuario_id, ip = _actor.get()
    for objeto in sesion.dirty:
        if isinstance(objeto, m.Auditoria) or not sesion.is_modified(objeto):
            continue
        antes, despues = _cambios(objeto)
        if despues:
            sesion.add(m.Auditoria(usuario_id=usuario_id, operacion='update', ip=ip,
                                   entidad=objeto.__tablename__, entidad_id=_id_de(objeto),
                                   antes=antes, despues=despues))
    # Los nuevos todavía no tienen id: se auditan después del flush
    sesion.info.setdefault('nuevos', []).extend(o for o in sesion.new if not isinstance(o, m.Auditoria))


@event.listens_for(SesionAdmin, 'after_flush_postexec')
def _auditar_nuevos(sesion: Session, _):
    usuario_id, ip = _actor.get()
    for objeto in sesion.info.pop('nuevos', []):
        sesion.add(m.Auditoria(usuario_id=usuario_id, operacion='insert', ip=ip,
                               entidad=objeto.__tablename__, entidad_id=_id_de(objeto),
                               despues=instantanea(objeto)))


# ------------------------------------------------------------------ acceso

class AccesoAdministracion(AuthenticationBackend):
    """Mismo ingreso que la API (bloqueo por intentos incluido) más el código de
    doble factor en el mismo formulario."""

    def __init__(self) -> None:
        super().__init__(secret_key=ajustes().app_secret)
        self.middlewares = [Middleware(
            SessionMiddleware, secret_key=ajustes().app_secret, session_cookie='visanow_admin',
            max_age=DURACION_SESION_HORAS * 3600,
            same_site='strict',              # ningún sitio ajeno puede enviar formularios con esta sesión
            https_only=not ajustes().es_local)]

    @staticmethod
    def _ip(request: Request) -> str | None:
        from app.core.deps import ip_cliente
        return ip_cliente(request)

    def _ingresar(self, email: str, password: str, codigo: str, ip: str | None) -> tuple[int, str]:
        with SesionLocal() as db:
            u = servicio_auth.autenticar(db, email, password, ip)
            if u.debe_cambiar_password:
                raise ErrorDominio('Cambie primero la contraseña temporal desde la aplicación.')
            if not u.mfa_habilitado:
                raise ErrorDominio('Active primero el doble factor desde la aplicación.')
            db.refresh(u, with_for_update=True)
            servicio_auth.verificar_codigo(db, u, codigo, ip)
            if PERMISO not in permisos_de_rol(db, u.rol_id):
                raise ErrorDominio('Su perfil no tiene acceso a la administración.')
            return u.id, servicio_auth.version_credenciales(u)

    async def login(self, request: Request) -> bool:
        formulario = await request.form()
        try:
            email = validate_email(str(formulario.get('username', '')).strip(),
                                   check_deliverability=False).normalized
        except EmailNotValidError:
            request.state.error_login = 'Escriba un correo válido.'
            return False
        try:
            uid, pv = await run_in_threadpool(self._ingresar, email, str(formulario.get('password', '')),
                                              str(formulario.get('codigo', '')).strip(), self._ip(request))
        except ErrorDominio as e:
            request.state.error_login = e.mensaje
            return False
        request.session.clear()
        request.session.update({'uid': uid, 'pv': pv, 'desde': datetime.now(timezone.utc).timestamp()})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    def _vigente(self, uid: int, pv: str) -> bool:
        with SesionLocal() as db:
            u = db.get(m.Usuarios, uid)
            return bool(u and u.activo and u.mfa_habilitado
                        and servicio_auth.version_credenciales(u) == pv
                        and PERMISO in permisos_de_rol(db, u.rol_id))

    async def authenticate(self, request: Request) -> bool:
        s = request.session
        edad = datetime.now(timezone.utc).timestamp() - s.get('desde', 0)
        if not s.get('uid') or edad > DURACION_SESION_HORAS * 3600 \
                or not await run_in_threadpool(self._vigente, s['uid'], s.get('pv', '')):
            s.clear()
            return False
        _actor.set((s['uid'], self._ip(request)))
        return True


# ------------------------------------------------------------------ vistas

NO_EDITABLES = {'id', 'creado_en', 'actualizado_en', 'actualizado_por'}
_RE_OPCIONES = re.compile(r"(\w+)\)?::text = ANY \(\(?ARRAY\[([^\]]*)\]")


def _opciones_de_checks(modelo) -> dict[str, list[tuple[str, str]]]:
    """Las listas desplegables salen de las restricciones CHECK de la base: si
    mañana se agrega una opción en una migración, el formulario la muestra."""
    opciones = {}
    for restriccion in modelo.__table__.constraints:
        if isinstance(restriccion, CheckConstraint):
            encontrado = _RE_OPCIONES.search(str(restriccion.sqltext))
            if encontrado:
                valores = re.findall(r"'([^']+)'::", encontrado.group(2))
                opciones[encontrado.group(1)] = [(v, v.replace('_', ' ').capitalize()) for v in valores]
    return opciones


def _vista(modelo, nombre: str, plural: str, icono: str, *, crear: bool = True,
           solo: list[str] | None = None, lista: list[str] | None = None) -> type[ModelView]:
    mapper = inspect(modelo)
    llaves_foraneas = {c.key for c in mapper.column_attrs if c.columns[0].foreign_keys}
    escalares = [c.key for c in mapper.column_attrs
                 if c.key not in NO_EDITABLES and c.key not in llaves_foraneas
                 and (not c.columns[0].primary_key or c.key in ('codigo', 'clave'))]
    relaciones = [r.key for r in mapper.relationships if r.direction.name == 'MANYTOONE'
                  and r.key not in ('usuarios', 'actualizado_por_usuario')]
    primero, ultimo = ('codigo', 'clave', 'nombre'), ('activo',)
    orden = lambda c: (0, primero.index(c)) if c in primero else ((2, 0) if c in ultimo else (1, 0))
    formulario = solo or sorted(escalares + relaciones, key=orden)
    etiquetas = {c: c.replace('_', ' ').capitalize() for c in formulario + (lista or [])}
    atributos = {
        'name': nombre, 'name_plural': plural, 'icon': f'fa-solid {icono}', 'category': 'Catálogos',
        'can_delete': False, 'can_create': crear, 'can_export': True, 'page_size': 50,
        'column_list': lista or formulario[:8],
        'form_columns': formulario,
        'form_create_rules': formulario,
        'form_edit_rules': [c for c in formulario if c not in ('codigo', 'clave')],
        'form_choices': _opciones_de_checks(modelo),
        'column_labels': etiquetas,
    }
    if 'nombre' in escalares:
        atributos['column_searchable_list'] = ['nombre']
        atributos['column_default_sort'] = 'nombre'
    return types.new_class(f'Vista{modelo.__name__}', (ModelView,), {'model': modelo},
                           lambda ns: ns.update(atributos))


def _pesos(modelo, atributo) -> str:
    valor = getattr(modelo, atributo.key if hasattr(atributo, 'key') else atributo)
    return '' if valor is None else '$' + f'{valor:,.0f}'.replace(',', '.')


VISTA_TARIFAS = _vista(m.Tarifas, 'Tarifa', 'Tarifas', 'fa-tags',
                       lista=['servicio', 'personas', 'modalidad', 'valor', 'valor_minimo',
                              'vigente_desde', 'vigente_hasta'])
VISTA_TARIFAS.column_formatters = {'valor': _pesos, 'valor_minimo': _pesos}
VISTA_TARIFAS.column_default_sort = [('servicio_id', False), ('personas', False)]

VISTAS = [
    _vista(m.Servicios, 'Servicio', 'Servicios', 'fa-briefcase',
           lista=['codigo', 'nombre', 'tipo', 'pais', 'crea_casos', 'tasa_consular_valor',
                  'tasa_consular_moneda', 'activo']),
    VISTA_TARIFAS,
    _vista(m.Paises, 'País', 'Países', 'fa-globe'),
    _vista(m.Sedes, 'Sede', 'Sedes y consulados', 'fa-building'),
    _vista(m.TiposVisa, 'Tipo de visa', 'Tipos de visa', 'fa-passport'),
    _vista(m.Modalidades, 'Modalidad', 'Modalidades', 'fa-users'),
    _vista(m.Canales, 'Canal', 'Canales', 'fa-bullhorn'),
    _vista(m.Campanias, 'Campaña', 'Campañas', 'fa-rectangle-ad'),
    _vista(m.MotivosPerdida, 'Motivo de pérdida', 'Motivos de pérdida', 'fa-circle-xmark'),
    _vista(m.MediosPago, 'Medio de pago', 'Medios de pago', 'fa-credit-card'),
    _vista(m.BancosCuentas, 'Cuenta bancaria', 'Bancos y cuentas', 'fa-building-columns'),
    _vista(m.CategoriasGasto, 'Categoría de gasto', 'Categorías de gasto', 'fa-receipt'),
    _vista(m.Proveedores, 'Proveedor', 'Proveedores', 'fa-truck'),
    _vista(m.Checklists, 'Checklist', 'Checklists', 'fa-list-check'),
    _vista(m.ChecklistItems, 'Ítem de checklist', 'Ítems de checklist', 'fa-square-check'),
    # Los estados, las alertas y los parámetros los usa el código por su código:
    # se ajustan, no se crean desde aquí.
    _vista(m.EstadosOperativos, 'Estado operativo', 'Estados operativos', 'fa-diagram-project',
           crear=False, solo=['nombre', 'orden', 'requiere_motivo', 'activo'],
           lista=['codigo', 'nombre', 'fase', 'orden', 'es_final', 'requiere_motivo', 'activo']),
    _vista(m.EstadosComerciales, 'Estado comercial', 'Estados comerciales', 'fa-filter',
           crear=False, solo=['nombre', 'orden', 'requiere_motivo', 'activo'],
           lista=['codigo', 'nombre', 'orden', 'es_cierre', 'requiere_motivo', 'activo']),
    _vista(m.AlertasTipos, 'Tipo de alerta', 'Alertas', 'fa-bell', crear=False,
           solo=['nombre', 'anticipacion_valor', 'anticipacion_unidad', 'repeticiones',
                 'destinatario_rol', 'canal', 'severidad', 'activo'],
           lista=['codigo', 'nombre', 'entidad', 'anticipacion_valor', 'anticipacion_unidad',
                  'destinatario_rol', 'severidad', 'activo']),
    _vista(m.Parametros, 'Parámetro', 'Parámetros', 'fa-sliders', crear=False,
           solo=['valor', 'descripcion'], lista=['clave', 'valor', 'descripcion', 'actualizado_en']),
    _vista(m.PoliticaCampos, 'Propiedad de campo', 'Propiedad de datos SaaS', 'fa-code-merge',
           crear=False, solo=['propietario', 'al_conflicto'],
           lista=['entidad', 'campo', 'propietario', 'al_conflicto']),
]


def montar_admin(app) -> Admin:
    admin = Admin(app, session_maker=SesionAdmin, base_url='/admin',
                  title='VisaNow · Administración',
                  templates_dir=str(Path(__file__).parent / 'templates'),
                  authentication_backend=AccesoAdministracion())
    for vista in VISTAS:
        admin.add_view(vista)
    return admin
