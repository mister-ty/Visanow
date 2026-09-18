create extension if not exists citext;    -- correos sin distinguir mayúsculas
create extension if not exists pg_trgm;   -- similitud de nombres para duplicados

create table roles (
  id      smallserial primary key,
  codigo  varchar(20) unique not null,   -- administradora, comercial, operaciones,
  nombre  varchar(60) not null           -- finanzas, apoyo_externo, solo_lectura
);

create table usuarios (
  id             bigserial primary key,
  nombre         varchar(120) not null,
  email          citext unique not null,
  password_hash  text not null,          -- bcrypt o argon2, nunca el texto plano
  rol_id         smallint not null references roles(id),
  activo         boolean not null default true,
  mfa_habilitado boolean not null default false,
  mfa_secreto    text,
  ultimo_acceso  timestamptz,
  creado_en      timestamptz not null default now()
);

create table paises      (id smallserial primary key, iso2 char(2) unique, nombre varchar(80) not null);
create table sedes       (id serial primary key, pais_id smallint references paises(id),
                          nombre varchar(120) not null, ciudad varchar(80));
create table tipos_visa  (id serial primary key, pais_id smallint references paises(id),
                          codigo varchar(20), nombre varchar(80) not null, activo boolean default true);
create table modalidades (id smallserial primary key, codigo varchar(30) unique, nombre varchar(60) not null);
create table servicios   (id serial primary key, codigo varchar(30) unique, nombre varchar(100) not null,
                          descripcion text, activo boolean not null default true);
create table tarifas     (id serial primary key, servicio_id int not null references servicios(id),
                          valor numeric(14,2) not null, moneda char(3) not null default 'COP',
                          vigente_desde date not null, vigente_hasta date);
create table canales     (id smallserial primary key, codigo varchar(30) unique, nombre varchar(60) not null,
                          activo boolean not null default true);
create table motivos_perdida (id smallserial primary key, codigo varchar(30) unique, nombre varchar(80) not null);

create table medios_pago      (id smallserial primary key, codigo varchar(30) unique, nombre varchar(60) not null,
                               activo boolean not null default true);
create table bancos_cuentas   (id smallserial primary key, banco varchar(60) not null, numero varchar(40),
                               titular varchar(120), activo boolean not null default true);
create table categorias_gasto (id smallserial primary key, codigo varchar(30) unique, nombre varchar(60) not null);

create table estados_comerciales (
  id               smallserial primary key,
  codigo           varchar(30) unique not null,
  nombre           varchar(60) not null,
  orden            smallint not null,
  es_cierre        boolean not null default false,
  requiere_motivo  boolean not null default false,
  activo           boolean not null default true
);

create table estados_operativos (
  id               smallserial primary key,
  codigo           varchar(40) unique not null,
  nombre           varchar(80) not null,
  fase             varchar(20) not null,     -- inicio, informacion, revision, formulario,
  orden            smallint not null,        -- tasa, cita, preparacion, documentos,
  es_final         boolean not null default false,   -- decision, cierre, entrega, excepcion
  requiere_motivo  boolean not null default false,
  activo           boolean not null default true
);

create table transiciones_operativas (
  estado_origen_id    smallint not null references estados_operativos(id),
  estado_destino_id   smallint not null references estados_operativos(id),
  requiere_checklist  boolean not null default false,
  campos_obligatorios jsonb not null default '[]'::jsonb,
  primary key (estado_origen_id, estado_destino_id)
);

insert into estados_operativos (codigo, nombre, fase, orden) values
 ('registrado',            'Registrado / pendiente de asignación',        'inicio',      10),
 ('esperando_info',        'Esperando información del cliente',           'informacion', 20),
 ('info_incompleta',       'Información incompleta',                      'informacion', 30),
 ('info_en_revision',      'Información completa / en revisión',          'revision',    40),
 ('formulario_elaborando', 'Formulario en elaboración',                   'formulario',  50),
 ('formulario_enviado',    'Formulario enviado / aprobado por cliente',   'formulario',  60),
 ('pago_consular_pend',    'Pendiente de pago consular',                  'tasa',        70),
 ('busqueda_cita',         'Búsqueda de cita',                            'cita',        80),
 ('cita_confirmada',       'Cita asignada / confirmada',                  'cita',        90),
 ('preparacion',           'Preparación pendiente / programada / hecha',  'preparacion',100),
 ('checklist',             'Checklist pendiente / completo',              'documentos', 110),
 ('esperando_resultado',   'Esperando resultado',                         'decision',   120),
 ('con_resultado',         'Aprobada / negada / proceso administrativo',  'cierre',     130),
 ('entrega_documento',     'Pasaporte por recoger / enviar / entregado',  'entrega',    140),
 ('finalizado',            'Finalizado',                                  'cierre',     150),
 ('excepcion',             'Cancelado / no continuó / suspendido',        'excepcion',  160);

update estados_operativos set es_final = true       where codigo in ('finalizado','excepcion');
update estados_operativos set requiere_motivo = true where codigo = 'excepcion';

insert into estados_comerciales (codigo, nombre, orden) values
 ('nuevo_lead',         'Nuevo lead',         10),
 ('contactado',         'Contactado',         20),
 ('calificado',         'Calificado',         30),
 ('cotizacion_enviada', 'Cotización enviada', 40),
 ('seguimiento',        'Seguimiento',        50),
 ('ganado',             'Ganado',             60),
 ('perdido',            'Perdido',            70),
 ('en_pausa',           'En pausa',           80);

update estados_comerciales set es_cierre = true where codigo in ('ganado','perdido');
update estados_comerciales set requiere_motivo = true where codigo = 'perdido';

create table clientes (
  id                   bigserial primary key,
  nombre               varchar(160) not null,
  tipo_documento       varchar(20),
  numero_documento     varchar(40),
  telefono             varchar(30),
  email                citext,
  ciudad               varchar(80),
  pais_id              smallint references paises(id),
  canal_id             smallint references canales(id),
  consentimiento       boolean not null default false,
  consentimiento_fecha timestamptz,
  observaciones        text,
  archivado            boolean not null default false,
  creado_por           bigint references usuarios(id),
  creado_en            timestamptz not null default now(),
  actualizado_en       timestamptz not null default now()
);

-- Índices que sostienen la detección de duplicados (RF-002)
create unique index ux_clientes_documento on clientes (tipo_documento, numero_documento)
  where numero_documento is not null;
create index ix_clientes_telefono on clientes (telefono);
create index ix_clientes_email    on clientes (email);
create index ix_clientes_nombre   on clientes using gin (nombre gin_trgm_ops);

create table grupos (
  id                  bigserial primary key,
  nombre              varchar(160) not null,
  cliente_contacto_id bigint not null references clientes(id),
  observaciones       text,
  creado_en           timestamptz not null default now()
);

create table solicitantes (
  id                   bigserial primary key,
  grupo_id             bigint references grupos(id),
  cliente_id           bigint references clientes(id),   -- si además es el comprador
  nombre               varchar(160) not null,
  tipo_documento       varchar(20),
  numero_documento     varchar(40),
  pasaporte            varchar(80),                      -- cifrado en reposo (RNF-04)
  fecha_nacimiento     date,
  nacionalidad         varchar(80),
  telefono             varchar(30),
  email                citext,
  relacion_con_cliente varchar(40),                      -- titular, cónyuge, hijo, otro
  observaciones        text,
  creado_en            timestamptz not null default now()
);

create table oportunidades (
  id                   bigserial primary key,
  cliente_id           bigint not null references clientes(id),
  estado_id            smallint not null references estados_comerciales(id),
  servicio_id          int references servicios(id),
  pais_id              smallint references paises(id),
  canal_id             smallint references canales(id),
  campania             varchar(120),
  asesor_id            bigint references usuarios(id),
  valor_estimado       numeric(14,2),
  proxima_accion       varchar(200),
  proxima_accion_fecha date,
  motivo_perdida_id    smallint references motivos_perdida(id),
  motivo_perdida_nota  text,
  creado_en            timestamptz not null default now(),
  cerrado_en           timestamptz
);

create table negocios (
  id                    bigserial primary key,
  cliente_id            bigint not null references clientes(id),
  grupo_id              bigint references grupos(id),
  oportunidad_id        bigint references oportunidades(id),
  servicio_id           int not null references servicios(id),
  fecha_venta           date not null,
  cantidad_solicitantes smallint not null default 1,
  valor_lista           numeric(14,2) not null,
  descuento             numeric(14,2) not null default 0,
  valor_pactado         numeric(14,2) not null,
  moneda                char(3) not null default 'COP',
  vendedor_id           bigint references usuarios(id),
  canal_id              smallint references canales(id),
  observaciones         text,
  creado_en             timestamptz not null default now()
);

create table casos (
  id                  bigserial primary key,
  negocio_id          bigint not null references negocios(id),
  solicitante_id      bigint not null references solicitantes(id),
  pais_id             smallint not null references paises(id),
  tipo_visa_id        int references tipos_visa(id),
  modalidad_id        smallint references modalidades(id),
  sede_id             int references sedes(id),
  fuente              varchar(10) not null default 'manual'
                      check (fuente in ('saas','manual','hibrido')),
  id_externo          varchar(60),          -- n.º de solicitud del SaaS
  sincronizado_en     timestamptz,
  estado_id           smallint not null references estados_operativos(id),
  responsable_id      bigint references usuarios(id),
  resultado           varchar(30) check (resultado in
                      ('aprobada','negada','proceso_administrativo','cancelado','no_continuo')),
  resultado_fecha     date,
  resultado_nota      text,
  ultima_actividad_en timestamptz not null default now(),
  creado_en           timestamptz not null default now()
);

-- La llave de la importación idempotente (RF-032): dos cargas del mismo
-- archivo actualizan, no duplican.
create unique index ux_casos_id_externo on casos (id_externo) where id_externo is not null;

-- Historial: solo se inserta, nunca se actualiza ni se borra (RF-028, RN-08)
create table casos_historial (
  id             bigserial primary key,
  caso_id        bigint not null references casos(id),
  campo          varchar(60) not null,
  valor_anterior text,
  valor_nuevo    text,
  usuario_id     bigint references usuarios(id),
  observacion    text,
  ocurrido_en    timestamptz not null default now()
);

create table citas (
  id            bigserial primary key,
  caso_id       bigint not null references casos(id),
  tipo          varchar(20) not null check (tipo in
                ('cas','biometria','entrevista','radicacion','preparacion','entrega','otra')),
  sede_id       int references sedes(id),
  inicia_en     timestamptz not null,
  zona_horaria  varchar(40) not null default 'America/Bogota',
  estado        varchar(20) not null default 'pendiente' check (estado in
                ('pendiente','programada','confirmada','reprogramada','realizada','cancelada')),
  observaciones text,
  creado_en     timestamptz not null default now()
);

create table auditoria (
  id          bigserial primary key,
  usuario_id  bigint references usuarios(id),
  operacion   varchar(15) not null,     -- insert, update, delete, login, export
  entidad     varchar(40) not null,
  entidad_id  bigint,
  antes       jsonb,
  despues     jsonb,
  ip          inet,
  ocurrido_en timestamptz not null default now()
);

create table pagos (
  id              bigserial primary key,
  negocio_id      bigint references negocios(id),      -- nulo = pago sin identificar
  fecha           date not null,
  monto_bruto     numeric(14,2) not null,
  costo_medio     numeric(14,2) not null default 0,    -- comisión de pasarela
  monto_neto      numeric(14,2) generated always as (monto_bruto - costo_medio) stored,
  moneda          char(3) not null default 'COP',
  medio_pago_id   smallint references medios_pago(id),
  banco_cuenta_id smallint references bancos_cuentas(id),
  referencia      varchar(80),
  comprobante_url text,
  estado          varchar(20) not null default 'confirmado' check (estado in
                  ('confirmado','pendiente','no_identificado','reversado','duplicado')),
  observacion     text,
  registrado_por  bigint references usuarios(id),
  creado_en       timestamptz not null default now()
);

create table ajustes_negocio (
  id             bigserial primary key,
  negocio_id     bigint not null references negocios(id),
  tipo           varchar(20) not null check (tipo in
                 ('reembolso','cargo','descuento','condonacion')),
  monto          numeric(14,2) not null,        -- positivo aumenta el saldo
  motivo         text not null,
  autorizado_por bigint not null references usuarios(id),
  fecha          date not null default current_date,
  creado_en      timestamptz not null default now()
);

create view v_estado_financiero as
select
  n.id                                                            as negocio_id,
  n.valor_pactado,
  coalesce(p.pagado, 0)                                           as total_pagado,
  coalesce(p.neto, 0)                                             as neto_recibido,
  coalesce(a.ajustes, 0)                                          as ajustes,
  n.valor_pactado + coalesce(a.ajustes,0) - coalesce(p.pagado,0)  as saldo,
  case
    when coalesce(p.pagado,0) = 0 then 'pendiente_anticipo'
    when n.valor_pactado + coalesce(a.ajustes,0) - coalesce(p.pagado,0) <= 0 then 'pagado'
    else 'abono'
  end                                                             as estado_financiero
from negocios n
left join lateral (
  select sum(monto_bruto) as pagado, sum(monto_neto) as neto
  from pagos where negocio_id = n.id and estado = 'confirmado'
) p on true
left join lateral (
  select sum(monto) as ajustes from ajustes_negocio where negocio_id = n.id
) a on true;

