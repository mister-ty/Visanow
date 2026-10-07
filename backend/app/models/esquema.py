"""GENERADO por generar_modelos.py a partir de la base de datos. NO EDITAR A MANO.

Para cambiar una tabla: escribir una migración de Alembic, aplicarla y volver
a correr generar_modelos.py.
"""
from typing import Any, Optional
import datetime
import decimal

from sqlalchemy import BigInteger, Boolean, CHAR, CheckConstraint, Column, Computed, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, SmallInteger, String, Table, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


class BancosCuentas(Base):
    __tablename__ = 'bancos_cuentas'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='bancos_cuentas_pkey'),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    banco: Mapped[str] = mapped_column(String(60), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    numero: Mapped[Optional[str]] = mapped_column(String(40))
    titular: Mapped[Optional[str]] = mapped_column(String(120))

    pagos: Mapped[list['Pagos']] = relationship('Pagos', back_populates='banco_cuenta')
    gastos: Mapped[list['Gastos']] = relationship('Gastos', back_populates='banco_cuenta')
    movimientos_banco: Mapped[list['MovimientosBanco']] = relationship('MovimientosBanco', back_populates='banco_cuenta')


class Canales(Base):
    __tablename__ = 'canales'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='canales_pkey'),
        UniqueConstraint('codigo', name='canales_codigo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    codigo: Mapped[Optional[str]] = mapped_column(String(30))

    campanias: Mapped[list['Campanias']] = relationship('Campanias', back_populates='canal')
    clientes: Mapped[list['Clientes']] = relationship('Clientes', back_populates='canal')
    oportunidades: Mapped[list['Oportunidades']] = relationship('Oportunidades', back_populates='canal')
    negocios: Mapped[list['Negocios']] = relationship('Negocios', back_populates='canal')


class CategoriasGasto(Base):
    __tablename__ = 'categorias_gasto'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='categorias_gasto_pkey'),
        UniqueConstraint('codigo', name='categorias_gasto_codigo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    codigo: Mapped[Optional[str]] = mapped_column(String(30))

    gastos: Mapped[list['Gastos']] = relationship('Gastos', back_populates='categoria')


class EstadosComerciales(Base):
    __tablename__ = 'estados_comerciales'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='estados_comerciales_pkey'),
        UniqueConstraint('codigo', name='estados_comerciales_codigo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    orden: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    es_cierre: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    requiere_motivo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))

    oportunidades: Mapped[list['Oportunidades']] = relationship('Oportunidades', back_populates='estado')


class EstadosOperativos(Base):
    __tablename__ = 'estados_operativos'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='estados_operativos_pkey'),
        UniqueConstraint('codigo', name='estados_operativos_codigo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    fase: Mapped[str] = mapped_column(String(20), nullable=False)
    orden: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    es_final: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    requiere_motivo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))

    transiciones_operativas_estado_destino: Mapped[list['TransicionesOperativas']] = relationship('TransicionesOperativas', foreign_keys='[TransicionesOperativas.estado_destino_id]', back_populates='estado_destino')
    transiciones_operativas_estado_origen: Mapped[list['TransicionesOperativas']] = relationship('TransicionesOperativas', foreign_keys='[TransicionesOperativas.estado_origen_id]', back_populates='estado_origen')
    checklists: Mapped[list['Checklists']] = relationship('Checklists', back_populates='estado')
    casos: Mapped[list['Casos']] = relationship('Casos', back_populates='estado')


class MediosPago(Base):
    __tablename__ = 'medios_pago'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='medios_pago_pkey'),
        UniqueConstraint('codigo', name='medios_pago_codigo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    codigo: Mapped[Optional[str]] = mapped_column(String(30))

    pagos: Mapped[list['Pagos']] = relationship('Pagos', back_populates='medio_pago')
    gastos: Mapped[list['Gastos']] = relationship('Gastos', back_populates='medio_pago')


class Modalidades(Base):
    __tablename__ = 'modalidades'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='modalidades_pkey'),
        UniqueConstraint('codigo', name='modalidades_codigo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    codigo: Mapped[Optional[str]] = mapped_column(String(30))

    checklists: Mapped[list['Checklists']] = relationship('Checklists', back_populates='modalidad')
    casos: Mapped[list['Casos']] = relationship('Casos', back_populates='modalidad')


class MotivosPerdida(Base):
    __tablename__ = 'motivos_perdida'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='motivos_perdida_pkey'),
        UniqueConstraint('codigo', name='motivos_perdida_codigo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    codigo: Mapped[Optional[str]] = mapped_column(String(30))

    oportunidades: Mapped[list['Oportunidades']] = relationship('Oportunidades', back_populates='motivo_perdida')


class Paises(Base):
    __tablename__ = 'paises'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='paises_pkey'),
        UniqueConstraint('iso2', name='paises_iso2_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    iso2: Mapped[Optional[str]] = mapped_column(CHAR(2))

    sedes: Mapped[list['Sedes']] = relationship('Sedes', back_populates='pais')
    servicios: Mapped[list['Servicios']] = relationship('Servicios', back_populates='pais')
    tipos_visa: Mapped[list['TiposVisa']] = relationship('TiposVisa', back_populates='pais')
    checklists: Mapped[list['Checklists']] = relationship('Checklists', back_populates='pais')
    clientes: Mapped[list['Clientes']] = relationship('Clientes', back_populates='pais')
    oportunidades: Mapped[list['Oportunidades']] = relationship('Oportunidades', back_populates='pais')
    casos: Mapped[list['Casos']] = relationship('Casos', back_populates='pais')


class Permisos(Base):
    __tablename__ = 'permisos'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='permisos_pkey'),
        UniqueConstraint('codigo', name='permisos_codigo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    modulo: Mapped[str] = mapped_column(String(30), nullable=False)

    rol: Mapped[list['Roles']] = relationship('Roles', secondary='roles_permisos', back_populates='permiso')


class PoliticaCampos(Base):
    __tablename__ = 'politica_campos'
    __table_args__ = (
        CheckConstraint("al_conflicto::text = ANY (ARRAY['registrar'::character varying, 'sobrescribir'::character varying, 'ignorar'::character varying]::text[])", name='politica_campos_al_conflicto_check'),
        CheckConstraint("propietario::text = ANY (ARRAY['saas'::character varying, 'visanow'::character varying]::text[])", name='politica_campos_propietario_check'),
        PrimaryKeyConstraint('id', name='politica_campos_pkey'),
        UniqueConstraint('entidad', 'campo', name='politica_campos_entidad_campo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    entidad: Mapped[str] = mapped_column(String(20), nullable=False)
    campo: Mapped[str] = mapped_column(String(60), nullable=False)
    propietario: Mapped[str] = mapped_column(String(10), nullable=False)
    al_conflicto: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'registrar'::character varying"))


class Proveedores(Base):
    __tablename__ = 'proveedores'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='proveedores_pkey'),
        Index('ux_proveedores_nombre', unique=True)
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    documento: Mapped[Optional[str]] = mapped_column(String(40))

    gastos: Mapped[list['Gastos']] = relationship('Gastos', back_populates='proveedor')


class Roles(Base):
    __tablename__ = 'roles'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='roles_pkey'),
        UniqueConstraint('codigo', name='roles_codigo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)

    permiso: Mapped[list['Permisos']] = relationship('Permisos', secondary='roles_permisos', back_populates='rol')
    alertas_tipos: Mapped[list['AlertasTipos']] = relationship('AlertasTipos', back_populates='destinatario_rol')
    usuarios: Mapped[list['Usuarios']] = relationship('Usuarios', back_populates='rol')


class Sincronizaciones(Base):
    __tablename__ = 'sincronizaciones'
    __table_args__ = (
        CheckConstraint("resultado::text = ANY (ARRAY['ok'::character varying, 'error'::character varying]::text[])", name='sincronizaciones_resultado_check'),
        PrimaryKeyConstraint('id', name='sincronizaciones_pkey')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    origen: Mapped[str] = mapped_column(String(20), nullable=False)
    resultado: Mapped[str] = mapped_column(String(10), nullable=False)
    intentos: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('1'))
    ocurrido_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    detalle: Mapped[Optional[str]] = mapped_column(Text)


t_v_cartera = Table(
    'v_cartera', Base.metadata,
    Column('negocio_id', BigInteger),
    Column('moneda', CHAR(3)),
    Column('valor_pactado', Numeric(14, 2)),
    Column('total_pagado', Numeric),
    Column('saldo', Numeric),
    Column('exigible_hoy', Numeric),
    Column('vencido', Numeric),
    Column('por_vencer', Numeric),
    Column('dias_mora', Integer)
)


t_v_estado_financiero = Table(
    'v_estado_financiero', Base.metadata,
    Column('negocio_id', BigInteger),
    Column('valor_pactado', Numeric(14, 2)),
    Column('total_pagado', Numeric),
    Column('neto_recibido', Numeric),
    Column('ajustes', Numeric),
    Column('saldo', Numeric),
    Column('estado_financiero', Text),
    Column('moneda', CHAR(3))
)


class AlertasTipos(Base):
    __tablename__ = 'alertas_tipos'
    __table_args__ = (
        CheckConstraint("anticipacion_unidad::text = ANY (ARRAY['horas'::character varying, 'dias'::character varying, 'dias_habiles'::character varying]::text[])", name='alertas_tipos_anticipacion_unidad_check'),
        CheckConstraint("canal::text = ANY (ARRAY['interna'::character varying, 'correo'::character varying, 'whatsapp'::character varying]::text[])", name='alertas_tipos_canal_check'),
        CheckConstraint("entidad::text = ANY (ARRAY['oportunidad'::character varying, 'caso'::character varying, 'negocio'::character varying, 'cita'::character varying, 'importacion'::character varying]::text[])", name='alertas_tipos_entidad_check'),
        CheckConstraint("severidad::text = ANY (ARRAY['baja'::character varying, 'media'::character varying, 'alta'::character varying]::text[])", name='alertas_tipos_severidad_check'),
        ForeignKeyConstraint(['destinatario_rol_id'], ['roles.id'], name='alertas_tipos_destinatario_rol_id_fkey'),
        PrimaryKeyConstraint('id', name='alertas_tipos_pkey'),
        UniqueConstraint('codigo', name='alertas_tipos_codigo_key')
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    entidad: Mapped[str] = mapped_column(String(20), nullable=False)
    anticipacion_valor: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    anticipacion_unidad: Mapped[str] = mapped_column(String(12), nullable=False, server_default=text("'dias'::character varying"))
    repeticiones: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    canal: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'interna'::character varying"))
    severidad: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'media'::character varying"))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    destinatario_rol_id: Mapped[Optional[int]] = mapped_column(SmallInteger)

    destinatario_rol: Mapped[Optional['Roles']] = relationship('Roles', back_populates='alertas_tipos')
    alertas: Mapped[list['Alertas']] = relationship('Alertas', back_populates='tipo')


class Campanias(Base):
    __tablename__ = 'campanias'
    __table_args__ = (
        CheckConstraint("tipo::text = ANY (ARRAY['pauta'::character varying, 'influencer'::character varying, 'referido'::character varying, 'organico'::character varying, 'otro'::character varying]::text[])", name='campanias_tipo_check'),
        ForeignKeyConstraint(['canal_id'], ['canales.id'], name='campanias_canal_id_fkey'),
        PrimaryKeyConstraint('id', name='campanias_pkey'),
        UniqueConstraint('codigo', name='campanias_codigo_key')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    canal_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    tipo: Mapped[Optional[str]] = mapped_column(String(20))
    responsable: Mapped[Optional[str]] = mapped_column(String(120))
    inicia_en: Mapped[Optional[datetime.date]] = mapped_column(Date)
    termina_en: Mapped[Optional[datetime.date]] = mapped_column(Date)
    presupuesto: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(14, 2))

    canal: Mapped[Optional['Canales']] = relationship('Canales', back_populates='campanias')
    oportunidades: Mapped[list['Oportunidades']] = relationship('Oportunidades', back_populates='campania_')


t_roles_permisos = Table(
    'roles_permisos', Base.metadata,
    Column('rol_id', SmallInteger, primary_key=True),
    Column('permiso_id', SmallInteger, primary_key=True),
    ForeignKeyConstraint(['permiso_id'], ['permisos.id'], ondelete='CASCADE', name='roles_permisos_permiso_id_fkey'),
    ForeignKeyConstraint(['rol_id'], ['roles.id'], ondelete='CASCADE', name='roles_permisos_rol_id_fkey'),
    PrimaryKeyConstraint('rol_id', 'permiso_id', name='roles_permisos_pkey')
)


class Sedes(Base):
    __tablename__ = 'sedes'
    __table_args__ = (
        ForeignKeyConstraint(['pais_id'], ['paises.id'], name='sedes_pais_id_fkey'),
        PrimaryKeyConstraint('id', name='sedes_pkey')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    pais_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    ciudad: Mapped[Optional[str]] = mapped_column(String(80))

    pais: Mapped[Optional['Paises']] = relationship('Paises', back_populates='sedes')
    casos: Mapped[list['Casos']] = relationship('Casos', back_populates='sede')
    citas: Mapped[list['Citas']] = relationship('Citas', back_populates='sede')


class Servicios(Base):
    __tablename__ = 'servicios'
    __table_args__ = (
        CheckConstraint("tipo::text = ANY (ARRAY['honorario'::character varying, 'recaudo_terceros'::character varying]::text[])", name='servicios_tipo_check'),
        ForeignKeyConstraint(['pais_id'], ['paises.id'], name='servicios_pais_id_fkey'),
        PrimaryKeyConstraint('id', name='servicios_pkey'),
        UniqueConstraint('codigo', name='servicios_codigo_key')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'honorario'::character varying"))
    crea_casos: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    codigo: Mapped[Optional[str]] = mapped_column(String(30))
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    pais_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    tasa_consular_valor: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(14, 2))
    tasa_consular_moneda: Mapped[Optional[str]] = mapped_column(CHAR(3))
    tasa_consular_nota: Mapped[Optional[str]] = mapped_column(String(200))

    pais: Mapped[Optional['Paises']] = relationship('Paises', back_populates='servicios')
    comisiones_reglas: Mapped[list['ComisionesReglas']] = relationship('ComisionesReglas', back_populates='servicio')
    tarifas: Mapped[list['Tarifas']] = relationship('Tarifas', back_populates='servicio')
    oportunidades: Mapped[list['Oportunidades']] = relationship('Oportunidades', back_populates='servicio')
    negocios: Mapped[list['Negocios']] = relationship('Negocios', back_populates='servicio')


class TiposVisa(Base):
    __tablename__ = 'tipos_visa'
    __table_args__ = (
        ForeignKeyConstraint(['pais_id'], ['paises.id'], name='tipos_visa_pais_id_fkey'),
        PrimaryKeyConstraint('id', name='tipos_visa_pkey')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    pais_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    codigo: Mapped[Optional[str]] = mapped_column(String(20))
    activo: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))

    pais: Mapped[Optional['Paises']] = relationship('Paises', back_populates='tipos_visa')
    checklists: Mapped[list['Checklists']] = relationship('Checklists', back_populates='tipo_visa')
    casos: Mapped[list['Casos']] = relationship('Casos', back_populates='tipo_visa')


class TransicionesOperativas(Base):
    __tablename__ = 'transiciones_operativas'
    __table_args__ = (
        ForeignKeyConstraint(['estado_destino_id'], ['estados_operativos.id'], name='transiciones_operativas_estado_destino_id_fkey'),
        ForeignKeyConstraint(['estado_origen_id'], ['estados_operativos.id'], name='transiciones_operativas_estado_origen_id_fkey'),
        PrimaryKeyConstraint('estado_origen_id', 'estado_destino_id', name='transiciones_operativas_pkey')
    )

    estado_origen_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    estado_destino_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    requiere_checklist: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    campos_obligatorios: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    estado_destino: Mapped['EstadosOperativos'] = relationship('EstadosOperativos', foreign_keys=[estado_destino_id], back_populates='transiciones_operativas_estado_destino')
    estado_origen: Mapped['EstadosOperativos'] = relationship('EstadosOperativos', foreign_keys=[estado_origen_id], back_populates='transiciones_operativas_estado_origen')


class Usuarios(Base):
    __tablename__ = 'usuarios'
    __table_args__ = (
        CheckConstraint("alcance::text = ANY (ARRAY['todos'::character varying, 'asignados'::character varying, 'propios'::character varying]::text[])", name='usuarios_alcance_check'),
        ForeignKeyConstraint(['rol_id'], ['roles.id'], name='usuarios_rol_id_fkey'),
        PrimaryKeyConstraint('id', name='usuarios_pkey'),
        UniqueConstraint('email', name='usuarios_email_key')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    rol_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    mfa_habilitado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    alcance: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'todos'::character varying"))
    intentos_fallidos: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    mfa_secreto: Mapped[Optional[str]] = mapped_column(Text)
    ultimo_acceso: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    bloqueado_hasta: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    password_cambiado_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    rol: Mapped['Roles'] = relationship('Roles', back_populates='usuarios')
    auditoria: Mapped[list['Auditoria']] = relationship('Auditoria', back_populates='usuario')
    clientes: Mapped[list['Clientes']] = relationship('Clientes', back_populates='usuarios')
    comisiones_reglas: Mapped[list['ComisionesReglas']] = relationship('ComisionesReglas', back_populates='vendedor')
    documentos: Mapped[list['Documentos']] = relationship('Documentos', back_populates='usuarios')
    exportaciones: Mapped[list['Exportaciones']] = relationship('Exportaciones', back_populates='usuario')
    fusiones: Mapped[list['Fusiones']] = relationship('Fusiones', back_populates='usuarios')
    importaciones: Mapped[list['Importaciones']] = relationship('Importaciones', back_populates='usuarios')
    liquidaciones_comision_liquidada_por: Mapped[list['LiquidacionesComision']] = relationship('LiquidacionesComision', foreign_keys='[LiquidacionesComision.liquidada_por]', back_populates='usuarios')
    liquidaciones_comision_vendedor: Mapped[list['LiquidacionesComision']] = relationship('LiquidacionesComision', foreign_keys='[LiquidacionesComision.vendedor_id]', back_populates='vendedor')
    migracion_corridas: Mapped[list['MigracionCorridas']] = relationship('MigracionCorridas', back_populates='usuarios')
    parametros: Mapped[list['Parametros']] = relationship('Parametros', back_populates='usuarios')
    actividades: Mapped[list['Actividades']] = relationship('Actividades', back_populates='usuario')
    oportunidades: Mapped[list['Oportunidades']] = relationship('Oportunidades', back_populates='asesor')
    negocios: Mapped[list['Negocios']] = relationship('Negocios', back_populates='vendedor')
    ajustes_negocio: Mapped[list['AjustesNegocio']] = relationship('AjustesNegocio', back_populates='usuarios')
    casos: Mapped[list['Casos']] = relationship('Casos', back_populates='responsable')
    comisiones: Mapped[list['Comisiones']] = relationship('Comisiones', back_populates='vendedor')
    pagos: Mapped[list['Pagos']] = relationship('Pagos', back_populates='usuarios')
    casos_checklist: Mapped[list['CasosChecklist']] = relationship('CasosChecklist', back_populates='usuarios')
    casos_historial: Mapped[list['CasosHistorial']] = relationship('CasosHistorial', back_populates='usuario')
    conflictos_sincronizacion: Mapped[list['ConflictosSincronizacion']] = relationship('ConflictosSincronizacion', back_populates='usuarios')
    gastos: Mapped[list['Gastos']] = relationship('Gastos', back_populates='usuarios')
    movimientos_banco: Mapped[list['MovimientosBanco']] = relationship('MovimientosBanco', back_populates='usuarios')
    tareas_creado_por: Mapped[list['Tareas']] = relationship('Tareas', foreign_keys='[Tareas.creado_por]', back_populates='usuarios')
    tareas_responsable: Mapped[list['Tareas']] = relationship('Tareas', foreign_keys='[Tareas.responsable_id]', back_populates='responsable')
    alertas_destinatario: Mapped[list['Alertas']] = relationship('Alertas', foreign_keys='[Alertas.destinatario_id]', back_populates='destinatario')
    alertas_resuelta_por: Mapped[list['Alertas']] = relationship('Alertas', foreign_keys='[Alertas.resuelta_por]', back_populates='usuarios')


class Auditoria(Base):
    __tablename__ = 'auditoria'
    __table_args__ = (
        ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name='auditoria_usuario_id_fkey'),
        PrimaryKeyConstraint('id', name='auditoria_pkey'),
        Index('ix_auditoria_entidad', 'entidad', 'entidad_id', 'ocurrido_en'),
        Index('ix_auditoria_usuario', 'usuario_id', 'ocurrido_en')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operacion: Mapped[str] = mapped_column(String(15), nullable=False)
    entidad: Mapped[str] = mapped_column(String(40), nullable=False)
    ocurrido_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    usuario_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    entidad_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    antes: Mapped[Optional[dict]] = mapped_column(JSONB)
    despues: Mapped[Optional[dict]] = mapped_column(JSONB)
    ip: Mapped[Optional[Any]] = mapped_column(INET)

    usuario: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='auditoria')


class Checklists(Base):
    __tablename__ = 'checklists'
    __table_args__ = (
        ForeignKeyConstraint(['estado_id'], ['estados_operativos.id'], name='checklists_estado_id_fkey'),
        ForeignKeyConstraint(['modalidad_id'], ['modalidades.id'], name='checklists_modalidad_id_fkey'),
        ForeignKeyConstraint(['pais_id'], ['paises.id'], name='checklists_pais_id_fkey'),
        ForeignKeyConstraint(['tipo_visa_id'], ['tipos_visa.id'], name='checklists_tipo_visa_id_fkey'),
        PrimaryKeyConstraint('id', name='checklists_pkey'),
        UniqueConstraint('codigo', name='checklists_codigo_key')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    pais_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    tipo_visa_id: Mapped[Optional[int]] = mapped_column(Integer)
    modalidad_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    estado_id: Mapped[Optional[int]] = mapped_column(SmallInteger)

    estado: Mapped[Optional['EstadosOperativos']] = relationship('EstadosOperativos', back_populates='checklists')
    modalidad: Mapped[Optional['Modalidades']] = relationship('Modalidades', back_populates='checklists')
    pais: Mapped[Optional['Paises']] = relationship('Paises', back_populates='checklists')
    tipo_visa: Mapped[Optional['TiposVisa']] = relationship('TiposVisa', back_populates='checklists')
    checklist_items: Mapped[list['ChecklistItems']] = relationship('ChecklistItems', back_populates='checklist')


class Clientes(Base):
    __tablename__ = 'clientes'
    __table_args__ = (
        ForeignKeyConstraint(['canal_id'], ['canales.id'], name='clientes_canal_id_fkey'),
        ForeignKeyConstraint(['creado_por'], ['usuarios.id'], name='clientes_creado_por_fkey'),
        ForeignKeyConstraint(['fusionado_en_id'], ['clientes.id'], name='clientes_fusionado_en_id_fkey'),
        ForeignKeyConstraint(['pais_id'], ['paises.id'], name='clientes_pais_id_fkey'),
        PrimaryKeyConstraint('id', name='clientes_pkey'),
        Index('ix_clientes_activos', 'id', postgresql_where='((fusionado_en_id IS NULL) AND (NOT archivado))'),
        Index('ix_clientes_email', 'email'),
        Index('ix_clientes_fusionados', 'fusionado_en_id', postgresql_where='(fusionado_en_id IS NOT NULL)'),
        Index('ix_clientes_migrado', 'origen_archivo', 'origen_hoja', 'origen_fila', postgresql_where='(origen_archivo IS NOT NULL)'),
        Index('ix_clientes_nombre', 'nombre', postgresql_using='gin'),
        Index('ix_clientes_nombre_busqueda', 'nombre_busqueda', postgresql_using='gin'),
        Index('ix_clientes_origen', 'origen_archivo', 'origen_hoja', 'origen_fila', postgresql_where='(origen_archivo IS NOT NULL)'),
        Index('ix_clientes_telefono', 'telefono'),
        Index('ix_clientes_telefono_norm', 'telefono_normalizado', postgresql_where='(telefono_normalizado IS NOT NULL)'),
        Index('ux_clientes_documento', 'numero_documento', postgresql_where='(numero_documento IS NOT NULL)', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    consentimiento: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    archivado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    actualizado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tipo_documento: Mapped[Optional[str]] = mapped_column(String(20))
    numero_documento: Mapped[Optional[str]] = mapped_column(String(40))
    telefono: Mapped[Optional[str]] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(CITEXT)
    ciudad: Mapped[Optional[str]] = mapped_column(String(80))
    pais_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    canal_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    consentimiento_fecha: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    observaciones: Mapped[Optional[str]] = mapped_column(Text)
    creado_por: Mapped[Optional[int]] = mapped_column(BigInteger)
    ultimo_contacto_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    origen_archivo: Mapped[Optional[str]] = mapped_column(String(80))
    origen_hoja: Mapped[Optional[str]] = mapped_column(String(40))
    origen_fila: Mapped[Optional[int]] = mapped_column(Integer)
    migrado_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    fusionado_en_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    nombre_busqueda: Mapped[Optional[str]] = mapped_column(Text, Computed('lower(sin_tildes((nombre)::text))', persisted=True))
    telefono_normalizado: Mapped[Optional[str]] = mapped_column(String(10), Computed('NULLIF("right"(regexp_replace((COALESCE(telefono, \'\'::character varying))::text, \'[^0-9]\'::text, \'\'::text, \'g\'::text), 10), \'\'::text)', persisted=True))

    canal: Mapped[Optional['Canales']] = relationship('Canales', back_populates='clientes')
    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='clientes')
    fusionado_en: Mapped[Optional['Clientes']] = relationship('Clientes', remote_side=[id], back_populates='fusionado_en_reverse')
    fusionado_en_reverse: Mapped[list['Clientes']] = relationship('Clientes', remote_side=[fusionado_en_id], back_populates='fusionado_en')
    pais: Mapped[Optional['Paises']] = relationship('Paises', back_populates='clientes')
    grupos: Mapped[list['Grupos']] = relationship('Grupos', back_populates='cliente_contacto')
    oportunidades_cliente: Mapped[list['Oportunidades']] = relationship('Oportunidades', foreign_keys='[Oportunidades.cliente_id]', back_populates='cliente')
    oportunidades_referido_por_cliente: Mapped[list['Oportunidades']] = relationship('Oportunidades', foreign_keys='[Oportunidades.referido_por_cliente_id]', back_populates='referido_por_cliente')
    negocios: Mapped[list['Negocios']] = relationship('Negocios', back_populates='cliente')
    solicitantes: Mapped[list['Solicitantes']] = relationship('Solicitantes', back_populates='cliente')
    migracion_filas: Mapped[list['MigracionFilas']] = relationship('MigracionFilas', back_populates='cliente')
    tareas: Mapped[list['Tareas']] = relationship('Tareas', back_populates='cliente')


class ComisionesReglas(Base):
    __tablename__ = 'comisiones_reglas'
    __table_args__ = (
        CheckConstraint("base::text = ANY (ARRAY['vendido'::character varying, 'cobrado'::character varying, 'neto_recibido'::character varying]::text[])", name='comisiones_reglas_base_check'),
        CheckConstraint('monto_fijo >= 0::numeric', name='comisiones_reglas_monto_fijo_check'),
        CheckConstraint('porcentaje >= 0::numeric AND porcentaje <= 100::numeric', name='comisiones_reglas_porcentaje_check'),
        CheckConstraint('porcentaje IS NOT NULL OR monto_fijo IS NOT NULL', name='ck_reglas_valor'),
        CheckConstraint('vigente_hasta IS NULL OR vigente_hasta >= vigente_desde', name='ck_reglas_vigencia'),
        ForeignKeyConstraint(['servicio_id'], ['servicios.id'], name='comisiones_reglas_servicio_id_fkey'),
        ForeignKeyConstraint(['vendedor_id'], ['usuarios.id'], name='comisiones_reglas_vendedor_id_fkey'),
        PrimaryKeyConstraint('id', name='comisiones_reglas_pkey')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    base: Mapped[str] = mapped_column(String(20), nullable=False)
    vigente_desde: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    definicion: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    vendedor_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    servicio_id: Mapped[Optional[int]] = mapped_column(Integer)
    porcentaje: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(6, 3))
    monto_fijo: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(14, 2))
    meta_cantidad: Mapped[Optional[int]] = mapped_column(SmallInteger)
    vigente_hasta: Mapped[Optional[datetime.date]] = mapped_column(Date)

    servicio: Mapped[Optional['Servicios']] = relationship('Servicios', back_populates='comisiones_reglas')
    vendedor: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='comisiones_reglas')
    comisiones: Mapped[list['Comisiones']] = relationship('Comisiones', back_populates='regla')


class Documentos(Base):
    __tablename__ = 'documentos'
    __table_args__ = (
        CheckConstraint("almacenamiento::text = 'enlace'::text AND url IS NOT NULL OR almacenamiento::text = 'local'::text AND ruta IS NOT NULL", name='ck_documentos_ubicacion'),
        CheckConstraint("almacenamiento::text = ANY (ARRAY['enlace'::character varying, 'local'::character varying]::text[])", name='documentos_almacenamiento_check'),
        CheckConstraint("entidad::text = ANY (ARRAY['cliente'::character varying, 'solicitante'::character varying, 'caso'::character varying, 'negocio'::character varying, 'pago'::character varying, 'gasto'::character varying]::text[])", name='documentos_entidad_check'),
        ForeignKeyConstraint(['subido_por'], ['usuarios.id'], name='documentos_subido_por_fkey'),
        PrimaryKeyConstraint('id', name='documentos_pkey'),
        Index('ix_documentos_entidad', 'entidad', 'entidad_id')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entidad: Mapped[str] = mapped_column(String(20), nullable=False)
    entidad_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    almacenamiento: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'enlace'::character varying"))
    restringido: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    tipo: Mapped[Optional[str]] = mapped_column(String(40))
    url: Mapped[Optional[str]] = mapped_column(Text)
    ruta: Mapped[Optional[str]] = mapped_column(Text)
    mime: Mapped[Optional[str]] = mapped_column(String(80))
    tamano_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    sha256: Mapped[Optional[str]] = mapped_column(CHAR(64))
    subido_por: Mapped[Optional[int]] = mapped_column(BigInteger)

    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='documentos')
    actividades: Mapped[list['Actividades']] = relationship('Actividades', back_populates='documento')


class Exportaciones(Base):
    __tablename__ = 'exportaciones'
    __table_args__ = (
        CheckConstraint("formato::text = ANY (ARRAY['xlsx'::character varying, 'csv'::character varying, 'pdf'::character varying]::text[])", name='exportaciones_formato_check'),
        ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name='exportaciones_usuario_id_fkey'),
        PrimaryKeyConstraint('id', name='exportaciones_pkey'),
        Index('ix_exportaciones_usuario', 'usuario_id', 'ocurrido_en')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recurso: Mapped[str] = mapped_column(String(40), nullable=False)
    formato: Mapped[str] = mapped_column(String(10), nullable=False)
    filtros: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    filas: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    ocurrido_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    ip: Mapped[Optional[Any]] = mapped_column(INET)

    usuario: Mapped['Usuarios'] = relationship('Usuarios', back_populates='exportaciones')


class Fusiones(Base):
    __tablename__ = 'fusiones'
    __table_args__ = (
        CheckConstraint("criterio::text = ANY (ARRAY['documento'::character varying, 'pasaporte'::character varying, 'telefono'::character varying, 'email'::character varying, 'nombre'::character varying, 'manual'::character varying]::text[])", name='fusiones_criterio_check'),
        CheckConstraint("entidad::text = ANY (ARRAY['cliente'::character varying, 'solicitante'::character varying]::text[])", name='fusiones_entidad_check'),
        CheckConstraint('id_conservado <> id_absorbido', name='ck_fusiones_distintos'),
        ForeignKeyConstraint(['autorizado_por'], ['usuarios.id'], name='fusiones_autorizado_por_fkey'),
        PrimaryKeyConstraint('id', name='fusiones_pkey'),
        Index('ix_fusiones_absorbido', 'entidad', 'id_absorbido')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entidad: Mapped[str] = mapped_column(String(20), nullable=False)
    id_conservado: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_absorbido: Mapped[int] = mapped_column(BigInteger, nullable=False)
    criterio: Mapped[str] = mapped_column(String(30), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    autorizado_por: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ocurrido_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    usuarios: Mapped['Usuarios'] = relationship('Usuarios', back_populates='fusiones')


class Importaciones(Base):
    __tablename__ = 'importaciones'
    __table_args__ = (
        CheckConstraint("estado::text = ANY (ARRAY['previsualizada'::character varying, 'aplicada'::character varying, 'descartada'::character varying, 'fallida'::character varying]::text[])", name='importaciones_estado_check'),
        ForeignKeyConstraint(['ejecutada_por'], ['usuarios.id'], name='importaciones_ejecutada_por_fkey'),
        PrimaryKeyConstraint('id', name='importaciones_pkey'),
        Index('ix_importaciones_sha', 'archivo_sha256')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    origen: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'saas'::character varying"))
    archivo_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    archivo_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    filas_totales: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    nuevos: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    actualizados: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    sin_cambios: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    conflictos: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    rechazados: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    estado: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'previsualizada'::character varying"))
    iniciada_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    mensaje_error: Mapped[Optional[str]] = mapped_column(Text)
    ejecutada_por: Mapped[Optional[int]] = mapped_column(BigInteger)
    aplicada_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='importaciones')
    conflictos_sincronizacion: Mapped[list['ConflictosSincronizacion']] = relationship('ConflictosSincronizacion', back_populates='importacion')
    importaciones_filas: Mapped[list['ImportacionesFilas']] = relationship('ImportacionesFilas', back_populates='importacion')


class LiquidacionesComision(Base):
    __tablename__ = 'liquidaciones_comision'
    __table_args__ = (
        CheckConstraint("estado::text = ANY (ARRAY['abierta'::character varying, 'pagada'::character varying, 'anulada'::character varying]::text[])", name='ck_liquidacion_estado'),
        CheckConstraint('total >= 0::numeric AND cantidad >= 0', name='ck_liquidacion_total'),
        ForeignKeyConstraint(['liquidada_por'], ['usuarios.id'], name='liquidaciones_comision_liquidada_por_fkey'),
        ForeignKeyConstraint(['vendedor_id'], ['usuarios.id'], name='liquidaciones_comision_vendedor_id_fkey'),
        PrimaryKeyConstraint('id', name='liquidaciones_comision_pkey'),
        Index('ux_liquidacion_vendedor_periodo', 'vendedor_id', 'periodo', postgresql_where="((estado)::text <> 'anulada'::text)", unique=True),
        {'comment': 'Corte de comisiones de una vendedora en un periodo. Las '
                'comisiones que entran quedan en estado liquidada y apuntan aquí, '
                'para que no se paguen dos veces.'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vendedor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    periodo: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    total: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False, server_default=text("'abierta'::character varying"))
    creada_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    observaciones: Mapped[Optional[str]] = mapped_column(Text)
    liquidada_por: Mapped[Optional[int]] = mapped_column(BigInteger)
    pagada_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', foreign_keys=[liquidada_por], back_populates='liquidaciones_comision_liquidada_por')
    vendedor: Mapped['Usuarios'] = relationship('Usuarios', foreign_keys=[vendedor_id], back_populates='liquidaciones_comision_vendedor')
    comisiones: Mapped[list['Comisiones']] = relationship('Comisiones', back_populates='liquidacion')


class MigracionCorridas(Base):
    __tablename__ = 'migracion_corridas'
    __table_args__ = (
        CheckConstraint("modo::text = ANY (ARRAY['previsualizacion'::character varying, 'aplicacion'::character varying]::text[])", name='ck_migracion_modo'),
        ForeignKeyConstraint(['ejecutada_por'], ['usuarios.id'], name='migracion_corridas_ejecutada_por_fkey'),
        PrimaryKeyConstraint('id', name='migracion_corridas_pkey'),
        {'comment': 'Cada ejecución de la migración desde los Excel. La '
                'previsualización no escribe datos: deja la corrida y sus filas '
                'para poder revisarla antes de aplicar.'}
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    modo: Mapped[str] = mapped_column(String(16), nullable=False)
    iniciada_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    resumen: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    terminada_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    ejecutada_por: Mapped[Optional[int]] = mapped_column(BigInteger)

    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='migracion_corridas')
    migracion_filas: Mapped[list['MigracionFilas']] = relationship('MigracionFilas', back_populates='corrida')


class Parametros(Base):
    __tablename__ = 'parametros'
    __table_args__ = (
        ForeignKeyConstraint(['actualizado_por'], ['usuarios.id'], name='parametros_actualizado_por_fkey'),
        PrimaryKeyConstraint('clave', name='parametros_pkey')
    )

    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSONB, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    actualizado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    actualizado_por: Mapped[Optional[int]] = mapped_column(BigInteger)

    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='parametros')


class Tarifas(Base):
    __tablename__ = 'tarifas'
    __table_args__ = (
        CheckConstraint("modalidad::text = ANY (ARRAY['total'::character varying, 'por_persona'::character varying]::text[])", name='tarifas_modalidad_check'),
        CheckConstraint('personas >= 1 AND personas <= 20', name='tarifas_personas_check'),
        CheckConstraint('valor >= 0::numeric', name='ck_tarifas_valor'),
        CheckConstraint('valor_minimo IS NULL OR valor_minimo >= 0::numeric', name='tarifas_valor_minimo_check'),
        CheckConstraint('vigente_hasta IS NULL OR vigente_hasta >= vigente_desde', name='ck_tarifas_vigencia'),
        ForeignKeyConstraint(['servicio_id'], ['servicios.id'], name='tarifas_servicio_id_fkey'),
        PrimaryKeyConstraint('id', name='tarifas_pkey'),
        Index('ux_tarifas_servicio_personas_vigencia', 'servicio_id', 'personas', 'vigente_desde', unique=True)
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    servicio_id: Mapped[int] = mapped_column(Integer, nullable=False)
    valor: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default=text("'COP'::bpchar"))
    vigente_desde: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    personas: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('1'))
    modalidad: Mapped[str] = mapped_column(String(12), nullable=False, server_default=text("'total'::character varying"))
    vigente_hasta: Mapped[Optional[datetime.date]] = mapped_column(Date)
    valor_minimo: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(14, 2))

    servicio: Mapped['Servicios'] = relationship('Servicios', back_populates='tarifas')


class Actividades(Base):
    __tablename__ = 'actividades'
    __table_args__ = (
        CheckConstraint("direccion::text = ANY (ARRAY['entrante'::character varying, 'saliente'::character varying]::text[])", name='actividades_direccion_check'),
        CheckConstraint("entidad::text = ANY (ARRAY['cliente'::character varying, 'solicitante'::character varying, 'grupo'::character varying, 'oportunidad'::character varying, 'negocio'::character varying, 'caso'::character varying, 'pago'::character varying]::text[])", name='actividades_entidad_check'),
        CheckConstraint("tipo::text = ANY (ARRAY['nota'::character varying, 'llamada'::character varying, 'whatsapp'::character varying, 'correo'::character varying, 'reunion'::character varying, 'sistema'::character varying, 'cambio_estado'::character varying]::text[])", name='actividades_tipo_check'),
        ForeignKeyConstraint(['documento_id'], ['documentos.id'], name='actividades_documento_id_fkey'),
        ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name='actividades_usuario_id_fkey'),
        PrimaryKeyConstraint('id', name='actividades_pkey'),
        Index('ix_actividades_entidad', 'entidad', 'entidad_id', 'ocurrido_en'),
        Index('ix_actividades_origen', 'origen_archivo', 'origen_hoja', 'origen_fila', postgresql_where='(origen_archivo IS NOT NULL)'),
        Index('ix_actividades_usuario', 'usuario_id', 'ocurrido_en')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entidad: Mapped[str] = mapped_column(String(20), nullable=False)
    entidad_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    ocurrido_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    direccion: Mapped[Optional[str]] = mapped_column(String(10))
    asunto: Mapped[Optional[str]] = mapped_column(String(200))
    cuerpo: Mapped[Optional[str]] = mapped_column(Text)
    usuario_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    documento_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    origen_archivo: Mapped[Optional[str]] = mapped_column(String(80))
    origen_hoja: Mapped[Optional[str]] = mapped_column(String(60))
    origen_fila: Mapped[Optional[int]] = mapped_column(Integer)

    documento: Mapped[Optional['Documentos']] = relationship('Documentos', back_populates='actividades')
    usuario: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='actividades')


class ChecklistItems(Base):
    __tablename__ = 'checklist_items'
    __table_args__ = (
        ForeignKeyConstraint(['checklist_id'], ['checklists.id'], ondelete='CASCADE', name='checklist_items_checklist_id_fkey'),
        PrimaryKeyConstraint('id', name='checklist_items_pkey'),
        UniqueConstraint('checklist_id', 'codigo', name='checklist_items_checklist_id_codigo_key')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checklist_id: Mapped[int] = mapped_column(Integer, nullable=False)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    obligatorio: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    orden: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('0'))

    checklist: Mapped['Checklists'] = relationship('Checklists', back_populates='checklist_items')
    casos_checklist: Mapped[list['CasosChecklist']] = relationship('CasosChecklist', back_populates='item')


class Grupos(Base):
    __tablename__ = 'grupos'
    __table_args__ = (
        ForeignKeyConstraint(['cliente_contacto_id'], ['clientes.id'], name='grupos_cliente_contacto_id_fkey'),
        PrimaryKeyConstraint('id', name='grupos_pkey'),
        Index('ix_grupos_contacto', 'cliente_contacto_id'),
        Index('ix_grupos_origen', 'origen_archivo', 'origen_hoja', 'origen_fila', postgresql_where='(origen_archivo IS NOT NULL)')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    cliente_contacto_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    observaciones: Mapped[Optional[str]] = mapped_column(Text)
    origen_archivo: Mapped[Optional[str]] = mapped_column(String(80))
    origen_hoja: Mapped[Optional[str]] = mapped_column(String(60))
    origen_fila: Mapped[Optional[int]] = mapped_column(Integer)

    cliente_contacto: Mapped['Clientes'] = relationship('Clientes', back_populates='grupos')
    negocios: Mapped[list['Negocios']] = relationship('Negocios', back_populates='grupo')
    solicitantes: Mapped[list['Solicitantes']] = relationship('Solicitantes', back_populates='grupo')


class Oportunidades(Base):
    __tablename__ = 'oportunidades'
    __table_args__ = (
        ForeignKeyConstraint(['asesor_id'], ['usuarios.id'], name='oportunidades_asesor_id_fkey'),
        ForeignKeyConstraint(['campania_id'], ['campanias.id'], name='oportunidades_campania_id_fkey'),
        ForeignKeyConstraint(['canal_id'], ['canales.id'], name='oportunidades_canal_id_fkey'),
        ForeignKeyConstraint(['cliente_id'], ['clientes.id'], name='oportunidades_cliente_id_fkey'),
        ForeignKeyConstraint(['estado_id'], ['estados_comerciales.id'], name='oportunidades_estado_id_fkey'),
        ForeignKeyConstraint(['motivo_perdida_id'], ['motivos_perdida.id'], name='oportunidades_motivo_perdida_id_fkey'),
        ForeignKeyConstraint(['pais_id'], ['paises.id'], name='oportunidades_pais_id_fkey'),
        ForeignKeyConstraint(['referido_por_cliente_id'], ['clientes.id'], name='oportunidades_referido_por_cliente_id_fkey'),
        ForeignKeyConstraint(['servicio_id'], ['servicios.id'], name='oportunidades_servicio_id_fkey'),
        PrimaryKeyConstraint('id', name='oportunidades_pkey'),
        Index('ix_oportunidades_campania', 'campania_id', postgresql_where='(campania_id IS NOT NULL)')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    estado_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    servicio_id: Mapped[Optional[int]] = mapped_column(Integer)
    pais_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    canal_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    campania: Mapped[Optional[str]] = mapped_column(String(120))
    asesor_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    valor_estimado: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(14, 2))
    proxima_accion: Mapped[Optional[str]] = mapped_column(String(200))
    proxima_accion_fecha: Mapped[Optional[datetime.date]] = mapped_column(Date)
    motivo_perdida_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    motivo_perdida_nota: Mapped[Optional[str]] = mapped_column(Text)
    cerrado_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    ultimo_contacto_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    campania_id: Mapped[Optional[int]] = mapped_column(Integer)
    referido_por_cliente_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    asesor: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='oportunidades')
    campania_: Mapped[Optional['Campanias']] = relationship('Campanias', back_populates='oportunidades')
    canal: Mapped[Optional['Canales']] = relationship('Canales', back_populates='oportunidades')
    cliente: Mapped['Clientes'] = relationship('Clientes', foreign_keys=[cliente_id], back_populates='oportunidades_cliente')
    estado: Mapped['EstadosComerciales'] = relationship('EstadosComerciales', back_populates='oportunidades')
    motivo_perdida: Mapped[Optional['MotivosPerdida']] = relationship('MotivosPerdida', back_populates='oportunidades')
    pais: Mapped[Optional['Paises']] = relationship('Paises', back_populates='oportunidades')
    referido_por_cliente: Mapped[Optional['Clientes']] = relationship('Clientes', foreign_keys=[referido_por_cliente_id], back_populates='oportunidades_referido_por_cliente')
    servicio: Mapped[Optional['Servicios']] = relationship('Servicios', back_populates='oportunidades')
    negocios: Mapped[list['Negocios']] = relationship('Negocios', back_populates='oportunidad')
    tareas: Mapped[list['Tareas']] = relationship('Tareas', back_populates='oportunidad')
    alertas: Mapped[list['Alertas']] = relationship('Alertas', back_populates='oportunidad')


class Negocios(Base):
    __tablename__ = 'negocios'
    __table_args__ = (
        CheckConstraint('valor_lista >= 0::numeric AND descuento >= 0::numeric AND valor_pactado >= 0::numeric', name='ck_negocios_valores'),
        ForeignKeyConstraint(['canal_id'], ['canales.id'], name='negocios_canal_id_fkey'),
        ForeignKeyConstraint(['cliente_id'], ['clientes.id'], name='negocios_cliente_id_fkey'),
        ForeignKeyConstraint(['grupo_id'], ['grupos.id'], name='negocios_grupo_id_fkey'),
        ForeignKeyConstraint(['negocio_principal_id'], ['negocios.id'], name='negocios_negocio_principal_id_fkey'),
        ForeignKeyConstraint(['oportunidad_id'], ['oportunidades.id'], name='negocios_oportunidad_id_fkey'),
        ForeignKeyConstraint(['servicio_id'], ['servicios.id'], name='negocios_servicio_id_fkey'),
        ForeignKeyConstraint(['vendedor_id'], ['usuarios.id'], name='negocios_vendedor_id_fkey'),
        PrimaryKeyConstraint('id', name='negocios_pkey'),
        Index('ix_negocios_principal', 'negocio_principal_id', postgresql_where='(negocio_principal_id IS NOT NULL)'),
        Index('ux_negocios_origen', 'origen_archivo', 'origen_hoja', 'origen_fila', postgresql_where='(origen_archivo IS NOT NULL)', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    servicio_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_venta: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    cantidad_solicitantes: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text('1'))
    valor_lista: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    descuento: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default=text('0'))
    valor_pactado: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default=text("'COP'::bpchar"))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    grupo_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    oportunidad_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    vendedor_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    canal_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    observaciones: Mapped[Optional[str]] = mapped_column(Text)
    origen_archivo: Mapped[Optional[str]] = mapped_column(String(80))
    origen_hoja: Mapped[Optional[str]] = mapped_column(String(40))
    origen_fila: Mapped[Optional[int]] = mapped_column(Integer)
    migrado_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    negocio_principal_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    canal: Mapped[Optional['Canales']] = relationship('Canales', back_populates='negocios')
    cliente: Mapped['Clientes'] = relationship('Clientes', back_populates='negocios')
    grupo: Mapped[Optional['Grupos']] = relationship('Grupos', back_populates='negocios')
    negocio_principal: Mapped[Optional['Negocios']] = relationship('Negocios', remote_side=[id], back_populates='negocio_principal_reverse')
    negocio_principal_reverse: Mapped[list['Negocios']] = relationship('Negocios', remote_side=[negocio_principal_id], back_populates='negocio_principal')
    oportunidad: Mapped[Optional['Oportunidades']] = relationship('Oportunidades', back_populates='negocios')
    servicio: Mapped['Servicios'] = relationship('Servicios', back_populates='negocios')
    vendedor: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='negocios')
    ajustes_negocio: Mapped[list['AjustesNegocio']] = relationship('AjustesNegocio', back_populates='negocio')
    casos: Mapped[list['Casos']] = relationship('Casos', back_populates='negocio')
    comisiones: Mapped[list['Comisiones']] = relationship('Comisiones', back_populates='negocio')
    cuotas_negocio: Mapped[list['CuotasNegocio']] = relationship('CuotasNegocio', back_populates='negocio')
    pagos: Mapped[list['Pagos']] = relationship('Pagos', back_populates='negocio')
    gastos: Mapped[list['Gastos']] = relationship('Gastos', back_populates='negocio')
    migracion_filas: Mapped[list['MigracionFilas']] = relationship('MigracionFilas', back_populates='negocio')
    tareas: Mapped[list['Tareas']] = relationship('Tareas', back_populates='negocio')
    alertas: Mapped[list['Alertas']] = relationship('Alertas', back_populates='negocio')


class Solicitantes(Base):
    __tablename__ = 'solicitantes'
    __table_args__ = (
        CheckConstraint('grupo_id IS NOT NULL OR cliente_id IS NOT NULL', name='ck_solicitante_vinculado'),
        ForeignKeyConstraint(['cliente_id'], ['clientes.id'], name='solicitantes_cliente_id_fkey'),
        ForeignKeyConstraint(['fusionado_en_id'], ['solicitantes.id'], name='solicitantes_fusionado_en_id_fkey'),
        ForeignKeyConstraint(['grupo_id'], ['grupos.id'], name='solicitantes_grupo_id_fkey'),
        PrimaryKeyConstraint('id', name='solicitantes_pkey'),
        Index('ix_solicitantes_cliente', 'cliente_id', postgresql_where='(cliente_id IS NOT NULL)'),
        Index('ix_solicitantes_documento', 'numero_documento', postgresql_where='(numero_documento IS NOT NULL)'),
        Index('ix_solicitantes_email', 'email', postgresql_where='(email IS NOT NULL)'),
        Index('ix_solicitantes_grupo', 'grupo_id', postgresql_where='(grupo_id IS NOT NULL)'),
        Index('ix_solicitantes_nombre_busqueda', 'nombre_busqueda', postgresql_using='gin'),
        Index('ix_solicitantes_origen', 'origen_archivo', 'origen_hoja', 'origen_fila', postgresql_where='(origen_archivo IS NOT NULL)'),
        Index('ix_solicitantes_telefono_norm', 'telefono_normalizado', postgresql_where='(telefono_normalizado IS NOT NULL)'),
        Index('ux_solicitantes_pasaporte', 'pasaporte_indice', postgresql_where='(pasaporte_indice IS NOT NULL)', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    grupo_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    cliente_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    tipo_documento: Mapped[Optional[str]] = mapped_column(String(20))
    numero_documento: Mapped[Optional[str]] = mapped_column(String(40))
    pasaporte: Mapped[Optional[str]] = mapped_column(Text)
    fecha_nacimiento: Mapped[Optional[datetime.date]] = mapped_column(Date)
    nacionalidad: Mapped[Optional[str]] = mapped_column(String(80))
    telefono: Mapped[Optional[str]] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(CITEXT)
    relacion_con_cliente: Mapped[Optional[str]] = mapped_column(String(40))
    observaciones: Mapped[Optional[str]] = mapped_column(Text)
    origen_archivo: Mapped[Optional[str]] = mapped_column(String(80))
    origen_hoja: Mapped[Optional[str]] = mapped_column(String(40))
    origen_fila: Mapped[Optional[int]] = mapped_column(Integer)
    migrado_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    fusionado_en_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    pasaporte_indice: Mapped[Optional[str]] = mapped_column(CHAR(64))
    nombre_busqueda: Mapped[Optional[str]] = mapped_column(Text, Computed('lower(sin_tildes((nombre)::text))', persisted=True))
    telefono_normalizado: Mapped[Optional[str]] = mapped_column(String(10), Computed('NULLIF("right"(regexp_replace((COALESCE(telefono, \'\'::character varying))::text, \'[^0-9]\'::text, \'\'::text, \'g\'::text), 10), \'\'::text)', persisted=True))

    cliente: Mapped[Optional['Clientes']] = relationship('Clientes', back_populates='solicitantes')
    fusionado_en: Mapped[Optional['Solicitantes']] = relationship('Solicitantes', remote_side=[id], back_populates='fusionado_en_reverse')
    fusionado_en_reverse: Mapped[list['Solicitantes']] = relationship('Solicitantes', remote_side=[fusionado_en_id], back_populates='fusionado_en')
    grupo: Mapped[Optional['Grupos']] = relationship('Grupos', back_populates='solicitantes')
    casos: Mapped[list['Casos']] = relationship('Casos', back_populates='solicitante')
    migracion_filas: Mapped[list['MigracionFilas']] = relationship('MigracionFilas', back_populates='solicitante')


class AjustesNegocio(Base):
    __tablename__ = 'ajustes_negocio'
    __table_args__ = (
        CheckConstraint("(tipo::text = ANY (ARRAY['reembolso'::character varying, 'cargo'::character varying]::text[])) AND monto > 0::numeric OR (tipo::text = ANY (ARRAY['descuento'::character varying, 'condonacion'::character varying]::text[])) AND monto < 0::numeric", name='ck_ajustes_signo'),
        CheckConstraint("tipo::text = ANY (ARRAY['reembolso'::character varying, 'cargo'::character varying, 'descuento'::character varying, 'condonacion'::character varying]::text[])", name='ajustes_negocio_tipo_check'),
        ForeignKeyConstraint(['autorizado_por'], ['usuarios.id'], name='ajustes_negocio_autorizado_por_fkey'),
        ForeignKeyConstraint(['negocio_id'], ['negocios.id'], name='ajustes_negocio_negocio_id_fkey'),
        PrimaryKeyConstraint('id', name='ajustes_negocio_pkey')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    monto: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    autorizado_por: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fecha: Mapped[datetime.date] = mapped_column(Date, nullable=False, server_default=text('CURRENT_DATE'))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    usuarios: Mapped['Usuarios'] = relationship('Usuarios', back_populates='ajustes_negocio')
    negocio: Mapped['Negocios'] = relationship('Negocios', back_populates='ajustes_negocio')


class Casos(Base):
    __tablename__ = 'casos'
    __table_args__ = (
        CheckConstraint("fuente::text = ANY (ARRAY['saas'::character varying, 'manual'::character varying, 'hibrido'::character varying]::text[])", name='casos_fuente_check'),
        CheckConstraint("resultado::text = ANY (ARRAY['aprobada'::character varying, 'negada'::character varying, 'proceso_administrativo'::character varying, 'cancelado'::character varying, 'no_continuo'::character varying]::text[])", name='casos_resultado_check'),
        ForeignKeyConstraint(['estado_id'], ['estados_operativos.id'], name='casos_estado_id_fkey'),
        ForeignKeyConstraint(['modalidad_id'], ['modalidades.id'], name='casos_modalidad_id_fkey'),
        ForeignKeyConstraint(['negocio_id'], ['negocios.id'], name='casos_negocio_id_fkey'),
        ForeignKeyConstraint(['pais_id'], ['paises.id'], name='casos_pais_id_fkey'),
        ForeignKeyConstraint(['responsable_id'], ['usuarios.id'], name='casos_responsable_id_fkey'),
        ForeignKeyConstraint(['sede_id'], ['sedes.id'], name='casos_sede_id_fkey'),
        ForeignKeyConstraint(['solicitante_id'], ['solicitantes.id'], name='casos_solicitante_id_fkey'),
        ForeignKeyConstraint(['tipo_visa_id'], ['tipos_visa.id'], name='casos_tipo_visa_id_fkey'),
        PrimaryKeyConstraint('id', name='casos_pkey'),
        Index('ix_casos_etapa_saas', 'etapa_saas', postgresql_where='(etapa_saas IS NOT NULL)'),
        Index('ix_casos_id_externo', 'id_externo', postgresql_where='(id_externo IS NOT NULL)'),
        Index('ix_casos_sin_asignar', 'creado_en', postgresql_where='(responsable_id IS NULL)'),
        Index('ix_casos_sin_venta', 'creado_en', postgresql_where='(negocio_id IS NULL)'),
        Index('ix_casos_solicitante', 'solicitante_id'),
        Index('ix_casos_tablero', 'estado_id', 'responsable_id', 'ultima_actividad_en'),
        Index('ux_casos_ds160', 'ds160_hash', postgresql_where='(ds160_hash IS NOT NULL)', unique=True),
        Index('ux_casos_origen', 'origen_archivo', 'origen_hoja', 'origen_fila', postgresql_where='(origen_archivo IS NOT NULL)', unique=True),
        Index('ux_casos_solicitud_solicitante', 'id_externo', 'solicitante_id', postgresql_where='(id_externo IS NOT NULL)', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    solicitante_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pais_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fuente: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'manual'::character varying"))
    estado_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ultima_actividad_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    negocio_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    tipo_visa_id: Mapped[Optional[int]] = mapped_column(Integer)
    modalidad_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    sede_id: Mapped[Optional[int]] = mapped_column(Integer)
    id_externo: Mapped[Optional[str]] = mapped_column(String(60))
    sincronizado_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    responsable_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    resultado: Mapped[Optional[str]] = mapped_column(String(30))
    resultado_fecha: Mapped[Optional[datetime.date]] = mapped_column(Date)
    resultado_nota: Mapped[Optional[str]] = mapped_column(Text)
    origen_archivo: Mapped[Optional[str]] = mapped_column(String(80))
    origen_hoja: Mapped[Optional[str]] = mapped_column(String(40))
    origen_fila: Mapped[Optional[int]] = mapped_column(Integer)
    migrado_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    ds160_enviado_en: Mapped[Optional[datetime.date]] = mapped_column(Date)
    ds160_numero_cifrado: Mapped[Optional[str]] = mapped_column(Text)
    ds160_hash: Mapped[Optional[str]] = mapped_column(CHAR(64), comment='Índice ciego (HMAC-SHA256 en hexadecimal) del número de DS-160, para buscarlo sin descifrar ds160_numero_cifrado')
    busqueda_citas: Mapped[Optional[str]] = mapped_column(String(20))
    etapa_saas: Mapped[Optional[str]] = mapped_column(String(80))
    proxima_accion: Mapped[Optional[str]] = mapped_column(String(200))
    proxima_accion_fecha: Mapped[Optional[datetime.date]] = mapped_column(Date)

    estado: Mapped['EstadosOperativos'] = relationship('EstadosOperativos', back_populates='casos')
    modalidad: Mapped[Optional['Modalidades']] = relationship('Modalidades', back_populates='casos')
    negocio: Mapped[Optional['Negocios']] = relationship('Negocios', back_populates='casos')
    pais: Mapped['Paises'] = relationship('Paises', back_populates='casos')
    responsable: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='casos')
    sede: Mapped[Optional['Sedes']] = relationship('Sedes', back_populates='casos')
    solicitante: Mapped['Solicitantes'] = relationship('Solicitantes', back_populates='casos')
    tipo_visa: Mapped[Optional['TiposVisa']] = relationship('TiposVisa', back_populates='casos')
    casos_checklist: Mapped[list['CasosChecklist']] = relationship('CasosChecklist', back_populates='caso')
    casos_historial: Mapped[list['CasosHistorial']] = relationship('CasosHistorial', back_populates='caso')
    citas: Mapped[list['Citas']] = relationship('Citas', back_populates='caso')
    conflictos_sincronizacion: Mapped[list['ConflictosSincronizacion']] = relationship('ConflictosSincronizacion', back_populates='caso')
    gastos: Mapped[list['Gastos']] = relationship('Gastos', back_populates='caso')
    importaciones_filas: Mapped[list['ImportacionesFilas']] = relationship('ImportacionesFilas', back_populates='caso')
    migracion_filas: Mapped[list['MigracionFilas']] = relationship('MigracionFilas', back_populates='caso')
    tareas: Mapped[list['Tareas']] = relationship('Tareas', back_populates='caso')
    alertas: Mapped[list['Alertas']] = relationship('Alertas', back_populates='caso')


class Comisiones(Base):
    __tablename__ = 'comisiones'
    __table_args__ = (
        CheckConstraint("estado::text = ANY (ARRAY['provisional'::character varying, 'causada'::character varying, 'liquidada'::character varying, 'anulada'::character varying]::text[])", name='comisiones_estado_check'),
        ForeignKeyConstraint(['liquidacion_id'], ['liquidaciones_comision.id'], name='comisiones_liquidacion_id_fkey'),
        ForeignKeyConstraint(['negocio_id'], ['negocios.id'], name='comisiones_negocio_id_fkey'),
        ForeignKeyConstraint(['regla_id'], ['comisiones_reglas.id'], name='comisiones_regla_id_fkey'),
        ForeignKeyConstraint(['vendedor_id'], ['usuarios.id'], name='comisiones_vendedor_id_fkey'),
        PrimaryKeyConstraint('id', name='comisiones_pkey'),
        UniqueConstraint('negocio_id', 'vendedor_id', 'regla_id', name='comisiones_negocio_id_vendedor_id_regla_id_key'),
        Index('ix_comisiones_liquidacion', 'liquidacion_id', postgresql_where='(liquidacion_id IS NOT NULL)'),
        Index('ix_comisiones_vendedor', 'vendedor_id', 'periodo', 'estado')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vendedor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    regla_aplicada: Mapped[dict] = mapped_column(JSONB, nullable=False)
    base_calculo: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    monto: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'provisional'::character varying"))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    regla_id: Mapped[Optional[int]] = mapped_column(Integer)
    periodo: Mapped[Optional[datetime.date]] = mapped_column(Date)
    liquidacion_id: Mapped[Optional[int]] = mapped_column(BigInteger, comment='En qué corte se pagó. Mientras sea nulo, la comisión no se ha pagado.')

    liquidacion: Mapped[Optional['LiquidacionesComision']] = relationship('LiquidacionesComision', back_populates='comisiones')
    negocio: Mapped['Negocios'] = relationship('Negocios', back_populates='comisiones')
    regla: Mapped[Optional['ComisionesReglas']] = relationship('ComisionesReglas', back_populates='comisiones')
    vendedor: Mapped['Usuarios'] = relationship('Usuarios', back_populates='comisiones')


class CuotasNegocio(Base):
    __tablename__ = 'cuotas_negocio'
    __table_args__ = (
        CheckConstraint('monto > 0::numeric', name='cuotas_negocio_monto_check'),
        ForeignKeyConstraint(['negocio_id'], ['negocios.id'], ondelete='CASCADE', name='cuotas_negocio_negocio_id_fkey'),
        PrimaryKeyConstraint('id', name='cuotas_negocio_pkey'),
        UniqueConstraint('negocio_id', 'numero', name='cuotas_negocio_negocio_id_numero_key'),
        Index('ix_cuotas_fecha', 'fecha_pactada'),
        Index('ix_cuotas_negocio_origen', 'origen_archivo', 'origen_hoja', 'origen_fila', postgresql_where='(origen_archivo IS NOT NULL)')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    negocio_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    numero: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    concepto: Mapped[str] = mapped_column(String(60), nullable=False, server_default=text("'abono'::character varying"))
    monto: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fecha_pactada: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    origen_archivo: Mapped[Optional[str]] = mapped_column(String(80))
    origen_hoja: Mapped[Optional[str]] = mapped_column(String(60))
    origen_fila: Mapped[Optional[int]] = mapped_column(Integer)

    negocio: Mapped['Negocios'] = relationship('Negocios', back_populates='cuotas_negocio')


class Pagos(Base):
    __tablename__ = 'pagos'
    __table_args__ = (
        CheckConstraint("estado::text = ANY (ARRAY['confirmado'::character varying, 'pendiente'::character varying, 'no_identificado'::character varying, 'reversado'::character varying, 'duplicado'::character varying]::text[])", name='pagos_estado_check'),
        CheckConstraint('monto_bruto > 0::numeric AND costo_medio >= 0::numeric AND costo_medio <= monto_bruto', name='ck_pagos_montos'),
        ForeignKeyConstraint(['banco_cuenta_id'], ['bancos_cuentas.id'], name='pagos_banco_cuenta_id_fkey'),
        ForeignKeyConstraint(['medio_pago_id'], ['medios_pago.id'], name='pagos_medio_pago_id_fkey'),
        ForeignKeyConstraint(['negocio_id'], ['negocios.id'], name='pagos_negocio_id_fkey'),
        ForeignKeyConstraint(['registrado_por'], ['usuarios.id'], name='pagos_registrado_por_fkey'),
        PrimaryKeyConstraint('id', name='pagos_pkey'),
        Index('ix_pagos_origen', 'origen_archivo', 'origen_hoja', 'origen_fila', postgresql_where='(origen_archivo IS NOT NULL)')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fecha: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    monto_bruto: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    costo_medio: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default=text('0'))
    moneda: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default=text("'COP'::bpchar"))
    estado: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'confirmado'::character varying"))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    negocio_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    monto_neto: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(14, 2), Computed('(monto_bruto - costo_medio)', persisted=True))
    medio_pago_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    banco_cuenta_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    referencia: Mapped[Optional[str]] = mapped_column(String(80))
    comprobante_url: Mapped[Optional[str]] = mapped_column(Text)
    observacion: Mapped[Optional[str]] = mapped_column(Text)
    registrado_por: Mapped[Optional[int]] = mapped_column(BigInteger)
    origen_archivo: Mapped[Optional[str]] = mapped_column(String(80))
    origen_hoja: Mapped[Optional[str]] = mapped_column(String(40))
    origen_fila: Mapped[Optional[int]] = mapped_column(Integer)
    migrado_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    pagador_nombre: Mapped[Optional[str]] = mapped_column(String(160))

    banco_cuenta: Mapped[Optional['BancosCuentas']] = relationship('BancosCuentas', back_populates='pagos')
    medio_pago: Mapped[Optional['MediosPago']] = relationship('MediosPago', back_populates='pagos')
    negocio: Mapped[Optional['Negocios']] = relationship('Negocios', back_populates='pagos')
    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='pagos')
    movimientos_banco: Mapped[list['MovimientosBanco']] = relationship('MovimientosBanco', back_populates='pago')


class CasosChecklist(Base):
    __tablename__ = 'casos_checklist'
    __table_args__ = (
        ForeignKeyConstraint(['caso_id'], ['casos.id'], ondelete='CASCADE', name='casos_checklist_caso_id_fkey'),
        ForeignKeyConstraint(['cumplido_por'], ['usuarios.id'], name='casos_checklist_cumplido_por_fkey'),
        ForeignKeyConstraint(['item_id'], ['checklist_items.id'], name='casos_checklist_item_id_fkey'),
        PrimaryKeyConstraint('id', name='casos_checklist_pkey'),
        UniqueConstraint('caso_id', 'item_id', name='casos_checklist_caso_id_item_id_key'),
        Index('ix_casos_checklist_caso', 'caso_id', postgresql_where='(NOT cumplido)')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    caso_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cumplido: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    cumplido_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    cumplido_por: Mapped[Optional[int]] = mapped_column(BigInteger)
    observacion: Mapped[Optional[str]] = mapped_column(Text)

    caso: Mapped['Casos'] = relationship('Casos', back_populates='casos_checklist')
    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='casos_checklist')
    item: Mapped['ChecklistItems'] = relationship('ChecklistItems', back_populates='casos_checklist')


class CasosHistorial(Base):
    __tablename__ = 'casos_historial'
    __table_args__ = (
        ForeignKeyConstraint(['caso_id'], ['casos.id'], name='casos_historial_caso_id_fkey'),
        ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name='casos_historial_usuario_id_fkey'),
        PrimaryKeyConstraint('id', name='casos_historial_pkey'),
        Index('ix_historial_caso', 'caso_id', 'ocurrido_en')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    caso_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    campo: Mapped[str] = mapped_column(String(60), nullable=False)
    ocurrido_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    valor_anterior: Mapped[Optional[str]] = mapped_column(Text)
    valor_nuevo: Mapped[Optional[str]] = mapped_column(Text)
    usuario_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    observacion: Mapped[Optional[str]] = mapped_column(Text)

    caso: Mapped['Casos'] = relationship('Casos', back_populates='casos_historial')
    usuario: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='casos_historial')


class Citas(Base):
    __tablename__ = 'citas'
    __table_args__ = (
        CheckConstraint("estado::text = ANY (ARRAY['pendiente'::character varying, 'programada'::character varying, 'confirmada'::character varying, 'reprogramada'::character varying, 'realizada'::character varying, 'cancelada'::character varying]::text[])", name='citas_estado_check'),
        CheckConstraint("tipo::text = ANY (ARRAY['cas'::character varying, 'biometria'::character varying, 'entrevista'::character varying, 'radicacion'::character varying, 'preparacion'::character varying, 'entrega'::character varying, 'otra'::character varying]::text[])", name='citas_tipo_check'),
        ForeignKeyConstraint(['caso_id'], ['casos.id'], name='citas_caso_id_fkey'),
        ForeignKeyConstraint(['sede_id'], ['sedes.id'], name='citas_sede_id_fkey'),
        PrimaryKeyConstraint('id', name='citas_pkey'),
        Index('ix_citas_caso', 'caso_id', 'inicia_en'),
        Index('ix_citas_origen', 'origen_archivo', 'origen_hoja', 'origen_fila', postgresql_where='(origen_archivo IS NOT NULL)'),
        Index('ix_citas_proximas', 'inicia_en', postgresql_where="((estado)::text = ANY ((ARRAY['pendiente'::character varying, 'programada'::character varying, 'confirmada'::character varying])::text[]))")
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    caso_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    inicia_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    zona_horaria: Mapped[str] = mapped_column(String(40), nullable=False, server_default=text("'America/Bogota'::character varying"))
    estado: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pendiente'::character varying"))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    sede_id: Mapped[Optional[int]] = mapped_column(Integer)
    observaciones: Mapped[Optional[str]] = mapped_column(Text)
    origen_archivo: Mapped[Optional[str]] = mapped_column(String(80))
    origen_hoja: Mapped[Optional[str]] = mapped_column(String(60))
    origen_fila: Mapped[Optional[int]] = mapped_column(Integer)

    caso: Mapped['Casos'] = relationship('Casos', back_populates='citas')
    sede: Mapped[Optional['Sedes']] = relationship('Sedes', back_populates='citas')
    alertas: Mapped[list['Alertas']] = relationship('Alertas', back_populates='cita')


class ConflictosSincronizacion(Base):
    __tablename__ = 'conflictos_sincronizacion'
    __table_args__ = (
        CheckConstraint("estado::text = ANY (ARRAY['abierto'::character varying, 'resuelto_visanow'::character varying, 'resuelto_saas'::character varying, 'ignorado'::character varying]::text[])", name='conflictos_sincronizacion_estado_check'),
        ForeignKeyConstraint(['caso_id'], ['casos.id'], name='conflictos_sincronizacion_caso_id_fkey'),
        ForeignKeyConstraint(['importacion_id'], ['importaciones.id'], name='conflictos_sincronizacion_importacion_id_fkey'),
        ForeignKeyConstraint(['resuelto_por'], ['usuarios.id'], name='conflictos_sincronizacion_resuelto_por_fkey'),
        PrimaryKeyConstraint('id', name='conflictos_sincronizacion_pkey'),
        Index('ix_conflictos_abiertos', 'caso_id', postgresql_where="((estado)::text = 'abierto'::text)")
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    caso_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    campo: Mapped[str] = mapped_column(String(60), nullable=False)
    estado: Mapped[str] = mapped_column(String(18), nullable=False, server_default=text("'abierto'::character varying"))
    detectado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    importacion_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    valor_visanow: Mapped[Optional[str]] = mapped_column(Text)
    valor_saas: Mapped[Optional[str]] = mapped_column(Text)
    resuelto_por: Mapped[Optional[int]] = mapped_column(BigInteger)
    resuelto_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    caso: Mapped['Casos'] = relationship('Casos', back_populates='conflictos_sincronizacion')
    importacion: Mapped[Optional['Importaciones']] = relationship('Importaciones', back_populates='conflictos_sincronizacion')
    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='conflictos_sincronizacion')


class Gastos(Base):
    __tablename__ = 'gastos'
    __table_args__ = (
        CheckConstraint("estado::text = ANY (ARRAY['pagado'::character varying, 'pendiente'::character varying, 'anulado'::character varying]::text[])", name='gastos_estado_check'),
        CheckConstraint('monto > 0::numeric', name='gastos_monto_check'),
        ForeignKeyConstraint(['banco_cuenta_id'], ['bancos_cuentas.id'], name='gastos_banco_cuenta_id_fkey'),
        ForeignKeyConstraint(['caso_id'], ['casos.id'], name='gastos_caso_id_fkey'),
        ForeignKeyConstraint(['categoria_id'], ['categorias_gasto.id'], name='gastos_categoria_id_fkey'),
        ForeignKeyConstraint(['medio_pago_id'], ['medios_pago.id'], name='gastos_medio_pago_id_fkey'),
        ForeignKeyConstraint(['negocio_id'], ['negocios.id'], name='gastos_negocio_id_fkey'),
        ForeignKeyConstraint(['proveedor_id'], ['proveedores.id'], name='gastos_proveedor_id_fkey'),
        ForeignKeyConstraint(['registrado_por'], ['usuarios.id'], name='gastos_registrado_por_fkey'),
        PrimaryKeyConstraint('id', name='gastos_pkey'),
        Index('ix_gastos_caso', 'caso_id', postgresql_where='(caso_id IS NOT NULL)'),
        Index('ix_gastos_categoria', 'categoria_id', 'fecha'),
        Index('ix_gastos_fecha', 'fecha'),
        Index('ix_gastos_negocio', 'negocio_id', postgresql_where='(negocio_id IS NOT NULL)')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    categoria_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    concepto: Mapped[str] = mapped_column(String(200), nullable=False)
    fecha: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    monto: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default=text("'COP'::bpchar"))
    estado: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'pagado'::character varying"))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    proveedor_id: Mapped[Optional[int]] = mapped_column(Integer)
    negocio_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    caso_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    medio_pago_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    banco_cuenta_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    comprobante_url: Mapped[Optional[str]] = mapped_column(Text)
    observacion: Mapped[Optional[str]] = mapped_column(Text)
    registrado_por: Mapped[Optional[int]] = mapped_column(BigInteger)

    banco_cuenta: Mapped[Optional['BancosCuentas']] = relationship('BancosCuentas', back_populates='gastos')
    caso: Mapped[Optional['Casos']] = relationship('Casos', back_populates='gastos')
    categoria: Mapped['CategoriasGasto'] = relationship('CategoriasGasto', back_populates='gastos')
    medio_pago: Mapped[Optional['MediosPago']] = relationship('MediosPago', back_populates='gastos')
    negocio: Mapped[Optional['Negocios']] = relationship('Negocios', back_populates='gastos')
    proveedor: Mapped[Optional['Proveedores']] = relationship('Proveedores', back_populates='gastos')
    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='gastos')


class ImportacionesFilas(Base):
    __tablename__ = 'importaciones_filas'
    __table_args__ = (
        CheckConstraint("resultado::text = ANY (ARRAY['nuevo'::character varying, 'actualizado'::character varying, 'sin_cambio'::character varying, 'conflicto'::character varying, 'rechazado'::character varying]::text[])", name='importaciones_filas_resultado_check'),
        ForeignKeyConstraint(['caso_id'], ['casos.id'], name='importaciones_filas_caso_id_fkey'),
        ForeignKeyConstraint(['importacion_id'], ['importaciones.id'], ondelete='CASCADE', name='importaciones_filas_importacion_id_fkey'),
        PrimaryKeyConstraint('id', name='importaciones_filas_pkey'),
        UniqueConstraint('importacion_id', 'fila_numero', name='importaciones_filas_importacion_id_fila_numero_key'),
        Index('ix_importaciones_filas_idext', 'id_externo')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    importacion_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fila_numero: Mapped[int] = mapped_column(Integer, nullable=False)
    datos: Mapped[dict] = mapped_column(JSONB, nullable=False)
    resultado: Mapped[str] = mapped_column(String(15), nullable=False)
    id_externo: Mapped[Optional[str]] = mapped_column(String(60))
    caso_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    detalle: Mapped[Optional[str]] = mapped_column(Text)

    caso: Mapped[Optional['Casos']] = relationship('Casos', back_populates='importaciones_filas')
    importacion: Mapped['Importaciones'] = relationship('Importaciones', back_populates='importaciones_filas')


class MigracionFilas(Base):
    __tablename__ = 'migracion_filas'
    __table_args__ = (
        CheckConstraint("resultado::text = ANY (ARRAY['creado'::character varying, 'actualizado'::character varying, 'sin_cambios'::character varying, 'excepcion'::character varying, 'omitido'::character varying]::text[])", name='ck_migracion_filas_resultado'),
        ForeignKeyConstraint(['caso_id'], ['casos.id'], name='migracion_filas_caso_id_fkey'),
        ForeignKeyConstraint(['cliente_id'], ['clientes.id'], name='migracion_filas_cliente_id_fkey'),
        ForeignKeyConstraint(['corrida_id'], ['migracion_corridas.id'], ondelete='CASCADE', name='migracion_filas_corrida_id_fkey'),
        ForeignKeyConstraint(['negocio_id'], ['negocios.id'], name='migracion_filas_negocio_id_fkey'),
        ForeignKeyConstraint(['solicitante_id'], ['solicitantes.id'], name='migracion_filas_solicitante_id_fkey'),
        PrimaryKeyConstraint('id', name='migracion_filas_pkey'),
        Index('ix_migracion_filas_corrida', 'corrida_id', 'resultado'),
        Index('ix_migracion_filas_huella', 'huella'),
        Index('ux_migracion_filas_origen', 'archivo', 'hoja', 'fila', 'corrida_id', unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    corrida_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    archivo: Mapped[str] = mapped_column(String(80), nullable=False)
    hoja: Mapped[str] = mapped_column(String(60), nullable=False)
    fila: Mapped[int] = mapped_column(Integer, nullable=False)
    huella: Mapped[str] = mapped_column(CHAR(64), nullable=False, comment='sha256 del contenido normalizado de la fila. Si cambia, el Excel se editó después de migrar y la fila se vuelve a mirar.')
    resultado: Mapped[str] = mapped_column(String(15), nullable=False)
    motivo: Mapped[Optional[str]] = mapped_column(Text)
    cliente_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    solicitante_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    caso_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    negocio_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    caso: Mapped[Optional['Casos']] = relationship('Casos', back_populates='migracion_filas')
    cliente: Mapped[Optional['Clientes']] = relationship('Clientes', back_populates='migracion_filas')
    corrida: Mapped['MigracionCorridas'] = relationship('MigracionCorridas', back_populates='migracion_filas')
    negocio: Mapped[Optional['Negocios']] = relationship('Negocios', back_populates='migracion_filas')
    solicitante: Mapped[Optional['Solicitantes']] = relationship('Solicitantes', back_populates='migracion_filas')


class MovimientosBanco(Base):
    __tablename__ = 'movimientos_banco'
    __table_args__ = (
        CheckConstraint("(estado::text <> ALL (ARRAY['conciliado'::character varying, 'parcial'::character varying]::text[])) OR pago_id IS NOT NULL", name='movimientos_banco_conciliado_check'),
        CheckConstraint("(estado::text <> ALL (ARRAY['descartado'::character varying, 'reversado'::character varying]::text[])) OR motivo_descarte IS NOT NULL AND btrim(motivo_descarte::text) <> ''::text", name='movimientos_banco_motivo_check'),
        CheckConstraint('duplicado_de_id IS NULL OR duplicado_de_id <> id', name='movimientos_banco_no_se_duplica_a_si_mismo'),
        CheckConstraint("estado::text <> 'duplicado'::text OR duplicado_de_id IS NOT NULL", name='movimientos_banco_duplicado_check'),
        CheckConstraint("estado::text = ANY (ARRAY['sin_conciliar'::character varying, 'conciliado'::character varying, 'parcial'::character varying, 'duplicado'::character varying, 'reversado'::character varying, 'descartado'::character varying]::text[])", name='movimientos_banco_estado_check'),
        ForeignKeyConstraint(['banco_cuenta_id'], ['bancos_cuentas.id'], name='movimientos_banco_banco_cuenta_id_fkey'),
        ForeignKeyConstraint(['conciliado_por'], ['usuarios.id'], name='movimientos_banco_conciliado_por_fkey'),
        ForeignKeyConstraint(['duplicado_de_id'], ['movimientos_banco.id'], name='movimientos_banco_duplicado_de_id_fkey'),
        ForeignKeyConstraint(['pago_id'], ['pagos.id'], name='movimientos_banco_pago_id_fkey'),
        PrimaryKeyConstraint('id', name='movimientos_banco_pkey'),
        Index('ix_movimientos_banco_bandeja', 'estado', 'fecha'),
        Index('ix_movimientos_banco_cruce', 'valor', 'fecha', postgresql_where="((estado)::text = 'sin_conciliar'::text)"),
        Index('ux_movimientos_banco_huella', 'huella', unique=True),
        Index('ux_movimientos_banco_pago', 'pago_id', postgresql_where="((pago_id IS NOT NULL) AND ((estado)::text = 'conciliado'::text))", unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    banco: Mapped[str] = mapped_column(String(60), nullable=False)
    fecha: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    valor: Mapped[decimal.Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default=text("'COP'::bpchar"))
    estado: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'sin_conciliar'::character varying"))
    huella: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    banco_cuenta_id: Mapped[Optional[int]] = mapped_column(SmallInteger)
    descripcion: Mapped[Optional[str]] = mapped_column(String(300))
    referencia: Mapped[Optional[str]] = mapped_column(String(120))
    pago_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    motivo_descarte: Mapped[Optional[str]] = mapped_column(String(300))
    duplicado_de_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    nota_cliente: Mapped[Optional[str]] = mapped_column(String(200))
    nota_abono: Mapped[Optional[str]] = mapped_column(String(60))
    observacion: Mapped[Optional[str]] = mapped_column(Text)
    origen_archivo: Mapped[Optional[str]] = mapped_column(String(120))
    origen_hoja: Mapped[Optional[str]] = mapped_column(String(60))
    origen_fila: Mapped[Optional[int]] = mapped_column(Integer)
    conciliado_por: Mapped[Optional[int]] = mapped_column(BigInteger)
    conciliado_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    banco_cuenta: Mapped[Optional['BancosCuentas']] = relationship('BancosCuentas', back_populates='movimientos_banco')
    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', back_populates='movimientos_banco')
    duplicado_de: Mapped[Optional['MovimientosBanco']] = relationship('MovimientosBanco', remote_side=[id], back_populates='duplicado_de_reverse')
    duplicado_de_reverse: Mapped[list['MovimientosBanco']] = relationship('MovimientosBanco', remote_side=[duplicado_de_id], back_populates='duplicado_de')
    pago: Mapped[Optional['Pagos']] = relationship('Pagos', back_populates='movimientos_banco')


class Tareas(Base):
    __tablename__ = 'tareas'
    __table_args__ = (
        CheckConstraint("estado::text = ANY (ARRAY['pendiente'::character varying, 'en_curso'::character varying, 'hecha'::character varying, 'cancelada'::character varying]::text[])", name='tareas_estado_check'),
        CheckConstraint('num_nonnulls(caso_id, negocio_id, oportunidad_id, cliente_id) >= 1', name='ck_tareas_vinculo'),
        CheckConstraint("origen::text = ANY (ARRAY['manual'::character varying, 'automatica'::character varying]::text[])", name='tareas_origen_check'),
        CheckConstraint("prioridad::text = ANY (ARRAY['baja'::character varying, 'media'::character varying, 'alta'::character varying]::text[])", name='tareas_prioridad_check'),
        ForeignKeyConstraint(['caso_id'], ['casos.id'], name='tareas_caso_id_fkey'),
        ForeignKeyConstraint(['cliente_id'], ['clientes.id'], name='tareas_cliente_id_fkey'),
        ForeignKeyConstraint(['creado_por'], ['usuarios.id'], name='tareas_creado_por_fkey'),
        ForeignKeyConstraint(['negocio_id'], ['negocios.id'], name='tareas_negocio_id_fkey'),
        ForeignKeyConstraint(['oportunidad_id'], ['oportunidades.id'], name='tareas_oportunidad_id_fkey'),
        ForeignKeyConstraint(['responsable_id'], ['usuarios.id'], name='tareas_responsable_id_fkey'),
        PrimaryKeyConstraint('id', name='tareas_pkey'),
        Index('ix_tareas_bandeja', 'responsable_id', 'estado', 'vence_en'),
        Index('ix_tareas_caso', 'caso_id', postgresql_where='(caso_id IS NOT NULL)')
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    responsable_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prioridad: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'media'::character varying"))
    estado: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'pendiente'::character varying"))
    origen: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'manual'::character varying"))
    creado_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    caso_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    negocio_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    oportunidad_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    cliente_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    vence_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    cerrada_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    creado_por: Mapped[Optional[int]] = mapped_column(BigInteger)

    caso: Mapped[Optional['Casos']] = relationship('Casos', back_populates='tareas')
    cliente: Mapped[Optional['Clientes']] = relationship('Clientes', back_populates='tareas')
    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', foreign_keys=[creado_por], back_populates='tareas_creado_por')
    negocio: Mapped[Optional['Negocios']] = relationship('Negocios', back_populates='tareas')
    oportunidad: Mapped[Optional['Oportunidades']] = relationship('Oportunidades', back_populates='tareas')
    responsable: Mapped['Usuarios'] = relationship('Usuarios', foreign_keys=[responsable_id], back_populates='tareas_responsable')
    alertas: Mapped[list['Alertas']] = relationship('Alertas', back_populates='tarea')


class Alertas(Base):
    __tablename__ = 'alertas'
    __table_args__ = (
        CheckConstraint("estado::text = ANY (ARRAY['nueva'::character varying, 'vista'::character varying, 'resuelta'::character varying, 'pospuesta'::character varying]::text[])", name='alertas_estado_check'),
        ForeignKeyConstraint(['caso_id'], ['casos.id'], name='alertas_caso_id_fkey'),
        ForeignKeyConstraint(['cita_id'], ['citas.id'], name='alertas_cita_id_fkey'),
        ForeignKeyConstraint(['destinatario_id'], ['usuarios.id'], name='alertas_destinatario_id_fkey'),
        ForeignKeyConstraint(['negocio_id'], ['negocios.id'], name='alertas_negocio_id_fkey'),
        ForeignKeyConstraint(['oportunidad_id'], ['oportunidades.id'], name='alertas_oportunidad_id_fkey'),
        ForeignKeyConstraint(['resuelta_por'], ['usuarios.id'], name='alertas_resuelta_por_fkey'),
        ForeignKeyConstraint(['tarea_id'], ['tareas.id'], name='alertas_tarea_id_fkey'),
        ForeignKeyConstraint(['tipo_id'], ['alertas_tipos.id'], name='alertas_tipo_id_fkey'),
        PrimaryKeyConstraint('id', name='alertas_pkey'),
        Index('ix_alertas_bandeja', 'destinatario_id', 'estado', 'generada_en'),
        Index('ux_alertas_dedupe', 'tipo_id', 'clave_dedupe', postgresql_where="((estado)::text = ANY ((ARRAY['nueva'::character varying, 'vista'::character varying, 'pospuesta'::character varying])::text[]))", unique=True)
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tipo_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    clave_dedupe: Mapped[str] = mapped_column(String(120), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'nueva'::character varying"))
    generada_en: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    caso_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    negocio_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    oportunidad_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    cita_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    tarea_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    destinatario_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    vence_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    pospuesta_hasta: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    resuelta_en: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    resuelta_por: Mapped[Optional[int]] = mapped_column(BigInteger)

    caso: Mapped[Optional['Casos']] = relationship('Casos', back_populates='alertas')
    cita: Mapped[Optional['Citas']] = relationship('Citas', back_populates='alertas')
    destinatario: Mapped[Optional['Usuarios']] = relationship('Usuarios', foreign_keys=[destinatario_id], back_populates='alertas_destinatario')
    negocio: Mapped[Optional['Negocios']] = relationship('Negocios', back_populates='alertas')
    oportunidad: Mapped[Optional['Oportunidades']] = relationship('Oportunidades', back_populates='alertas')
    usuarios: Mapped[Optional['Usuarios']] = relationship('Usuarios', foreign_keys=[resuelta_por], back_populates='alertas_resuelta_por')
    tarea: Mapped[Optional['Tareas']] = relationship('Tareas', back_populates='alertas')
    tipo: Mapped['AlertasTipos'] = relationship('AlertasTipos', back_populates='alertas')
