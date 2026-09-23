# KPI Command Center

Centro de control para visualizar y operar la red física bancaria en República Dominicana. Integra inventario de sucursales, cajeros automáticos y subagentes; telemetría operacional; logística de efectivo; planificación geoespacial; competencia y jobs de sincronización.

La solución incluye una API REST con FastAPI, un dashboard web servido por la misma aplicación y una base PostgreSQL con migraciones, auditoría y scripts SQL reproducibles.

La solucion conecta con fuentes oficiales de BHD y Scotiabank adeams de algunos web scrappers para mostrar las locaciones, pero datos como depositos y transacciones son datos de prueba. Todo funciona si alteras un valor en la DB ves los cambios cuando refresques.

![Dashboard de operaciones ATM](images/page4.png)
![Dashboard de operaciones Sucursales](images/page3.png)
![Dashboard de operaciones Subagentes](images/page2.png)
![Dashboard de Analiticas](images/page1.png)

## Capacidades principales

- Monitoreo de disponibilidad, utilización, transacciones y efectivo de ATM.
- Alertas de bajo efectivo y detección de equipos sin comunicación reciente.
- Seguimiento de colas, espera, SLA y capacidad de atención en sucursales.
- Saldos diarios propios de depósitos y préstamos por sucursal.
- Inventario y cobertura geográfica de subagentes bancarios.
- Comparación territorial con sucursales de Scotiabank.
- Evaluación de ubicaciones candidatas y competidores cercanos.
- Sincronización idempotente del inventario público de BHD.
- Historial y progreso de jobs ejecutados desde el dashboard.
- Autenticación JWT, permisos por rol y auditoría de escrituras.

## Casos de uso

### 1. Monitorear la red de ATM

Un equipo de operaciones puede identificar cuántos ATM están operativos, con bajo efectivo, en mantenimiento o fuera de servicio. El dashboard combina el estado actual del equipo con lecturas históricas para mostrar uptime, utilización, transacciones y monto retirado.

Ejemplo de decisión: priorizar los ATM con efectivo menor o igual al umbral configurado y mayor volumen transaccional.

### 2. Coordinar recargas de efectivo

Cuando un ATM entra en `BAJO_EFECTIVO`, un operador puede registrar una orden CIT, asignar una transportadora y controlar su transición de `PROGRAMADA` a `EN_TRANSITO` y `COMPLETADA`. Al completar la orden se registra el monto entregado y el nivel de efectivo medido.

Ejemplo de decisión: agrupar recargas urgentes por provincia y evitar una segunda ejecución de la misma orden.

### 3. Mejorar atención y SLA en sucursales

Los responsables de oficinas pueden comparar visitantes, clientes atendidos, espera promedio, cumplimiento de SLA, cola actual y utilización de cajeros humanos.

Ejemplo de decisión: reforzar personal en las horas con mayor tráfico o en sucursales cuya espera ponderada supera el objetivo.

### 4. Analizar cobertura de subagentes

El módulo de subagentes permite buscar comercios aliados, filtrar por provincia o región, revisar horarios extendidos y distinguir registros con o sin coordenadas.

Ejemplo de decisión: detectar provincias con baja cobertura y priorizar la incorporación o georreferenciación de nuevos aliados.

### 5. Planificar expansión de la red

Geospatial Analytics combina sucursales propias, competencia, densidad territorial y ubicaciones candidatas. La participación de mercado se calcula por cantidad de sucursales observadas, no por depósitos estimados de competidores.

Ejemplo de decisión: evaluar una nueva sucursal según su potencial, la cobertura actual y los puntos competidores dentro de un radio configurable.

### 6. Consultar depósitos propios por sucursal

`Total Branch Deposits` suma el último saldo disponible de cada sucursal hasta la fecha seleccionada. No suma saldos de días diferentes ni intenta inferir depósitos de otras instituciones.

Ejemplo de decisión: comparar la distribución de depósitos propios por provincia con la presencia física de la red.

### 7. Actualizar el inventario BHD desde el dashboard

Usuarios `ADMIN` y `OPERATOR` pueden iniciar el job de ubicaciones BHD, seguir su progreso y consultar el resultado persistente. La carga actualiza sucursales, ATM y subagentes por `fuente + fuente_id`, evitando duplicados.

Ejemplo de decisión: ejecutar la sincronización después de una actualización pública del banco y revisar cuántos registros fueron insertados, actualizados u omitidos.

### 8. Mantener una muestra competitiva verificable

El sincronizador de competencia carga actualmente sucursales oficiales de Scotiabank. Los ATM y subagentes competidores permanecen fuera del alcance hasta disponer de una fuente confiable.

Ejemplo de decisión: recalcular la cuota de sucursales después de actualizar la presencia física de Scotia.

## Módulos del dashboard

| Módulo | Ruta | Contenido |
|---|---|---|
| Operaciones ATM | `/dashboard/atm.html` | Estados, efectivo, uptime, transacciones, incidencias y CIT |
| Sucursales | `/dashboard/branches.html` | Colas, SLA, tráfico, capacidad y estado de oficinas |
| Subagentes | `/dashboard/subagents.html` | Inventario, cobertura, búsqueda y mapa |
| Geospatial Analytics | `/dashboard/planning.html` | Cuota por sucursales, competencia y candidatos |
| Jobs | `/dashboard/jobs.html` | Ejecución e historial de sincronizaciones BHD |

![Dashboard de sucursales](images/page2.jpg)

![Dashboard de planificación geoespacial](images/page3.jpg)

## Cómo se conectan los componentes

```mermaid
flowchart LR
    U[Usuarios] --> D[Dashboard HTML y JavaScript]
    D --> A[FastAPI /api/v1]
    A --> P[(PostgreSQL)]
    A --> J[Jobs en segundo plano]
    J --> B[BHD Locations API]
    S[Scraper Scotiabank] --> A
    T[Telemetría e integraciones] --> A
```

## Stack

- Python 3.11+
- FastAPI y Uvicorn
- SQLAlchemy 2 y Psycopg2
- PostgreSQL 18
- Alembic
- Pydantic v2
- JWT y Bcrypt
- HTML, CSS y JavaScript sin framework de frontend
- Google Maps JavaScript API opcional
- Docker Compose y pgAdmin opcional

## Inicio rápido con Docker

Requisitos: Python, Docker y Docker Compose.

```powershell
python scripts/init_env.py
docker compose up --build -d
docker compose exec api python -m app.db.seed
```

`scripts/init_env.py` crea `.env` con secretos aleatorios y conserva cualquier archivo existente. Compose espera a PostgreSQL, aplica las migraciones y luego inicia la API.

Servicios disponibles:

| Servicio | URL |
|---|---|
| Dashboard | http://localhost:8000/dashboard/ |
| Swagger | http://localhost:8000/docs |
| OpenAPI | http://localhost:8000/openapi.json |
| Health check | http://localhost:8000/health/ready |

Credenciales del seed de desarrollo:

```text
Usuario: admin@bank.com
Clave:   admin123
```

El seed está bloqueado cuando `APP_ENV=production`.

Para habilitar pgAdmin:

```powershell
docker compose --profile tools up -d pgadmin
```

Abre http://localhost:5050 y registra PostgreSQL usando `db` como host y `5432` como puerto interno.

## Instalación local

Requiere Python 3.11 o posterior y una base PostgreSQL existente.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe scripts\init_env.py
```

Configura la conexión en `.env` y ejecuta:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m app.db.seed
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```

En Linux y macOS sustituye `.venv\Scripts\` por `.venv/bin/`.

## Configuración

Las variables principales están documentadas en [.env.example](.env.example).

| Variable | Uso | Predeterminado |
|---|---|---|
| `APP_ENV` | `development`, `test` o `production` | `development` |
| `DATABASE_URL` | Reemplaza los parámetros PostgreSQL individuales | Vacío |
| `POSTGRES_*` | Usuario, clave, base, host y puerto | Configuración local |
| `SECRET_KEY` | Firma de tokens JWT; mínimo 32 caracteres | Obligatoria |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Duración del token | `45` |
| `LOW_CASH_THRESHOLD` | Umbral de alerta de efectivo | `20` |
| `STALE_AFTER_MINUTES` | Tiempo para marcar un ATM sin comunicación | `15` |
| `GOOGLE_MAPS_API_KEY` | Habilita mapas en el dashboard | Vacío |
| `CORS_ORIGINS` | Orígenes permitidos por la API | Locales |
| `TRUSTED_HOSTS` | Hosts HTTP aceptados | Locales |

Sin `GOOGLE_MAPS_API_KEY`, las tarjetas, tablas y gráficos continúan funcionando; sólo el mapa muestra un aviso.

## Autenticación y roles

`POST /api/v1/auth/login` utiliza formulario OAuth2. El correo se envía en `username` y las demás rutas reciben `Authorization: Bearer <token>`.

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/auth/login `
  -Body @{username='admin@bank.com'; password='admin123'}

$headers = @{Authorization="Bearer $($login.access_token)"}
Invoke-RestMethod `
  -Uri http://localhost:8000/api/v1/metrics/summary `
  -Headers $headers
```

| Capacidad | ADMIN | OPERATOR | ANALYST |
|---|:---:|:---:|:---:|
| Consultar dashboard, inventario y mapas | Sí | Sí | Sí |
| Modificar operaciones, incidencias y recargas | Sí | Sí | No |
| Ejecutar sincronización BHD | Sí | Sí | No |
| Gestionar usuarios, provincias e instituciones | Sí | No | No |
| Consultar auditoría | Sí | No | No |

Para crear el primer administrador sin cargar datos demo:

```powershell
.\.venv\Scripts\python.exe -m app.db.create_admin `
  --email admin@tu-banco.com `
  --name "Administrador"
```

## Semántica importante de los datos

- `SIN_DATOS` significa que la ubicación existe en el inventario, pero todavía no tiene telemetría operacional.
- `BAJO_EFECTIVO` usa `LOW_CASH_THRESHOLD`; por defecto se activa con un nivel menor o igual a 20%.
- La disponibilidad actual excluye los ATM `SIN_DATOS` del denominador observado.
- El uptime histórico se calcula con segundos disponibles sobre segundos observados.
- La espera promedio de sucursales está ponderada por clientes atendidos.
- Los depósitos y préstamos son saldos propios; se toma el último corte de cada sucursal.
- La cuota geoespacial usa cantidad de sucursales propias y competidoras observadas.
- Los periodos sin lecturas no se completan artificialmente con ceros.
- Los importes monetarios se expresan en pesos dominicanos y se serializan sin pérdida de precisión.

## Sincronización de ubicaciones BHD

### Desde el dashboard

Abre `/dashboard/jobs.html` y ejecuta la actualización. Sólo puede existir un job BHD activo; el historial permanece en `job_runs`.

Endpoints relacionados:

```text
POST /api/v1/jobs/bhd-locations
GET  /api/v1/jobs
GET  /api/v1/jobs/{id}
```

### Desde línea de comandos

```powershell
.\.venv\Scripts\python.exe scripts\scrapers\bhd_branches_scraper.py --load-db
```

Para validar la carga sin confirmar cambios:

```powershell
.\.venv\Scripts\python.exe scripts\scrapers\bhd_branches_scraper.py --load-db --dry-run
```

También se puede reutilizar un CSV previamente generado:

```powershell
.\.venv\Scripts\python.exe -m app.db.import_bhd_locations `
  --input data\bhd_locations_rd.csv `
  --dry-run
```

## Sincronización de sucursales Scotiabank

La integración competitiva sólo carga sucursales por ahora.

```powershell
.\.venv\Scripts\python.exe -m app.services.competitors_sync `
  --checkpoint data\scotiabank_branches_rd.csv `
  --browser msedge
```

Para cargar un archivo existente o validar con rollback:

```powershell
.\.venv\Scripts\python.exe -m app.services.competitors_sync `
  --input data\scotiabank_branches_rd.csv

.\.venv\Scripts\python.exe -m app.services.competitors_sync `
  --input data\scotiabank_branches_rd.csv `
  --dry-run
```

## Scripts SQL

El directorio [`sql/`](sql/) contiene cinco scripts ordenados:

```text
00_database.sql
01_schema.sql
02_functions.sql
03_sample_data.sql
04_clear.sql
```

Instalación SQL completa:

```powershell
psql -U postgres -d postgres -f sql\00_database.sql
psql -U kpi_user -d kpi_command_center -f sql\01_schema.sql
psql -U kpi_user -d kpi_command_center -f sql\02_functions.sql
psql -U kpi_user -d kpi_command_center -f sql\03_sample_data.sql
```

El sample SQL genera 150 lecturas de ATM, 150 lecturas de sucursal, 150 saldos diarios y 150 transacciones de subagentes. También crea estados para 25 ATM y cuatro alertas de bajo efectivo.

Para eliminar únicamente la muestra:

```powershell
psql -U kpi_user -d kpi_command_center -f sql\04_clear.sql
```

La limpieza completa requiere confirmación explícita. Consulta [sql/README.md](sql/README.md) antes de ejecutarla.

## API y documentación

Todas las rutas funcionales usan el prefijo `/api/v1`.

- [Mapa de endpoints por módulo](docs/dashboard-api.md)
- [Modelo relacional y definición de indicadores](docs/data-model.md)
- [Contrato OpenAPI exportado](docs/openapi.json)
- Swagger en `/docs` durante desarrollo

Las colecciones usan el formato `items`, `total`, `limit` y `offset`. Los endpoints analíticos aceptan filtros por provincia, región y periodo. El rango predeterminado son los últimos 30 días en `America/Santo_Domingo`.

## Estructura del proyecto

```text
app/
  api/v1/           Endpoints REST
  core/             Configuración y seguridad
  db/               Sesiones, seed e importadores
  models/           Entidades SQLAlchemy y enums
  services/         Métricas, filtros, jobs y sincronizadores
dashboard/          Aplicación web estática
scripts/scrapers/   Extracción BHD y Scotiabank
alembic/            Migraciones de base de datos
sql/                Instalación, funciones, sample y limpieza
tests/              Pruebas de API, métricas, jobs e importación
docs/               Contratos y documentación técnica
```

## Pruebas y calidad

Las pruebas requieren una base PostgreSQL separada cuyo nombre termine en `_test`.

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg2://usuario:password@localhost:5432/kpi_command_center_test'
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\alembic.exe check
```

Cada prueba revierte sus cambios. El proyecto rechaza una URL de pruebas cuyo nombre de base no termine en `_test`.

## Consideraciones de producción

- Configura `APP_ENV=production`.
- Usa secretos distintos para PostgreSQL, JWT y pgAdmin.
- Define `CORS_ORIGINS` y `TRUSTED_HOSTS` explícitos.
- Publica la API detrás de HTTPS y un proxy con límites de solicitudes.
- No ejecutes seeds ni datos de muestra en producción.
- Mantén las sincronizaciones externas bajo monitoreo y revisa sus fuentes.
- Swagger y OpenAPI públicos se deshabilitan automáticamente en producción.
