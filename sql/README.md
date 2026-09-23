# SQL del KPI Command Center

El directorio contiene cinco scripts ejecutables, ordenados por dependencia.

## Archivos

1. `00_database.sql`: crea el rol y la base PostgreSQL. Se ejecuta como administrador.
2. `01_schema.sql`: crea enums, tablas, restricciones e índices hasta la revisión `0004_job_runs`.
3. `02_functions.sql`: instala funciones auxiliares y triggers de `updated_at`.
4. `03_sample_data.sql`: carga datos sintéticos e idempotentes para los dashboards.
5. `04_clear.sql`: elimina los datos de muestra o, con confirmación explícita, todo el inventario de ubicaciones.

## Instalación desde cero

```powershell
psql -U postgres -d postgres -f sql\00_database.sql
psql -U kpi_user -d kpi_command_center -f sql\01_schema.sql
psql -U kpi_user -d kpi_command_center -f sql\02_functions.sql
psql -U kpi_user -d kpi_command_center -f sql\03_sample_data.sql
```

Antes de usar `00_database.sql` fuera de desarrollo, cambia la variable
`app_password` incluida al inicio del archivo.

## Datos de muestra

`03_sample_data.sql` puede ejecutarse más de una vez. Reutiliza el inventario
existente y sólo crea ubicaciones sintéticas si hay menos de 25 entidades por
canal. Genera:

- 150 lecturas de ATM;
- 150 lecturas de sucursal;
- 150 saldos diarios de sucursal;
- 150 transacciones de subagentes;
- estados para 25 ATM, incluidas cuatro alertas de bajo efectivo;
- sucursales Scotiabank y ubicaciones candidatas de muestra cuando no existen.

Los estados originales de los ATM quedan respaldados para que la limpieza pueda
restaurarlos.

## Limpiar únicamente los datos de muestra

Este es el modo predeterminado y no necesita confirmación:

```powershell
psql -U kpi_user -d kpi_command_center -f sql\04_clear.sql
```

## Limpiar todo el inventario de ubicaciones

Este modo elimina sucursales, ATM, subagentes, lecturas, saldos, incidencias,
recargas, candidatos, competencia, cortes de mercado e instituciones. Conserva
usuarios, jobs, provincias, funciones y estructura.

```powershell
psql -U kpi_user -d kpi_command_center `
  -c "SET kpi.clear_scope = 'all'; SET kpi.clear_confirmation = 'BORRAR_LOCALIZACIONES';" `
  -f sql\04_clear.sql
```

La confirmación es obligatoria; sin ella la transacción se aborta.

## Conexión de la aplicación

```env
DATABASE_URL=postgresql+psycopg2://kpi_user:change_me_strong_password@127.0.0.1:5432/kpi_command_center
```

En Docker Compose, usa `db` como host.
