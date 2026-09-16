# KPI Command Center — Backend

API funcional y dashboard HTML/JS para las tres páginas de referencia en `images/`: operaciones ATM, sucursales y colas, y planificación geoespacial. Incluye **14 tablas PostgreSQL y 60 operaciones REST**, autenticación JWT, permisos por rol, migraciones y datos de demostración.

El dashboard está en `dashboard/` y se sirve desde FastAPI en `/dashboard/`. Los contratos también están disponibles en OpenAPI y en [el mapa de integración](docs/dashboard-api.md).

## Screenshots
![Page 1](images/page1.jpg)

![Page 2](images/page2.jpg)

![Page 3](images/page3.jpg)


## Stack

Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 síncrono con `psycopg2-binary`, PostgreSQL, Alembic, PyJWT y Bcrypt. La configuración usa `pydantic-settings` y `python-dotenv`.

Se conserva Bcrypt con coste 12 mediante `pwdlib[bcrypt]`, en lugar de Passlib, siguiendo la integración de librerías actuales descrita por [FastAPI](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/). Las contraseñas se validan contra su límite de 72 bytes UTF-8. Se probaron Python 3.13 y PostgreSQL 18.3; las versiones exactas están en `requirements.lock` y `requirements-dev.lock`.

## Inicio con Docker

Requiere Python para generar `.env` y Docker Compose con el motor encendido.

```powershell
python scripts/init_env.py
docker compose up --build -d
docker compose exec api python -m app.db.seed
```

El primer comando conserva cualquier `.env` existente. En instalaciones nuevas genera secretos aleatorios. Si el puerto PostgreSQL ya está ocupado, cambia `POSTGRES_PORT` en `.env`. Dentro de los contenedores la conexión usa `db:5432`. Deja `DATABASE_URL` sin definir al usar Compose para que no reemplace esos parámetros.

- Swagger: http://localhost:8000/docs
- Dashboard: http://localhost:8000/dashboard/
- OpenAPI: http://localhost:8000/openapi.json
- Estado: http://localhost:8000/health/ready
- Demo: **admin@bank.com / admin123**. El seed está bloqueado con `APP_ENV=production`.

Compose espera a PostgreSQL, aplica la migración con un servicio separado y arranca la API sin insertar datos demo automáticamente.

### pgAdmin opcional

```powershell
docker compose --profile tools up -d pgadmin
```

Abre http://localhost:5050 con las credenciales `PGADMIN_*` de `.env`. Registra el servidor con host `db`, puerto `5432` y credenciales `POSTGRES_*`.

## Inicio con Python y PostgreSQL local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe scripts/init_env.py
```

Configura `POSTGRES_*` en `.env` y crea previamente esa base en tu servidor PostgreSQL. Luego:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m app.db.seed
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```

En Linux/macOS usa `.venv/bin/` en lugar de `.venv\Scripts\`.

Abre http://localhost:8000/dashboard/ para el login y las tres páginas del tablero.
Configura `GOOGLE_MAPS_API_KEY` en `.env` para habilitar los mapas de Google Maps JS.
Sin esa variable, las tarjetas, tablas y gráficos cargan igual, y el panel del mapa muestra un aviso.

### Instancia aislada preparada durante el desarrollo

En este workspace se creó `.local/pgdata`, con PostgreSQL en `127.0.0.1:55432`, sin modificar el servicio PostgreSQL preexistente. El `.env` local apunta a esa instancia. Es una instancia de desarrollo con autenticación local `trust` y escucha únicamente en loopback; los datos y `.env` están excluidos del repositorio. La configuración de Docker usa autenticación con contraseña.

Para reiniciarla, desde la raíz del proyecto y con PostgreSQL 18 instalado:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D .local/pgdata -l .local/postgres.log -o '-h 127.0.0.1 -p 55432' start
```

Para detener **solo esta instancia**:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D .local/pgdata -m fast stop
```

## Autenticación y roles

`POST /api/v1/auth/login` recibe formulario OAuth2: `username` contiene el correo y `password` la contraseña. El resto de la API recibe `Authorization: Bearer <access_token>`.

```powershell
$login = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/login -Body @{username='admin@bank.com'; password='admin123'}
$headers = @{Authorization="Bearer $($login.access_token)"}
Invoke-RestMethod -Uri http://localhost:8000/api/v1/metrics/summary -Headers $headers
```

| Función | ADMIN | OPERATOR | ANALYST |
|---|---|---|---|
| Consultar inventario, métricas, mapas y competencia | Sí | Sí | Sí |
| Modificar red, incidencias, recargas y datos analíticos | Sí | Sí | No |
| Gestionar usuarios, provincias e instituciones | Sí | No | No |
| Consultar auditoría | Sí | No | No |
| Ver perfil, cambiar contraseña, cerrar sesiones propias | Sí | Sí | Sí |

Los tokens expiran a los 45 minutos por defecto. Se comprueban firma, algoritmo, emisor, audiencia, fechas, tipo y versión de sesión. El rol y la activación se consultan en PostgreSQL en cada solicitud. Cambiar contraseña, desactivar o cambiar el rol invalida los tokens anteriores. `POST /auth/logout` cierra **todas las sesiones** del usuario.

Tras 5 intentos fallidos, la cuenta se bloquea 15 minutos; el contador persiste en PostgreSQL. Las escrituras guardan auditoría en la misma transacción, sin contraseñas, hashes ni tokens. Los errores de validación tampoco devuelven esos valores.

Para crear el primer administrador sin datos demo:

```powershell
python -m app.db.create_admin --email admin@tu-banco.com --name 'Administrador'
```

Solicita la contraseña sin mostrarla. Las cuentas creadas por API y los cambios de contraseña requieren al menos 12 caracteres. En producción configura secretos, hosts y orígenes explícitos, usa HTTPS en el proxy de entrada y aplica límites de solicitudes en ese proxy. Swagger y OpenAPI públicos se deshabilitan con `APP_ENV=production`.

## Datos y API

- [Modelo relacional y decisiones](docs/data-model.md)
- [Widgets de las tres páginas → endpoints](docs/dashboard-api.md)
- [Contrato OpenAPI exportado](docs/openapi.json)

Las colecciones tienen `items`, `total`, `limit` (1–200) y `offset`. Las rutas están definidas sin barra final; FastAPI redirige la variante con barra. Los UUID inválidos y cuerpos incorrectos devuelven `422`; recursos ausentes, `404`; duplicados o transiciones incompatibles, `409`; token inválido, `401`; permisos insuficientes, `403`.

El seed es idempotente para la misma fecha y configuración; no sobrescribe contraseñas ni datos existentes. Incluye 32 provincias, 6 sucursales ficticias, 18 ATMs, 3 incidencias activas, 2 recargas, 30 días de lecturas horarias, saldos, 4 instituciones demo, 12 ubicaciones competidoras y 6 candidatas. Las coordenadas sitúan ejemplos en zonas urbanas dominicanas; no identifican oficinas o cajeros reales. Las cifras operativas, financieras y de competencia son sintéticas.

## Migraciones

```powershell
alembic upgrade head
alembic check
# Después de cambiar modelos:
alembic revision --autogenerate -m 'descripcion del cambio'
```

La migración inicial es explícita y está versionada en `alembic/versions/`. Incluye UUID, enums nativos, claves foráneas, índices, unicidad y restricciones. No se usa `create_all()` al iniciar la API. Revisa cada migración autogenerada antes de aplicarla; referencia: [Alembic autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html).

## Pruebas

Se ejecutan contra PostgreSQL real. Crea una base de pruebas independiente cuyo nombre termine en `_test`; `pytest` rechaza otro destino y nunca toma `.env` como destino implícito.

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg2://usuario:password@localhost:5432/kpi_command_center_test'
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

En la instancia aislada de este workspace se puede usar `postgresql+psycopg2://kpi_test@127.0.0.1:55432/kpi_command_center_test`. Cada prueba revierte sus cambios mediante una transacción exterior y savepoints.

Validación realizada: **46 pruebas aprobadas**, migración de ida/vuelta y `alembic check`, análisis/formato Ruff, coherencia de dependencias y todos los GET de colecciones/métricas contra el seed. La configuración Compose fue validada; el motor Docker no estaba encendido, por lo que la ejecución se comprobó con PostgreSQL nativo. Hay dos avisos de deprecación de dependencias del cliente de pruebas, sin fallos.

GitHub Actions repite pruebas y migraciones con PostgreSQL 18. Para actualizar los locks tras resolver nuevas versiones: `python scripts/lock_dependencies.py`.
