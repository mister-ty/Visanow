-- Correcciones al núcleo — verificadas contra PostgreSQL 16.13 el 17/09/2026.
-- Detalle y evidencia: 03_Diseno/Verificacion_esquema_nucleo_2026-09-17.md
--
-- Los seis defectos no impiden crear las tablas: permiten guardar datos
-- incorrectos en silencio, que es el problema del que VisaNow está huyendo.

-- 1. El signo del ajuste no estaba amarrado al tipo. Un descuento capturado
--    con signo positivo AUMENTABA el saldo ($2.400.000 en vez de $2.000.000).
alter table ajustes_negocio add constraint ck_ajustes_signo check (
  (tipo in ('reembolso','cargo')       and monto > 0) or
  (tipo in ('descuento','condonacion') and monto < 0));

-- 2. Faltaba el estado 'sin_acuerdo' que exige RF-042. Un negocio sin precio
--    pactado reportaba 'pendiente_anticipo' y ensuciaba la cartera.
--    Se corrige además el orden del CASE: un negocio condonado a cero con
--    cero pagos debe quedar 'pagado', no 'pendiente_anticipo'.
-- La definición corregida de la vista está más abajo, en el punto 7:
-- incorpora el estado sin_acuerdo, el orden correcto del CASE y la moneda.

-- 3. En PostgreSQL los NULL son distintos entre sí dentro de un índice único:
--    dos clientes con el mismo documento y tipo_documento nulo entraban los dos.
--    Es el hueco por donde se cuela el riesgo R-08 al migrar, porque en los
--    Excel actuales casi ninguna fila trae el tipo de documento.
drop index if exists ux_clientes_documento;
create unique index ux_clientes_documento on clientes
  (coalesce(tipo_documento,'?'), numero_documento) where numero_documento is not null;

-- 4. Un solicitante sin grupo y sin cliente es un caso que no pertenece a nadie.
--    Con D-02 cerrada (un caso por solicitante) esto no puede quedar abierto.
alter table solicitantes add constraint ck_solicitante_vinculado
  check (grupo_id is not null or cliente_id is not null);

-- 5. monto_neto es una columna generada sin restricción: un pago de $100.000
--    con costo de medio de $150.000 producía un neto de -$50.000 que entraba
--    directo al «neto recibido» y descuadraba la caja.
alter table pagos add constraint ck_pagos_montos
  check (monto_bruto > 0 and costo_medio >= 0 and costo_medio <= monto_bruto);

-- 6. Un valor pactado negativo invierte el signo del saldo y contamina el
--    total vendido del periodo. Solo se bloquea el signo, no el monto: hay
--    ventas con extras por encima del valor de lista.
alter table negocios add constraint ck_negocios_valores
  check (valor_lista >= 0 and descuento >= 0 and valor_pactado >= 0);

-- 7. La vista sumaba pagos sin comparar la moneda del pago contra la del
--    negocio: un pago capturado en USD se sumaba como si fueran pesos.
--    Se expone la moneda del negocio y se restringe la suma a esa moneda.
create or replace view v_estado_financiero as
select
  n.id                                                           as negocio_id,
  n.valor_pactado,
  coalesce(p.pagado, 0)                                          as total_pagado,
  coalesce(p.neto, 0)                                            as neto_recibido,
  coalesce(a.ajustes, 0)                                         as ajustes,
  n.valor_pactado + coalesce(a.ajustes,0) - coalesce(p.pagado,0) as saldo,
  case
    when n.valor_pactado is null or n.valor_pactado = 0                then 'sin_acuerdo'
    when n.valor_pactado + coalesce(a.ajustes,0)
         - coalesce(p.pagado,0) <= 0                                   then 'pagado'
    when coalesce(p.pagado,0) = 0                                      then 'pendiente_anticipo'
    else                                                                    'abono'
  end                                                            as estado_financiero,
  n.moneda
from negocios n
left join lateral (
  select sum(monto_bruto) as pagado, sum(monto_neto) as neto
  from pagos
  where negocio_id = n.id and estado = 'confirmado' and moneda = n.moneda
) p on true
left join lateral (
  select sum(monto) as ajustes from ajustes_negocio where negocio_id = n.id
) a on true;

-- Cartera (RF-046): saldos por vencer, vencidos y antigüedad.
-- Depende del plan de cuotas de 002_brechas.sql y de la moneda que expone
-- la vista corregida de arriba.
create view v_cartera as
with exigible as (
  select negocio_id, sum(monto) as exigible_hoy, min(fecha_pactada) as mas_antigua
  from cuotas_negocio where fecha_pactada <= current_date group by negocio_id
)
select f.negocio_id, f.moneda, f.valor_pactado, f.total_pagado, f.saldo,
       coalesce(e.exigible_hoy,0) as exigible_hoy,
       greatest(coalesce(e.exigible_hoy,0) - f.total_pagado, 0) as vencido,
       greatest(f.saldo - greatest(coalesce(e.exigible_hoy,0) - f.total_pagado, 0), 0) as por_vencer,
       case when coalesce(e.exigible_hoy,0) - f.total_pagado > 0
            then current_date - e.mas_antigua else 0 end as dias_mora
from v_estado_financiero f
left join exigible e on e.negocio_id = f.negocio_id;
