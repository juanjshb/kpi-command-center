-- ============================================================================
-- DATOS DE MUESTRA: SUCURSALES, SUBAGENTES, ATMS Y COMPETENCIA
-- ============================================================================
-- PostgreSQL. Inserta exactamente 150 registros por canal:
--   * 150 lecturas ATM en public.atm_readings (25 ATMs x 6 horas);
--   * 150 lecturas de sucursal en public.branch_readings (25 x 6 horas);
--   * 150 transacciones individuales en public.subagent_test_transactions.
--   * 150 saldos en public.branch_financials (25 sucursales x 6 fechas).
-- Además asigna estados operativos de prueba a esos 25 ATMs, incluyendo cuatro
-- alertas de bajo efectivo. El estado original queda respaldado para restaurarlo.
--
-- Los IDs se resuelven dinámicamente desde el inventario actual; no hay UUIDs
-- de sucursales/ATMs/subagentes codificados en el archivo. El batch es
-- idempotente: antes de insertar elimina solamente una ejecución anterior del
-- mismo batch KPI_TEST_TRANSACTIONS_V1.
--
-- branch_readings representa actividad horaria de clientes atendidos porque el
-- modelo actual no almacena transacciones monetarias individuales de sucursal.
-- La tabla subagent_test_transactions es deliberadamente de prueba y el script
-- 04_clear.sql la elimina por completo.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '3min';

SELECT pg_advisory_xact_lock(714005);

-- Registra únicamente el inventario sintético creado por este archivo. Si ya
-- existen al menos 25 entidades por canal, se reutiliza el inventario real y
-- no se crean ubicaciones artificiales.
CREATE TABLE IF NOT EXISTS public.sample_seed_registry (
    batch_tag VARCHAR(80) NOT NULL,
    entity_type VARCHAR(40) NOT NULL,
    entity_id UUID NOT NULL,
    PRIMARY KEY (batch_tag, entity_type, entity_id)
);

-- Catálogo geográfico mínimo para que el seed también funcione sobre un schema
-- recién creado. ON CONFLICT conserva cualquier dato demográfico existente.
INSERT INTO public.provincias (id, nombre, region, fuente)
VALUES
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Distrito Nacional'), 'Distrito Nacional', 'Metropolitana', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Santo Domingo'), 'Santo Domingo', 'Metropolitana', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Santiago'), 'Santiago', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:La Vega'), 'La Vega', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Puerto Plata'), 'Puerto Plata', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Espaillat'), 'Espaillat', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Duarte'), 'Duarte', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Hermanas Mirabal'), 'Hermanas Mirabal', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:María Trinidad Sánchez'), 'María Trinidad Sánchez', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Samaná'), 'Samaná', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Sánchez Ramírez'), 'Sánchez Ramírez', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Monseñor Nouel'), 'Monseñor Nouel', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Valverde'), 'Valverde', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Monte Cristi'), 'Monte Cristi', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Dajabón'), 'Dajabón', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Santiago Rodríguez'), 'Santiago Rodríguez', 'Norte', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:San Cristóbal'), 'San Cristóbal', 'Sur', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Peravia'), 'Peravia', 'Sur', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:San José de Ocoa'), 'San José de Ocoa', 'Sur', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Azua'), 'Azua', 'Sur', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:San Juan'), 'San Juan', 'Sur', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Elías Piña'), 'Elías Piña', 'Sur', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Barahona'), 'Barahona', 'Sur', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Baoruco'), 'Baoruco', 'Sur', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Independencia'), 'Independencia', 'Sur', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Pedernales'), 'Pedernales', 'Sur', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:La Altagracia'), 'La Altagracia', 'Este', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:La Romana'), 'La Romana', 'Este', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:El Seibo'), 'El Seibo', 'Este', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Hato Mayor'), 'Hato Mayor', 'Este', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:San Pedro de Macorís'), 'San Pedro de Macorís', 'Este', 'sql_sample_v1'),
    (public.kpi_uuid('KPI_SAMPLE:PROVINCE:Monte Plata'), 'Monte Plata', 'Este', 'sql_sample_v1')
ON CONFLICT (nombre) DO NOTHING;

-- Completar hasta 25 sucursales solamente cuando el inventario actual no sea
-- suficiente para producir las 150 lecturas solicitadas.
WITH
needed AS (
    SELECT greatest(0, 25 - count(*))::INTEGER AS amount
    FROM public.sucursales
),
available AS (
    SELECT seq
    FROM generate_series(1, 100) AS seq
    WHERE NOT EXISTS (
        SELECT 1 FROM public.sucursales
        WHERE codigo = 'SAMPLE-BR-' || lpad(seq::text, 3, '0')
    )
    ORDER BY seq
    LIMIT (SELECT amount FROM needed)
),
inserted AS (
    INSERT INTO public.sucursales (
        id, codigo, nombre, provincia, municipio, direccion, latitud, longitud,
        estado, total_cajeros_humanos, sla_objetivo_segundos, fuente, fuente_id
    )
    SELECT
        public.kpi_uuid('KPI_SAMPLE:BRANCH:' || seq),
        'SAMPLE-BR-' || lpad(seq::text, 3, '0'),
        'Sucursal de muestra ' || seq,
        (ARRAY['Distrito Nacional', 'Santo Domingo', 'Santiago', 'La Vega', 'La Altagracia'])[1 + ((seq - 1) % 5)],
        (ARRAY['Santo Domingo', 'Santo Domingo Este', 'Santiago', 'La Vega', 'Higüey'])[1 + ((seq - 1) % 5)],
        'Ubicación sintética generada por 03_sample_data.sql',
        18.45 + ((seq % 20) * 0.035),
        -70.75 + ((seq % 20) * 0.055),
        'OPERATIVA'::public.branch_status,
        4 + (seq % 5),
        600,
        'sql_sample_v1',
        'branch-' || seq
    FROM available
    RETURNING id
)
INSERT INTO public.sample_seed_registry (batch_tag, entity_type, entity_id)
SELECT 'KPI_TEST_TRANSACTIONS_V1', 'sucursal', id FROM inserted
ON CONFLICT DO NOTHING;

-- Completar hasta 25 ATMs.
WITH
needed AS (
    SELECT greatest(0, 25 - count(*))::INTEGER AS amount
    FROM public.atms
),
available AS (
    SELECT seq
    FROM generate_series(1, 100) AS seq
    WHERE NOT EXISTS (
        SELECT 1 FROM public.atms
        WHERE codigo_unico = 'SAMPLE-ATM-' || lpad(seq::text, 3, '0')
    )
    ORDER BY seq
    LIMIT (SELECT amount FROM needed)
),
inserted AS (
    INSERT INTO public.atms (
        id, codigo_unico, nombre, provincia, municipio, direccion, tipo,
        nivel_efectivo_pct, capacidad_efectivo, estado, latitud, longitud,
        fuente, fuente_id
    )
    SELECT
        public.kpi_uuid('KPI_SAMPLE:ATM:' || seq),
        'SAMPLE-ATM-' || lpad(seq::text, 3, '0'),
        'ATM de muestra ' || seq,
        (ARRAY['Distrito Nacional', 'Santo Domingo', 'Santiago', 'La Vega', 'La Altagracia'])[1 + ((seq - 1) % 5)],
        (ARRAY['Santo Domingo', 'Santo Domingo Este', 'Santiago', 'La Vega', 'Higüey'])[1 + ((seq - 1) % 5)],
        'Ubicación sintética generada por 03_sample_data.sql',
        CASE WHEN seq % 4 = 0 THEN 'CDM_DEPOSITO' ELSE 'DISPENSADOR' END::public.atm_type,
        0,
        1000000,
        'SIN_DATOS'::public.atm_status,
        18.46 + ((seq % 20) * 0.035),
        -70.74 + ((seq % 20) * 0.055),
        'sql_sample_v1',
        'atm-' || seq
    FROM available
    RETURNING id
)
INSERT INTO public.sample_seed_registry (batch_tag, entity_type, entity_id)
SELECT 'KPI_TEST_TRANSACTIONS_V1', 'atm', id FROM inserted
ON CONFLICT DO NOTHING;

-- Completar hasta 25 subagentes activos.
WITH
needed AS (
    SELECT greatest(0, 25 - count(*))::INTEGER AS amount
    FROM public.subagentes
    WHERE activo IS TRUE
),
available AS (
    SELECT seq
    FROM generate_series(1, 100) AS seq
    WHERE NOT EXISTS (
        SELECT 1 FROM public.subagentes
        WHERE codigo_unico = 'SAMPLE-SA-' || lpad(seq::text, 3, '0')
    )
    ORDER BY seq
    LIMIT (SELECT amount FROM needed)
),
inserted AS (
    INSERT INTO public.subagentes (
        id, codigo_unico, nombre, provincia, municipio, direccion, latitud,
        longitud, fuente, fuente_id, activo
    )
    SELECT
        public.kpi_uuid('KPI_SAMPLE:SUBAGENT:' || seq),
        'SAMPLE-SA-' || lpad(seq::text, 3, '0'),
        'Subagente de muestra ' || seq,
        (ARRAY['Distrito Nacional', 'Santo Domingo', 'Santiago', 'La Vega', 'La Altagracia'])[1 + ((seq - 1) % 5)],
        (ARRAY['Santo Domingo', 'Santo Domingo Este', 'Santiago', 'La Vega', 'Higüey'])[1 + ((seq - 1) % 5)],
        'Ubicación sintética generada por 03_sample_data.sql',
        18.47 + ((seq % 20) * 0.035),
        -70.73 + ((seq % 20) * 0.055),
        'sql_sample_v1',
        'subagent-' || seq,
        true
    FROM available
    RETURNING id
)
INSERT INTO public.sample_seed_registry (batch_tag, entity_type, entity_id)
SELECT 'KPI_TEST_TRANSACTIONS_V1', 'subagente', id FROM inserted
ON CONFLICT DO NOTHING;

-- Instituciones y sucursales competidoras para Geospatial Analytics. Nunca se
-- inventan depósitos del competidor; la cuota de mercado se calcula por locales.
INSERT INTO public.institutions (id, nombre, es_propia, color)
SELECT public.kpi_uuid('KPI_SAMPLE:INSTITUTION:BHD Leon'), 'BHD Leon', true, '#35C83E'
WHERE NOT EXISTS (SELECT 1 FROM public.institutions WHERE es_propia IS TRUE)
ON CONFLICT (nombre) DO UPDATE
SET es_propia = true, color = EXCLUDED.color;

INSERT INTO public.institutions (id, nombre, es_propia, color)
VALUES (
    public.kpi_uuid('KPI_SAMPLE:INSTITUTION:Scotiabank'),
    'Scotiabank',
    false,
    '#EC111A'
)
ON CONFLICT (nombre) DO UPDATE
SET color = EXCLUDED.color;

WITH institution AS (
    SELECT id FROM public.institutions WHERE nombre = 'Scotiabank'
),
inserted AS (
    INSERT INTO public.competitor_locations (
        id, institucion_id, codigo, nombre, provincia, tipo, latitud, longitud,
        fuente, fecha_verificacion
    )
    SELECT
        public.kpi_uuid('KPI_SAMPLE:COMPETITOR_BRANCH:' || seq),
        institution.id,
        'SAMPLE-SCOTIA-BR-' || lpad(seq::text, 3, '0'),
        'Scotiabank muestra ' || seq,
        (ARRAY['Distrito Nacional', 'Santo Domingo', 'Santiago', 'La Vega', 'La Altagracia'])[1 + ((seq - 1) % 5)],
        'SUCURSAL'::public.location_type,
        18.48 + ((seq % 12) * 0.045),
        -70.72 + ((seq % 12) * 0.060),
        'sql_sample_v1',
        current_date
    FROM institution
    CROSS JOIN generate_series(1, 12) AS seq
    ON CONFLICT (institucion_id, codigo) DO NOTHING
    RETURNING id
)
INSERT INTO public.sample_seed_registry (batch_tag, entity_type, entity_id)
SELECT 'KPI_TEST_TRANSACTIONS_V1', 'competitor_location', id FROM inserted
ON CONFLICT DO NOTHING;

WITH inserted AS (
    INSERT INTO public.candidate_locations (
        id, codigo, nombre, provincia, municipio, tipo, latitud, longitud,
        potencial_mercado, densidad_poblacional, estado, fuente, notas
    )
    SELECT
        public.kpi_uuid('KPI_SAMPLE:CANDIDATE:' || seq),
        'SAMPLE-CAND-' || lpad(seq::text, 3, '0'),
        'Ubicación candidata de muestra ' || seq,
        (ARRAY['Distrito Nacional', 'Santo Domingo', 'Santiago', 'La Vega', 'La Altagracia'])[1 + ((seq - 1) % 5)],
        (ARRAY['Santo Domingo', 'Santo Domingo Este', 'Santiago', 'La Vega', 'Higüey'])[1 + ((seq - 1) % 5)],
        CASE WHEN seq % 3 = 0 THEN 'ATM' ELSE 'SUCURSAL' END::public.location_type,
        18.49 + ((seq % 10) * 0.050),
        -70.70 + ((seq % 10) * 0.065),
        55 + seq * 3,
        500 + seq * 45,
        'PROPUESTA'::public.candidate_status,
        'sql_sample_v1',
        'Dato sintético, sin relación con operaciones reales'
    FROM generate_series(1, 10) AS seq
    ON CONFLICT (codigo) DO NOTHING
    RETURNING id
)
INSERT INTO public.sample_seed_registry (batch_tag, entity_type, entity_id)
SELECT 'KPI_TEST_TRANSACTIONS_V1', 'candidate_location', id FROM inserted
ON CONFLICT DO NOTHING;

-- La aplicación aún no tiene un modelo transaccional para subagentes. Esta
-- tabla aislada permite probar el dominio sin modificar tablas productivas.
CREATE TABLE IF NOT EXISTS public.subagent_test_transactions (
    id UUID PRIMARY KEY,
    subagente_id UUID NOT NULL
        REFERENCES public.subagentes(id) ON DELETE RESTRICT,
    ocurrida_en TIMESTAMPTZ NOT NULL,
    tipo VARCHAR(30) NOT NULL,
    estado VARCHAR(20) NOT NULL,
    monto NUMERIC(18, 2) NOT NULL,
    comision NUMERIC(18, 2) NOT NULL DEFAULT 0,
    referencia VARCHAR(80) NOT NULL UNIQUE,
    batch_tag VARCHAR(80) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_subagent_test_transactions_type
        CHECK (tipo IN ('RETIRO', 'DEPOSITO', 'PAGO_SERVICIO', 'TRANSFERENCIA')),
    CONSTRAINT ck_subagent_test_transactions_status
        CHECK (estado IN ('APROBADA', 'RECHAZADA', 'REVERSADA')),
    CONSTRAINT ck_subagent_test_transactions_amounts
        CHECK (monto > 0 AND comision >= 0)
);

CREATE INDEX IF NOT EXISTS ix_subagent_test_transactions_subagente_id
    ON public.subagent_test_transactions (subagente_id);

CREATE INDEX IF NOT EXISTS ix_subagent_test_transactions_ocurrida_en
    ON public.subagent_test_transactions (ocurrida_en);

CREATE INDEX IF NOT EXISTS ix_subagent_test_transactions_batch_tag
    ON public.subagent_test_transactions (batch_tag);

-- Respaldo aislado de los campos maestros de ATM que este seed modifica. Si el
-- seed se vuelve a ejecutar, primero restaura el estado previo y crea un respaldo
-- limpio para que 04_clear.sql siempre pueda revertirlo.
CREATE TABLE IF NOT EXISTS public.atm_test_state_backup (
    batch_tag VARCHAR(80) NOT NULL,
    atm_id UUID NOT NULL,
    nivel_efectivo_pct FLOAT NOT NULL,
    estado VARCHAR(40) NOT NULL,
    ultima_comunicacion TIMESTAMPTZ,
    PRIMARY KEY (batch_tag, atm_id)
);

UPDATE public.atms atm
SET
    nivel_efectivo_pct = backup.nivel_efectivo_pct,
    estado = backup.estado::public.atm_status,
    ultima_comunicacion = backup.ultima_comunicacion
FROM public.atm_test_state_backup backup
WHERE backup.batch_tag = 'KPI_TEST_TRANSACTIONS_V1'
  AND backup.atm_id = atm.id;

DELETE FROM public.atm_test_state_backup
WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1';

-- Se requieren al menos 25 entidades por canal para obtener 150 filas sin
-- concentrar toda la actividad en unas pocas ubicaciones.
DO $validation$
DECLARE
    v_branches  BIGINT;
    v_atms      BIGINT;
    v_subagents BIGINT;
BEGIN
    SELECT count(*) INTO v_branches FROM public.sucursales;
    SELECT count(*) INTO v_atms FROM public.atms;
    SELECT count(*) INTO v_subagents FROM public.subagentes WHERE activo IS TRUE;

    IF v_branches < 25 OR v_atms < 25 OR v_subagents < 25 THEN
        RAISE EXCEPTION
            'Inventario insuficiente. Requerido: 25 por canal. Sucursales=%, ATMs=%, subagentes activos=%',
            v_branches, v_atms, v_subagents;
    END IF;
END
$validation$;

-- Limpiar exclusivamente una ejecución anterior de este mismo batch.
DELETE FROM public.atm_readings reading
WHERE reading.id IN (
    SELECT md5(
        'KPI_TEST_TRANSACTIONS_V1:ATM:' || atm.id::text || ':' || slot::text
    )::UUID
    FROM public.atms atm
    CROSS JOIN generate_series(1, 6) AS slot
);

DELETE FROM public.branch_readings reading
WHERE reading.id IN (
    SELECT md5(
        'KPI_TEST_TRANSACTIONS_V1:BRANCH:' || branch.id::text || ':' || slot::text
    )::UUID
    FROM public.sucursales branch
    CROSS JOIN generate_series(1, 6) AS slot
);

DELETE FROM public.branch_financials financial
WHERE financial.id IN (
    SELECT md5(
        'KPI_TEST_TRANSACTIONS_V1:FINANCIAL:' || branch.id::text || ':' || slot::text
    )::UUID
    FROM public.sucursales branch
    CROSS JOIN generate_series(1, 6) AS slot
);

DELETE FROM public.subagent_test_transactions
WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1';

-- Guardar el estado real antes de simular telemetría en los 25 ATMs usados.
WITH selected AS (
    SELECT chosen.id
    FROM (
        SELECT id, codigo_unico
        FROM public.atms
        ORDER BY
            (fuente = 'bhd_public_locations_api') DESC,
            codigo_unico,
            id
        LIMIT 25
    ) chosen
)
INSERT INTO public.atm_test_state_backup (
    batch_tag,
    atm_id,
    nivel_efectivo_pct,
    estado,
    ultima_comunicacion
)
SELECT
    'KPI_TEST_TRANSACTIONS_V1',
    atm.id,
    atm.nivel_efectivo_pct,
    atm.estado::text,
    atm.ultima_comunicacion
FROM public.atms atm
JOIN selected ON selected.id = atm.id;

-- Distribución controlada: 17 operativos, 4 con bajo efectivo, 2 fuera de
-- servicio y 2 en mantenimiento. Las cuatro filas BAJO_EFECTIVO alimentan el
-- indicador "Low cash alerts" porque sus niveles están por debajo de 20%.
WITH selected AS (
    SELECT
        chosen.id,
        row_number() OVER (ORDER BY chosen.codigo_unico, chosen.id)::INTEGER AS rn
    FROM (
        SELECT id, codigo_unico
        FROM public.atms
        ORDER BY
            (fuente = 'bhd_public_locations_api') DESC,
            codigo_unico,
            id
        LIMIT 25
    ) chosen
)
UPDATE public.atms atm
SET
    estado = (
        CASE
            WHEN selected.rn <= 17 THEN 'OPERATIVO'
            WHEN selected.rn <= 21 THEN 'BAJO_EFECTIVO'
            WHEN selected.rn <= 23 THEN 'FUERA_DE_SERVICIO'
            ELSE 'MANTENIMIENTO'
        END
    )::public.atm_status,
    nivel_efectivo_pct = CASE
        WHEN selected.rn <= 17 THEN 65 + ((selected.rn + 1) % 25)
        WHEN selected.rn <= 21 THEN 9 + ((selected.rn - 18) * 2)
        WHEN selected.rn <= 23 THEN 35 + ((selected.rn - 22) * 5)
        ELSE 55 + ((selected.rn - 24) * 5)
    END,
    ultima_comunicacion = CASE
        WHEN selected.rn <= 21 THEN now() - interval '2 minutes'
        ELSE now() - interval '30 minutes'
    END
FROM selected
WHERE atm.id = selected.id;

-- --------------------------------------------------------------------------
-- 1. ATM: 25 equipos x 6 horas = 150 lecturas
-- --------------------------------------------------------------------------
WITH
params AS (
    SELECT date_trunc('hour', now()) - interval '1 hour' AS base_hour
),
selected AS (
    SELECT
        chosen.id,
        row_number() OVER (ORDER BY chosen.codigo_unico, chosen.id)::INTEGER AS rn
    FROM (
        SELECT id, codigo_unico
        FROM public.atms
        ORDER BY
            (fuente = 'bhd_public_locations_api') DESC,
            codigo_unico,
            id
        LIMIT 25
    ) chosen
),
generated AS (
    SELECT
        atm.id AS atm_id,
        atm.rn,
        slot,
        params.base_hour - ((slot - 1) * interval '1 hour') AS reading_hour,
        20 + ((atm.rn * 13 + slot * 7) % 91) AS tx_count,
        CASE
            WHEN atm.rn <= 21 THEN
                3600 - CASE WHEN (atm.rn + slot) % 5 = 0 THEN 600 ELSE 0 END
            WHEN atm.rn <= 23 THEN 0
            ELSE 1200
        END AS available_seconds
    FROM selected atm
    CROSS JOIN generate_series(1, 6) AS slot
    CROSS JOIN params
)
INSERT INTO public.atm_readings (
    atm_id,
    hora,
    transacciones,
    transacciones_exitosas,
    monto_retirado,
    nivel_efectivo_pct,
    segundos_observados,
    segundos_disponible,
    segundos_utilizado,
    id
)
SELECT
    atm_id,
    reading_hour,
    tx_count,
    tx_count - ((rn + slot) % 4),
    (tx_count - ((rn + slot) % 4)) * (500 + ((rn + slot) % 8) * 250),
    CASE
        WHEN rn <= 17 THEN 65 + ((rn + slot) % 25)
        WHEN rn <= 21 THEN 7 + slot * 2 + ((rn - 18) % 3)
        WHEN rn <= 23 THEN 35 + ((rn - 22) * 5)
        ELSE 55 + ((rn - 24) * 5)
    END,
    3600,
    available_seconds,
    least(available_seconds, 900 + ((rn * 97 + slot * 211) % 1900)),
    md5('KPI_TEST_TRANSACTIONS_V1:ATM:' || atm_id::text || ':' || slot::text)::UUID
FROM generated;

-- --------------------------------------------------------------------------
-- 2. SUCURSALES: 25 oficinas x 6 horas = 150 lecturas operativas
-- --------------------------------------------------------------------------
WITH
params AS (
    SELECT date_trunc('hour', now()) - interval '1 hour' AS base_hour
),
selected AS (
    SELECT
        chosen.id,
        row_number() OVER (ORDER BY chosen.codigo, chosen.id)::INTEGER AS rn
    FROM (
        SELECT id, codigo
        FROM public.sucursales
        ORDER BY
            (fuente = 'bhd_public_locations_api') DESC,
            codigo,
            id
        LIMIT 25
    ) chosen
),
generated AS (
    SELECT
        branch.id AS sucursal_id,
        branch.rn,
        slot,
        params.base_hour - ((slot - 1) * interval '1 hour') AS reading_hour,
        18 + ((branch.rn * 11 + slot * 5) % 58) AS visitors,
        3 + ((branch.rn + slot) % 5) AS tellers
    FROM selected branch
    CROSS JOIN generate_series(1, 6) AS slot
    CROSS JOIN params
),
calculated AS (
    SELECT
        *,
        visitors - (2 + ((rn + slot) % 5)) AS served
    FROM generated
)
INSERT INTO public.branch_readings (
    sucursal_id,
    hora,
    visitantes,
    clientes_atendidos,
    clientes_dentro_sla,
    espera_total_segundos,
    cajeros_disponibles,
    cola_actual,
    segundos_cajero_disponibles,
    segundos_cajero_ocupados,
    id
)
SELECT
    sucursal_id,
    reading_hour,
    visitors,
    served,
    greatest(0, served - ((rn + slot) % 7)),
    served * (180 + ((rn * 23 + slot * 31) % 540)),
    tellers,
    (rn * 3 + slot) % 12,
    tellers * 3600,
    least(tellers * 3600, 2400 + ((rn * 307 + slot * 419) % 9000)),
    md5(
        'KPI_TEST_TRANSACTIONS_V1:BRANCH:' || sucursal_id::text || ':' || slot::text
    )::UUID
FROM calculated;

-- --------------------------------------------------------------------------
-- 3. SALDOS DE SUCURSALES: 25 oficinas x 6 fechas = 150 registros
-- --------------------------------------------------------------------------
WITH
params AS (
    SELECT current_date AS base_date
),
selected AS (
    SELECT
        chosen.id,
        row_number() OVER (ORDER BY chosen.codigo, chosen.id)::INTEGER AS rn
    FROM (
        SELECT id, codigo
        FROM public.sucursales
        ORDER BY
            (fuente = 'bhd_public_locations_api') DESC,
            codigo,
            id
        LIMIT 25
    ) chosen
),
generated AS (
    SELECT
        branch.id AS sucursal_id,
        branch.rn,
        slot,
        params.base_date - (slot - 1) AS balance_date
    FROM selected branch
    CROSS JOIN generate_series(1, 6) AS slot
    CROSS JOIN params
)
INSERT INTO public.branch_financials (
    sucursal_id,
    fecha,
    depositos,
    prestamos,
    id
)
SELECT
    sucursal_id,
    balance_date,
    (
        15000000 + rn * 750000 + (7 - slot) * 125000
    )::NUMERIC(20, 2),
    (
        8000000 + rn * 425000 + (7 - slot) * 90000
    )::NUMERIC(20, 2),
    md5(
        'KPI_TEST_TRANSACTIONS_V1:FINANCIAL:' || sucursal_id::text || ':' || slot::text
    )::UUID
FROM generated;

-- --------------------------------------------------------------------------
-- 4. SUBAGENTES: 25 comercios x 6 transacciones = 150 transacciones
-- --------------------------------------------------------------------------
WITH
params AS (
    SELECT date_trunc('hour', now()) - interval '1 hour' AS base_hour
),
selected AS (
    SELECT
        chosen.id,
        row_number() OVER (ORDER BY chosen.codigo_unico, chosen.id)::INTEGER AS rn
    FROM (
        SELECT id, codigo_unico
        FROM public.subagentes
        WHERE activo IS TRUE
        ORDER BY
            (fuente = 'bhd_public_locations_api') DESC,
            codigo_unico,
            id
        LIMIT 25
    ) chosen
),
generated AS (
    SELECT
        subagent.id AS subagente_id,
        subagent.rn,
        slot,
        params.base_hour
            - ((slot - 1) * interval '1 hour')
            + (((subagent.rn * 2 + slot) % 55) * interval '1 minute') AS transaction_time
    FROM selected subagent
    CROSS JOIN generate_series(1, 6) AS slot
    CROSS JOIN params
)
INSERT INTO public.subagent_test_transactions (
    id,
    subagente_id,
    ocurrida_en,
    tipo,
    estado,
    monto,
    comision,
    referencia,
    batch_tag
)
SELECT
    md5(
        'KPI_TEST_TRANSACTIONS_V1:SUBAGENT:' || subagente_id::text || ':' || slot::text
    )::UUID,
    subagente_id,
    transaction_time,
    (ARRAY['RETIRO', 'DEPOSITO', 'PAGO_SERVICIO', 'TRANSFERENCIA'])[
        1 + ((rn + slot) % 4)
    ],
    CASE
        WHEN (rn + slot) % 17 = 0 THEN 'RECHAZADA'
        WHEN (rn + slot) % 29 = 0 THEN 'REVERSADA'
        ELSE 'APROBADA'
    END,
    (500 + ((rn * 173 + slot * 337) % 19500))::NUMERIC(18, 2),
    (10 + ((rn + slot) % 6) * 5)::NUMERIC(18, 2),
    left(
        'KPI-TEST-SA-' || replace(subagente_id::text, '-', '') || '-' || slot::text,
        80
    ),
    'KPI_TEST_TRANSACTIONS_V1'
FROM generated;

-- Verificación automática. Cualquier diferencia aborta toda la transacción.
DO $verification$
DECLARE
    v_atm_rows       BIGINT;
    v_branch_rows    BIGINT;
    v_financial_rows BIGINT;
    v_subagent_rows  BIGINT;
    v_backup_rows    BIGINT;
    v_low_cash_rows  BIGINT;
BEGIN
    SELECT count(*)
    INTO v_atm_rows
    FROM public.atm_readings reading
    WHERE reading.id IN (
        SELECT md5(
            'KPI_TEST_TRANSACTIONS_V1:ATM:' || atm.id::text || ':' || slot::text
        )::UUID
        FROM public.atms atm
        CROSS JOIN generate_series(1, 6) AS slot
    );

    SELECT count(*)
    INTO v_branch_rows
    FROM public.branch_readings reading
    WHERE reading.id IN (
        SELECT md5(
            'KPI_TEST_TRANSACTIONS_V1:BRANCH:' || branch.id::text || ':' || slot::text
        )::UUID
        FROM public.sucursales branch
        CROSS JOIN generate_series(1, 6) AS slot
    );

    SELECT count(*)
    INTO v_subagent_rows
    FROM public.subagent_test_transactions
    WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1';

    SELECT count(*)
    INTO v_financial_rows
    FROM public.branch_financials financial
    WHERE financial.id IN (
        SELECT md5(
            'KPI_TEST_TRANSACTIONS_V1:FINANCIAL:' || branch.id::text || ':' || slot::text
        )::UUID
        FROM public.sucursales branch
        CROSS JOIN generate_series(1, 6) AS slot
    );

    SELECT count(*)
    INTO v_backup_rows
    FROM public.atm_test_state_backup
    WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1';

    SELECT count(*)
    INTO v_low_cash_rows
    FROM public.atms atm
    JOIN public.atm_test_state_backup backup ON backup.atm_id = atm.id
    WHERE backup.batch_tag = 'KPI_TEST_TRANSACTIONS_V1'
      AND atm.estado = 'BAJO_EFECTIVO'
      AND atm.nivel_efectivo_pct <= 20;

    IF v_atm_rows <> 150
       OR v_branch_rows <> 150
       OR v_financial_rows <> 150
       OR v_subagent_rows <> 150
       OR v_backup_rows <> 25
       OR v_low_cash_rows <> 4 THEN
        RAISE EXCEPTION
            'Validación fallida. ATM=%, sucursal=%, saldos=%, subagente=%, respaldos ATM=%, alertas low cash=%',
            v_atm_rows,
            v_branch_rows,
            v_financial_rows,
            v_subagent_rows,
            v_backup_rows,
            v_low_cash_rows;
    END IF;

    RAISE NOTICE
        'Batch listo: ATM=%, sucursal=%, saldos=%, subagente=%, alertas low cash=%',
        v_atm_rows,
        v_branch_rows,
        v_financial_rows,
        v_subagent_rows,
        v_low_cash_rows;
END
$verification$;

COMMIT;

SELECT
    'KPI_TEST_TRANSACTIONS_V1' AS batch,
    150 AS lecturas_atm,
    150 AS lecturas_sucursal,
    150 AS saldos_sucursal,
    150 AS transacciones_subagente,
    4 AS alertas_bajo_efectivo,
    600 AS total_registros_prueba;
