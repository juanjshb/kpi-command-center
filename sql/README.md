# SQL para crear la base de datos

Estos archivos crean la base PostgreSQL del KPI Command Center sin depender de la API.

## Archivos

- `00_create_database.sql`: crea el rol `kpi_user` y la base `kpi_command_center`.
- `01_schema.sql`: crea enums, tablas, constraints, indices y registra la migracion `0001_core`.
- `02_seed_demo.sql`: inserta datos demo para los dashboards: provincias, sucursales, ATMs, incidencias, recargas CIT, lecturas, competencia y ubicaciones candidatas.

## Ejecucion

Desde la raiz del proyecto:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d postgres -f sql\00_create_database.sql
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U kpi_user -d kpi_command_center -f sql\01_schema.sql
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U kpi_user -d kpi_command_center -f sql\02_seed_demo.sql
```

Si `psql` esta en tu PATH, puedes usar:

```powershell
psql -U postgres -d postgres -f sql\00_create_database.sql
psql -U kpi_user -d kpi_command_center -f sql\01_schema.sql
psql -U kpi_user -d kpi_command_center -f sql\02_seed_demo.sql
```

## Conexion de la API

Usa una URL como esta en `.env`:

```env
DATABASE_URL=postgresql+psycopg://kpi_user:change_me_strong_password@127.0.0.1:5432/kpi_command_center
```

Para Docker Compose, el host debe ser `db` dentro de la red de compose.

```env
DATABASE_URL=postgresql+psycopg://kpi_user:change_me_strong_password@db:5432/kpi_command_center
```
