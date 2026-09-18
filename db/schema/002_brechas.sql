-- ===== Permisos por rol. Solo existe `roles` con un código; no hay forma de expresar qué puede hacer cada rol. El criterio de aceptación 9 («un usuario de operaciones no puede editar reglas de comisión ni valores conciliados») no es verificable, y con sqladmin exponiendo todas las tablas, un control de acceso por rol a nivel de módulo es obligatorio desde el primer endpoint.
-- RF: RF-025 (PDF), RNF-03, criterio de aceptación 9  bloquea_ahora=True
create table permisos (
  id     smallserial primary key,
  codigo varchar(60) unique not null,     -- 'comisiones.editar', 'pagos.crear', 'clientes.exportar'
  nombre varchar(120) not null,
  modulo varchar(30) not null
);

create table roles_permisos (
  rol_id     smallint not null references roles(id) on delete cascade,
  permiso_id smallint not null references permisos(id) on delete cascade,
  primary key (rol_id, permiso_id)
);

-- alcance por asignación (RNF-03: «y, cuando aplique, por casos asignados»)
alter table usuarios add column alcance varchar(15) not null default 'todos'
  check (alcance in ('todos','asignados','propios'));

-- ===== Cronología de actividades. No hay ninguna tabla donde registrar una nota, una llamada, un WhatsApp o un correo. La ficha 360° (RF-005) exige «tareas, alertas, documentos y cronología», el seguimiento comercial (RF-012) exige «llamadas, mensajes, notas y fecha de último contacto», y RF-064 pide la cronología completa. `casos_historial` solo guarda cambios de campo, no interacciones. Si esta tabla se añade tarde, hay que volver a pasar por cada servicio ya escrito a insertar la escritura.
-- RF: RF-005, RF-012, RF-064  bloquea_ahora=True
create table actividades (
  id           bigserial primary key,
  entidad      varchar(20) not null check (entidad in
               ('cliente','solicitante','grupo','oportunidad','negocio','caso','pago')),
  entidad_id   bigint not null,
  tipo         varchar(20) not null check (tipo in
               ('nota','llamada','whatsapp','correo','reunion','sistema','cambio_estado')),
  direccion    varchar(10) check (direccion in ('entrante','saliente')),
  asunto       varchar(200),
  cuerpo       text,
  usuario_id   bigint references usuarios(id),
  ocurrido_en  timestamptz not null default now(),
  creado_en    timestamptz not null default now()
);
create index ix_actividades_entidad on actividades (entidad, entidad_id, ocurrido_en desc);
create index ix_actividades_usuario on actividades (usuario_id, ocurrido_en desc);

alter table oportunidades add column ultimo_contacto_en timestamptz;
alter table clientes      add column ultimo_contacto_en timestamptz;

-- ===== Checklists de documentos y su cumplimiento por caso. `transiciones_operativas.requiere_checklist` ya existe y apunta a un concepto que no tiene tabla: es una columna colgando en el vacío. Sin esto, RF-025 no existe y RF-023 («transiciones con checklist») no se puede validar. Como la tabla de transiciones se siembra en la primera migración, la referencia hay que resolverla ahí mismo.
-- RF: RF-023, RF-025, RN-05  bloquea_ahora=True
create table checklists (
  id           serial primary key,
  codigo       varchar(40) unique not null,
  nombre       varchar(120) not null,
  pais_id      smallint references paises(id),
  tipo_visa_id int      references tipos_visa(id),
  modalidad_id smallint references modalidades(id),
  estado_id    smallint references estados_operativos(id),   -- estado en que se exige
  activo       boolean not null default true
);

create table checklist_items (
  id           serial primary key,
  checklist_id int not null references checklists(id) on delete cascade,
  codigo       varchar(40) not null,
  nombre       varchar(160) not null,
  obligatorio  boolean not null default true,
  orden        smallint not null default 0,
  unique (checklist_id, codigo)
);

create table casos_checklist (
  id           bigserial primary key,
  caso_id      bigint not null references casos(id) on delete cascade,
  item_id      int    not null references checklist_items(id),
  cumplido     boolean not null default false,
  cumplido_en  timestamptz,
  cumplido_por bigint references usuarios(id),
  observacion  text,
  unique (caso_id, item_id)
);
create index ix_casos_checklist_caso on casos_checklist (caso_id) where not cumplido;

-- ===== Tareas. No existe la entidad, pese a que RN-04 exige que todo caso activo tenga «próxima acción o tarea» y a que las 13 alertas de la sección 7 terminan todas en una acción con responsable y vencimiento. Va junto con las columnas de próxima acción que se agregan a `casos` (ver errores).
-- RF: RF-060, RN-04, criterio de aceptación 6  bloquea_ahora=True
create table tareas (
  id             bigserial primary key,
  titulo         varchar(200) not null,
  descripcion    text,
  caso_id        bigint references casos(id),
  negocio_id     bigint references negocios(id),
  oportunidad_id bigint references oportunidades(id),
  cliente_id     bigint references clientes(id),
  responsable_id bigint not null references usuarios(id),
  prioridad      varchar(10) not null default 'media' check (prioridad in ('baja','media','alta')),
  estado         varchar(15) not null default 'pendiente'
                 check (estado in ('pendiente','en_curso','hecha','cancelada')),
  vence_en       timestamptz,
  origen         varchar(10) not null default 'manual' check (origen in ('manual','automatica')),
  cerrada_en     timestamptz,
  creado_por     bigint references usuarios(id),
  creado_en      timestamptz not null default now(),
  constraint ck_tareas_vinculo check (
    num_nonnulls(caso_id, negocio_id, oportunidad_id, cliente_id) >= 1)
);
create index ix_tareas_bandeja on tareas (responsable_id, estado, vence_en);
create index ix_tareas_caso    on tareas (caso_id) where caso_id is not null;

-- ===== Trazabilidad de la migración. La actividad 6.2 exige «conservando archivo de origen, fila y fecha de importación para trazabilidad», y ninguna tabla del núcleo tiene dónde guardarlo. Con tres libros, 26 hojas y duplicados heredados (R-08), sin esto el reporte de excepciones de la actividad 6.3 no se puede construir: no hay manera de volver de un registro sospechoso a la celda que lo originó. Agregarlo después obliga a rellenar hacia atrás lo ya migrado, que es justo cuando ya no se sabe de dónde vino.
-- RF: Actividades 6.1–6.3, RNF-09, R-01 y R-08  bloquea_ahora=True
alter table clientes     add column origen_archivo varchar(80), add column origen_hoja varchar(40),
                         add column origen_fila int, add column migrado_en timestamptz;
alter table solicitantes add column origen_archivo varchar(80), add column origen_hoja varchar(40),
                         add column origen_fila int, add column migrado_en timestamptz;
alter table negocios     add column origen_archivo varchar(80), add column origen_hoja varchar(40),
                         add column origen_fila int, add column migrado_en timestamptz;
alter table casos        add column origen_archivo varchar(80), add column origen_hoja varchar(40),
                         add column origen_fila int, add column migrado_en timestamptz;
alter table pagos        add column origen_archivo varchar(80), add column origen_hoja varchar(40),
                         add column origen_fila int, add column migrado_en timestamptz;

create index ix_clientes_migrado on clientes (origen_archivo, origen_hoja, origen_fila)
  where origen_archivo is not null;

-- ===== Plan de pagos / fechas pactadas. RF-040 exige «fechas pactadas de pago» y no hay dónde guardarlas: `negocios` solo tiene el valor. Sin ellas, RF-046 (cartera por vencer, vencida y antigüedad) es imposible, las alertas «saldo próximo a vencer» y «saldo vencido día 1, 7 y 15» no tienen contra qué comparar, y los criterios de aceptación 5 y 7 no se pueden cumplir. Hoy hay 51 negocios con saldo abierto en la hoja PAGOS que hay que migrar con su fecha comprometida.
-- RF: RF-040, RF-046, criterios de aceptación 5 y 7  bloquea_ahora=False
create table cuotas_negocio (
  id            bigserial primary key,
  negocio_id    bigint not null references negocios(id) on delete cascade,
  numero        smallint not null,
  concepto      varchar(60) not null default 'abono',
  monto         numeric(14,2) not null check (monto > 0),
  fecha_pactada date not null,
  creado_en     timestamptz not null default now(),
  unique (negocio_id, numero)
);
create index ix_cuotas_fecha on cuotas_negocio (fecha_pactada);

-- v_cartera se crea en 003_correcciones.sql: depende de que v_estado_financiero
-- exponga la moneda del negocio, que es una de las correcciones.


-- ===== Gastos. `categorias_gasto` está creada y no la usa nadie: es un catálogo sin tabla de hechos. RF-053 pide gastos generales y directos por caso o negocio, con proveedor, categoría, fecha, moneda, estado y comprobante, y hay 131 filas reales entre las hojas GASTOS y GASTOS 2026 esperando migración (con la categoría hoy escrita como nombre de persona: MIRIAM/miriam, YAS/yas, META, MARIO-DISEÑOS).
-- RF: RF-053, RF-054  bloquea_ahora=False
create table proveedores (
  id        serial primary key,
  nombre    varchar(120) not null,
  documento varchar(40),
  activo    boolean not null default true,
  creado_en timestamptz not null default now()
);
create unique index ux_proveedores_nombre on proveedores (upper(trim(nombre)));

create table gastos (
  id              bigserial primary key,
  categoria_id    smallint not null references categorias_gasto(id),
  proveedor_id    int      references proveedores(id),
  negocio_id      bigint   references negocios(id),
  caso_id         bigint   references casos(id),
  concepto        varchar(200) not null,
  fecha           date not null,
  monto           numeric(14,2) not null check (monto > 0),
  moneda          char(3) not null default 'COP',
  estado          varchar(15) not null default 'pagado'
                  check (estado in ('pagado','pendiente','anulado')),
  medio_pago_id   smallint references medios_pago(id),
  banco_cuenta_id smallint references bancos_cuentas(id),
  comprobante_url text,
  observacion     text,
  registrado_por  bigint references usuarios(id),
  creado_en       timestamptz not null default now()
);
create index ix_gastos_fecha    on gastos (fecha);
create index ix_gastos_negocio  on gastos (negocio_id) where negocio_id is not null;
create index ix_gastos_caso     on gastos (caso_id)    where caso_id is not null;
create index ix_gastos_categoria on gastos (categoria_id, fecha);

-- ===== Comisiones y sus reglas. RN-07 («la comisión conserva la regla aplicada al momento de la venta») es una de las diez reglas innegociables y no tiene ni una tabla donde vivir. RF-050 sobrevive al corte como registro de reglas; RF-051 y RF-052 van a MVP 2 por D-08, pero la tabla `comisiones` con el `jsonb` congelado hay que dejarla desde ya, porque es lo que hace que la regla sea reconstruible después.
-- RF: RF-050, RN-07, criterio de aceptación 8  bloquea_ahora=False
create table comisiones_reglas (
  id            serial primary key,
  nombre        varchar(120) not null,
  vendedor_id   bigint references usuarios(id),
  servicio_id   int    references servicios(id),
  base          varchar(20) not null check (base in ('vendido','cobrado','neto_recibido')),
  porcentaje    numeric(6,3) check (porcentaje >= 0 and porcentaje <= 100),
  monto_fijo    numeric(14,2) check (monto_fijo >= 0),
  meta_cantidad smallint,
  vigente_desde date not null,
  vigente_hasta date,
  definicion    jsonb not null default '{}'::jsonb,
  activo        boolean not null default true,
  creado_en     timestamptz not null default now(),
  constraint ck_reglas_valor    check (porcentaje is not null or monto_fijo is not null),
  constraint ck_reglas_vigencia check (vigente_hasta is null or vigente_hasta >= vigente_desde)
);

create table comisiones (
  id             bigserial primary key,
  negocio_id     bigint not null references negocios(id),
  vendedor_id    bigint not null references usuarios(id),
  regla_id       int references comisiones_reglas(id),
  regla_aplicada jsonb  not null,          -- RN-07: copia congelada, no una FK
  base_calculo   numeric(14,2) not null,
  monto          numeric(14,2) not null,
  estado         varchar(15) not null default 'provisional'
                 check (estado in ('provisional','causada','liquidada','anulada')),
  periodo        date,
  creado_en      timestamptz not null default now(),
  unique (negocio_id, vendedor_id, regla_id)
);
create index ix_comisiones_vendedor on comisiones (vendedor_id, periodo, estado);

-- ===== Centro de alertas y su configuración. RF-061 y RF-062 piden 13 alertas con anticipación, destinatario y canal configurables, y estados vista/resuelta/pospuesta. No hay ninguna tabla. Detalle que decide el diseño: sin una clave de deduplicación, el job horario vuelve a crear las mismas alertas cada hora y el centro de alertas queda inservible en el primer día de uso.
-- RF: RF-061, RF-062, criterios de aceptación 6 y 7  bloquea_ahora=False
create table alertas_tipos (
  id                  smallserial primary key,
  codigo              varchar(40) unique not null,
  nombre              varchar(120) not null,
  entidad             varchar(20) not null check (entidad in
                      ('oportunidad','caso','negocio','cita','importacion')),
  anticipacion_valor  int not null default 0,
  anticipacion_unidad varchar(12) not null default 'dias'
                      check (anticipacion_unidad in ('horas','dias','dias_habiles')),
  repeticiones        jsonb not null default '[]'::jsonb,   -- p. ej. [1,7,15]
  destinatario_rol_id smallint references roles(id),
  canal               varchar(15) not null default 'interna'
                      check (canal in ('interna','correo','whatsapp')),
  severidad           varchar(10) not null default 'media'
                      check (severidad in ('baja','media','alta')),
  activo              boolean not null default true
);

create table alertas (
  id              bigserial primary key,
  tipo_id         smallint not null references alertas_tipos(id),
  caso_id         bigint references casos(id),
  negocio_id      bigint references negocios(id),
  oportunidad_id  bigint references oportunidades(id),
  cita_id         bigint references citas(id),
  tarea_id        bigint references tareas(id),
  destinatario_id bigint references usuarios(id),
  clave_dedupe    varchar(120) not null,
  mensaje         text not null,
  estado          varchar(15) not null default 'nueva'
                  check (estado in ('nueva','vista','resuelta','pospuesta')),
  vence_en        timestamptz,
  pospuesta_hasta timestamptz,
  generada_en     timestamptz not null default now(),
  resuelta_en     timestamptz,
  resuelta_por    bigint references usuarios(id)
);
create unique index ux_alertas_dedupe on alertas (tipo_id, clave_dedupe)
  where estado in ('nueva','vista','pospuesta');
create index ix_alertas_bandeja on alertas (destinatario_id, estado, generada_en desc);

-- ===== Importaciones del SaaS y su bitácora. RF-033 exige previsualizar «nuevos, actualizados, sin cambios, conflictos y rechazados» ANTES de aplicar la carga, y RF-035 exige registro de última sincronización, errores y reintentos. Con el esquema actual eso es imposible: no hay dónde dejar las filas leídas mientras el usuario decide, así que el único camino sería escribir directo en `casos` y deshacer después. El criterio de aceptación 2 (importar dos veces sin duplicar) tampoco es demostrable sin esta bitácora.
-- RF: RF-031, RF-032, RF-033, RF-035, criterio de aceptación 2  bloquea_ahora=False
create table importaciones (
  id             bigserial primary key,
  origen         varchar(20) not null default 'saas',
  archivo_nombre varchar(200) not null,
  archivo_sha256 char(64) not null,
  filas_totales  int not null default 0,
  nuevos         int not null default 0,
  actualizados   int not null default 0,
  sin_cambios    int not null default 0,
  conflictos     int not null default 0,
  rechazados     int not null default 0,
  estado         varchar(15) not null default 'previsualizada'
                 check (estado in ('previsualizada','aplicada','descartada','fallida')),
  mensaje_error  text,
  ejecutada_por  bigint references usuarios(id),
  iniciada_en    timestamptz not null default now(),
  aplicada_en    timestamptz
);
create index ix_importaciones_sha on importaciones (archivo_sha256);

create table importaciones_filas (
  id             bigserial primary key,
  importacion_id bigint not null references importaciones(id) on delete cascade,
  fila_numero    int not null,
  id_externo     varchar(60),
  datos          jsonb not null,
  resultado      varchar(15) not null check (resultado in
                 ('nuevo','actualizado','sin_cambio','conflicto','rechazado')),
  caso_id        bigint references casos(id),
  detalle        text,
  unique (importacion_id, fila_numero)
);
create index ix_importaciones_filas_idext on importaciones_filas (id_externo);

create table sincronizaciones (
  id          bigserial primary key,
  origen      varchar(20) not null,
  resultado   varchar(10) not null check (resultado in ('ok','error')),
  detalle     text,
  intentos    smallint not null default 1,
  ocurrido_en timestamptz not null default now()
);

-- ===== Propiedad de datos por campo y registro de conflictos. RF-034 y RN-09 son la regla que impide que el SaaS pise lo que VisaNow gobierna, y no hay ni la política ni el lugar donde dejar constancia del conflicto. Sin la tabla de conflictos, «no se resuelve solo: se registra y se muestra» es una frase sin implementación.
-- RF: RF-034, RF-035, RN-09, criterio de aceptación 12  bloquea_ahora=False
create table politica_campos (
  id           smallserial primary key,
  entidad      varchar(20) not null,
  campo        varchar(60) not null,
  propietario  varchar(10) not null check (propietario in ('saas','visanow')),
  al_conflicto varchar(15) not null default 'registrar'
               check (al_conflicto in ('registrar','sobrescribir','ignorar')),
  unique (entidad, campo)
);

insert into politica_campos (entidad, campo, propietario) values
 ('caso','estado_id','saas'), ('caso','ds160_enviado_en','saas'),
 ('caso','ds160_numero','saas'), ('caso','busqueda_citas','saas'),
 ('caso','responsable_id','visanow'), ('caso','proxima_accion','visanow'),
 ('negocio','valor_pactado','visanow'), ('negocio','vendedor_id','visanow');

create table conflictos_sincronizacion (
  id             bigserial primary key,
  importacion_id bigint references importaciones(id),
  caso_id        bigint not null references casos(id),
  campo          varchar(60) not null,
  valor_visanow  text,
  valor_saas     text,
  estado         varchar(18) not null default 'abierto'
                 check (estado in ('abierto','resuelto_visanow','resuelto_saas','ignorado')),
  resuelto_por   bigint references usuarios(id),
  resuelto_en    timestamptz,
  detectado_en   timestamptz not null default now()
);
create index ix_conflictos_abiertos on conflictos_sincronizacion (caso_id) where estado = 'abierto';

-- ===== Campos del SaaS en `casos`. El consolidado trae «Fecha de envio DS-160», «N° DS-160» y «Búsqueda de citas» (valor observado: 'inactive'), y ninguno tiene columna: la importación de RF-031 no tiene dónde escribir tres de sus ocho campos. El n.º DS-160 es además un dato sensible que debe recibir el mismo tratamiento que el pasaporte.
-- RF: RF-031, RF-021, RF-029  bloquea_ahora=False
alter table casos
  add column ds160_enviado_en    date,
  add column ds160_numero_cifrado text,
  add column ds160_hash          bytea,
  add column busqueda_citas      varchar(20),
  add column etapa_saas          varchar(80);     -- etapa cruda del SaaS antes de homologar
create unique index ux_casos_ds160 on casos (ds160_hash) where ds160_hash is not null;
create index ix_casos_etapa_saas on casos (etapa_saas) where etapa_saas is not null;

-- ===== Documentos adjuntos. RF-005 exige documentos en la ficha 360° y RF-064 adjuntos en la cronología. La decisión D-06 (¿en el sistema o enlazados desde Drive?) vence el 18/09 y la tabla se puede diseñar para las dos salidas, de modo que D-06 deje de bloquear.
-- RF: RF-005, RF-064, RNF-04, D-06  bloquea_ahora=False
create table documentos (
  id             bigserial primary key,
  entidad        varchar(20) not null check (entidad in
                 ('cliente','solicitante','caso','negocio','pago','gasto')),
  entidad_id     bigint not null,
  tipo           varchar(40),
  nombre         varchar(200) not null,
  almacenamiento varchar(10) not null default 'enlace'
                 check (almacenamiento in ('enlace','local')),
  url            text,
  ruta           text,
  mime           varchar(80),
  tamano_bytes   bigint,
  sha256         char(64),
  restringido    boolean not null default false,
  subido_por     bigint references usuarios(id),
  creado_en      timestamptz not null default now(),
  constraint ck_documentos_ubicacion check (
    (almacenamiento = 'enlace' and url  is not null) or
    (almacenamiento = 'local'  and ruta is not null))
);
create index ix_documentos_entidad on documentos (entidad, entidad_id);
alter table actividades add column documento_id bigint references documentos(id);

-- ===== Campañas y referidos. `oportunidades.campania varchar(120)` es texto libre, y RF-010 pide «campaña/influencer/referido» como dato estructurado. En los datos reales el canal y la campaña están mezclados en una sola columna MEDIO (INSTAGRAM, PUBLICIDAD, RECOMEN, Influencer, Tiktok) y no hay forma de saber quién refirió a quién, que es precisamente lo que el área comercial quiere medir.
-- RF: RF-010, RF-018 (PDF, conversión por canal)  bloquea_ahora=False
create table campanias (
  id          serial primary key,
  codigo      varchar(40) unique not null,
  nombre      varchar(120) not null,
  canal_id    smallint references canales(id),
  tipo        varchar(20) check (tipo in ('pauta','influencer','referido','organico','otro')),
  responsable varchar(120),
  inicia_en   date,
  termina_en  date,
  presupuesto numeric(14,2),
  activo      boolean not null default true
);

alter table oportunidades
  add column campania_id             int    references campanias(id),
  add column referido_por_cliente_id bigint references clientes(id);
create index ix_oportunidades_campania on oportunidades (campania_id) where campania_id is not null;
-- la columna de texto `campania` se conserva durante la migración y se elimina al cerrar la fase 6.

-- ===== Registro de exportaciones. RNF-07 exige saber «quién exportó, cuándo y qué filtro aplicó», y el criterio de aceptación 11 exige que los filtros del tablero coincidan con el detalle exportado: sin guardar el filtro no hay forma de demostrarlo. La tabla `auditoria` sirve para el quién y el cuándo, pero no tiene dónde dejar el filtro (se corrige agregándole `filtros jsonb`) ni el conteo de filas.
-- RF: RF-023 (PDF), RNF-07, criterio de aceptación 11  bloquea_ahora=False
create table exportaciones (
  id          bigserial primary key,
  usuario_id  bigint not null references usuarios(id),
  recurso     varchar(40) not null,
  formato     varchar(10) not null check (formato in ('xlsx','csv','pdf')),
  filtros     jsonb not null default '{}'::jsonb,
  filas       int not null default 0,
  ip          inet,
  ocurrido_en timestamptz not null default now()
);
create index ix_exportaciones_usuario on exportaciones (usuario_id, ocurrido_en desc);

-- ===== Fusión de duplicados. RF-002 exige «fusión autorizada y trazable» y no hay ni registro de la fusión ni forma de que un enlace viejo al registro absorbido siga resolviendo. Con duplicados heredados como riesgo alto reconocido (R-08) y tres libros con el mismo cliente escrito de formas distintas, la primera fusión mal hecha e irreversible va a costar más que la tabla.
-- RF: RF-002, RN-08, R-08  bloquea_ahora=False
create table fusiones (
  id             bigserial primary key,
  entidad        varchar(20) not null check (entidad in ('cliente','solicitante')),
  id_conservado  bigint not null,
  id_absorbido   bigint not null,
  criterio       varchar(30) not null check (criterio in
                 ('documento','pasaporte','telefono','email','nombre','manual')),
  snapshot       jsonb not null,         -- copia íntegra del registro absorbido
  autorizado_por bigint not null references usuarios(id),
  ocurrido_en    timestamptz not null default now(),
  constraint ck_fusiones_distintos check (id_conservado <> id_absorbido)
);
create index ix_fusiones_absorbido on fusiones (entidad, id_absorbido);

alter table clientes     add column fusionado_en_id bigint references clientes(id);
alter table solicitantes add column fusionado_en_id bigint references solicitantes(id);
create index ix_clientes_fusionados on clientes (fusionado_en_id) where fusionado_en_id is not null;
