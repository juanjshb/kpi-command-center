-- ============================================================================
-- LIMPIEZA DE DATOS
-- ============================================================================
-- Modo predeterminado: limpia únicamente 03_sample_data.sql y restaura los
-- estados originales de ATM.
--
-- Para borrar TODO el inventario de ubicaciones y sus dependencias, ejecutar
-- estas dos sentencias en la misma sesión antes de este archivo:
--
--   SET kpi.clear_scope = 'all';
--   SET kpi.clear_confirmation = 'BORRAR_LOCALIZACIONES';
--
-- El modo all conserva users, job_runs, provincias, funciones y schema.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '3min';

SELECT pg_advisory_xact_lock(714005);

DO $validation$
DECLARE
    v_scope TEXT := coalesce(
        nullif(current_setting('kpi.clear_scope', true), ''),
        'sample'
    );
    v_confirmation TEXT := current_setting('kpi.clear_confirmation', true);
BEGIN
    IF v_scope NOT IN ('sample', 'all') THEN
        RAISE EXCEPTION 'kpi.clear_scope debe ser sample o all; recibido=%', v_scope;
    END IF;

    IF v_scope = 'all' AND v_confirmation IS DISTINCT FROM 'BORRAR_LOCALIZACIONES' THEN
        RAISE EXCEPTION
            'Modo all cancelado: configure kpi.clear_confirmation=BORRAR_LOCALIZACIONES';
    END IF;

    PERFORM set_config('kpi.clear_scope', v_scope, true);
    RAISE NOTICE 'Modo de limpieza: %', v_scope;
END
$validation$;

-- Garantiza que la limpieza selectiva funcione si el seed nunca fue ejecutado.
CREATE TABLE IF NOT EXISTS public.sample_seed_registry (
    batch_tag VARCHAR(80) NOT NULL,
    entity_type VARCHAR(40) NOT NULL,
    entity_id UUID NOT NULL,
    PRIMARY KEY (batch_tag, entity_type, entity_id)
);

-- Restaurar los campos maestros modificados para simular estados operativos.
DO $restore_atms$
DECLARE
    v_expected BIGINT := 0;
    v_restored BIGINT := 0;
BEGIN
    IF to_regclass('public.atm_test_state_backup') IS NOT NULL THEN
        EXECUTE $sql$
            SELECT count(*)
            FROM public.atm_test_state_backup
            WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1'
        $sql$
        INTO v_expected;

        EXECUTE $sql$
            UPDATE public.atms atm
            SET
                nivel_efectivo_pct = backup.nivel_efectivo_pct,
                estado = backup.estado::public.atm_status,
                ultima_comunicacion = backup.ultima_comunicacion
            FROM public.atm_test_state_backup backup
            WHERE backup.batch_tag = 'KPI_TEST_TRANSACTIONS_V1'
              AND backup.atm_id = atm.id
        $sql$;
        GET DIAGNOSTICS v_restored = ROW_COUNT;

        IF v_restored <> v_expected THEN
            RAISE EXCEPTION
                'Restauración ATM incompleta. Esperados=%, restaurados=%',
                v_expected,
                v_restored;
        END IF;
    END IF;

    RAISE NOTICE 'Estados originales de ATM restaurados: %', v_restored;
END
$restore_atms$;

DROP TABLE IF EXISTS public.atm_test_state_backup;

-- Dependencias operativas.
DELETE FROM public.incidencias incident
WHERE current_setting('kpi.clear_scope') = 'all'
   OR incident.atm_id IN (
        SELECT entity_id FROM public.sample_seed_registry
        WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1' AND entity_type = 'atm'
   )
   OR incident.sucursal_id IN (
        SELECT entity_id FROM public.sample_seed_registry
        WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1' AND entity_type = 'sucursal'
   );

DELETE FROM public.logistica_recargas refill
WHERE current_setting('kpi.clear_scope') = 'all'
   OR refill.atm_id IN (
        SELECT entity_id FROM public.sample_seed_registry
        WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1' AND entity_type = 'atm'
   );

DELETE FROM public.atm_readings reading
WHERE current_setting('kpi.clear_scope') = 'all'
   OR reading.id IN (
        SELECT md5(
            'KPI_TEST_TRANSACTIONS_V1:ATM:' || atm.id::text || ':' || slot::text
        )::UUID
        FROM public.atms atm
        CROSS JOIN generate_series(1, 6) AS slot
   );

DELETE FROM public.branch_readings reading
WHERE current_setting('kpi.clear_scope') = 'all'
   OR reading.id IN (
        SELECT md5(
            'KPI_TEST_TRANSACTIONS_V1:BRANCH:' || branch.id::text || ':' || slot::text
        )::UUID
        FROM public.sucursales branch
        CROSS JOIN generate_series(1, 6) AS slot
   );

DELETE FROM public.branch_financials financial
WHERE current_setting('kpi.clear_scope') = 'all'
   OR financial.id IN (
        SELECT md5(
            'KPI_TEST_TRANSACTIONS_V1:FINANCIAL:' || branch.id::text || ':' || slot::text
        )::UUID
        FROM public.sucursales branch
        CROSS JOIN generate_series(1, 6) AS slot
   );

DO $subagent_transactions$
BEGIN
    IF to_regclass('public.subagent_test_transactions') IS NOT NULL THEN
        IF current_setting('kpi.clear_scope') = 'all' THEN
            EXECUTE 'DELETE FROM public.subagent_test_transactions';
        ELSE
            EXECUTE $sql$
                DELETE FROM public.subagent_test_transactions
                WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1'
            $sql$;
        END IF;
    END IF;
END
$subagent_transactions$;

DROP TABLE IF EXISTS public.subagent_test_transactions;

-- Datos geoespaciales y comparativos.
DELETE FROM public.candidate_locations candidate
WHERE current_setting('kpi.clear_scope') = 'all'
   OR candidate.fuente = 'sql_sample_v1'
   OR candidate.id IN (
        SELECT entity_id FROM public.sample_seed_registry
        WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1'
          AND entity_type = 'candidate_location'
   );

DELETE FROM public.competitor_locations competitor
WHERE current_setting('kpi.clear_scope') = 'all'
   OR competitor.fuente = 'sql_sample_v1'
   OR competitor.id IN (
        SELECT entity_id FROM public.sample_seed_registry
        WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1'
          AND entity_type = 'competitor_location'
   );

DELETE FROM public.market_snapshots
WHERE current_setting('kpi.clear_scope') = 'all';

-- Inventario sintético. El orden respeta sus claves foráneas.
DELETE FROM public.subagentes entity
WHERE current_setting('kpi.clear_scope') = 'all'
   OR entity.id IN (
        SELECT entity_id FROM public.sample_seed_registry
        WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1' AND entity_type = 'subagente'
   );

DELETE FROM public.atms entity
WHERE current_setting('kpi.clear_scope') = 'all'
   OR entity.id IN (
        SELECT entity_id FROM public.sample_seed_registry
        WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1' AND entity_type = 'atm'
   );

DELETE FROM public.sucursales entity
WHERE current_setting('kpi.clear_scope') = 'all'
   OR entity.id IN (
        SELECT entity_id FROM public.sample_seed_registry
        WHERE batch_tag = 'KPI_TEST_TRANSACTIONS_V1' AND entity_type = 'sucursal'
   );

-- Auditorías lógicas del inventario eliminado en modo completo.
DELETE FROM public.audit_logs audit
WHERE current_setting('kpi.clear_scope') = 'all'
  AND audit.entidad IN (
      'atms', 'sucursales', 'subagentes', 'atm_readings',
      'branch_readings', 'branch_financials', 'incidencias',
      'logistica_recargas', 'candidate_locations',
      'competitor_locations', 'market_snapshots', 'institutions'
  );

-- En sample sólo se eliminan instituciones/provincias con IDs determinísticos
-- creados por el seed y siempre que ya no tengan referencias.
DELETE FROM public.institutions institution
WHERE (
        current_setting('kpi.clear_scope') = 'all'
        OR institution.id IN (
            public.kpi_uuid('KPI_SAMPLE:INSTITUTION:BHD Leon'),
            public.kpi_uuid('KPI_SAMPLE:INSTITUTION:Scotiabank')
        )
      )
  AND NOT EXISTS (
      SELECT 1 FROM public.competitor_locations location
      WHERE location.institucion_id = institution.id
  )
  AND NOT EXISTS (
      SELECT 1 FROM public.market_snapshots snapshot
      WHERE snapshot.institucion_id = institution.id
  );

DELETE FROM public.provincias province
WHERE current_setting('kpi.clear_scope') = 'sample'
  AND province.id = public.kpi_uuid('KPI_SAMPLE:PROVINCE:' || province.nombre)
  AND NOT EXISTS (SELECT 1 FROM public.sucursales x WHERE x.provincia = province.nombre)
  AND NOT EXISTS (SELECT 1 FROM public.atms x WHERE x.provincia = province.nombre)
  AND NOT EXISTS (SELECT 1 FROM public.subagentes x WHERE x.provincia = province.nombre)
  AND NOT EXISTS (SELECT 1 FROM public.candidate_locations x WHERE x.provincia = province.nombre)
  AND NOT EXISTS (SELECT 1 FROM public.competitor_locations x WHERE x.provincia = province.nombre)
  AND NOT EXISTS (SELECT 1 FROM public.market_snapshots x WHERE x.provincia = province.nombre);

DROP TABLE public.sample_seed_registry;

-- Verificación automática antes del COMMIT.
DO $verification$
DECLARE
    v_scope TEXT := current_setting('kpi.clear_scope');
    v_remaining BIGINT;
BEGIN
    IF to_regclass('public.subagent_test_transactions') IS NOT NULL
       OR to_regclass('public.atm_test_state_backup') IS NOT NULL
       OR to_regclass('public.sample_seed_registry') IS NOT NULL THEN
        RAISE EXCEPTION 'Quedaron tablas auxiliares del seed';
    END IF;

    IF v_scope = 'all' THEN
        SELECT
            (SELECT count(*) FROM public.atms)
            + (SELECT count(*) FROM public.sucursales)
            + (SELECT count(*) FROM public.subagentes)
            + (SELECT count(*) FROM public.atm_readings)
            + (SELECT count(*) FROM public.branch_readings)
            + (SELECT count(*) FROM public.branch_financials)
            + (SELECT count(*) FROM public.incidencias)
            + (SELECT count(*) FROM public.logistica_recargas)
            + (SELECT count(*) FROM public.candidate_locations)
            + (SELECT count(*) FROM public.competitor_locations)
            + (SELECT count(*) FROM public.market_snapshots)
            + (SELECT count(*) FROM public.institutions)
        INTO v_remaining;

        IF v_remaining <> 0 THEN
            RAISE EXCEPTION 'Limpieza all incompleta; registros restantes=%', v_remaining;
        END IF;
    ELSE
        SELECT
            (SELECT count(*) FROM public.candidate_locations WHERE fuente = 'sql_sample_v1')
            + (SELECT count(*) FROM public.competitor_locations WHERE fuente = 'sql_sample_v1')
            + (SELECT count(*) FROM public.atms WHERE fuente = 'sql_sample_v1')
            + (SELECT count(*) FROM public.sucursales WHERE fuente = 'sql_sample_v1')
            + (SELECT count(*) FROM public.subagentes WHERE fuente = 'sql_sample_v1')
        INTO v_remaining;

        IF v_remaining <> 0 THEN
            RAISE EXCEPTION 'Limpieza sample incompleta; registros restantes=%', v_remaining;
        END IF;
    END IF;
END
$verification$;

COMMIT;

SELECT 'Limpieza completada correctamente' AS resultado;
