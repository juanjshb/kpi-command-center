-- ============================================================================
-- FUNCIONES Y TRIGGERS DE BASE DE DATOS
-- Ejecutar después de 01_schema.sql.
-- ============================================================================

BEGIN;

-- UUID determinístico utilizado por los datos de muestra y su limpieza.
CREATE OR REPLACE FUNCTION public.kpi_uuid(p_value TEXT)
RETURNS UUID
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $function$
    SELECT md5(p_value)::UUID
$function$;

-- Mantiene updated_at consistente incluso cuando la escritura no viene de la API.
CREATE OR REPLACE FUNCTION public.kpi_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$function$;

DO $triggers$
DECLARE
    v_table TEXT;
BEGIN
    FOREACH v_table IN ARRAY ARRAY[
        'users',
        'job_runs',
        'candidate_locations',
        'competitor_locations',
        'sucursales',
        'atms',
        'subagentes',
        'incidencias',
        'logistica_recargas'
    ]
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_%1$s_updated_at ON public.%1$I',
            v_table
        );
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at '
            'BEFORE UPDATE ON public.%1$I '
            'FOR EACH ROW EXECUTE FUNCTION public.kpi_set_updated_at()',
            v_table
        );
    END LOOP;
END
$triggers$;

COMMIT;
