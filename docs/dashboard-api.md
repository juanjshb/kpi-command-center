# Integración de las tres páginas

Todos los paths siguientes llevan el prefijo `/api/v1` y requieren Bearer JWT. OpenAPI expone los modelos de respuesta, enums y validaciones para generar un cliente tipado.

## Filtros comunes

Carga `GET /catalogs/filters` para obtener provincias, regiones, tipos y estados.

Los endpoints analíticos admiten `provincia`, `region`, `desde=YYYY-MM-DD` y `hasta=YYYY-MM-DD`. Las fechas son inclusivas en `America/Santo_Domingo`; por defecto son los últimos 30 días incluyendo hoy. El rango máximo es 731 días. Se puede filtrar por `tipo=DISPENSADOR|CDM_DEPOSITO` en métricas ATM. Sucursales y planificación tienen su propio ámbito; el tipo ATM no filtra esos indicadores.

Los conteos de inventario, estados y alertas son **actuales**, aunque se seleccione otro periodo para las series. Los saldos se toman hasta `hasta`. La respuesta indica el ámbito temporal en los metadatos. No interpretes un inventario actual como un inventario reconstruido de años anteriores.

### Página 1 — Operaciones ATM

| Widget de `images/page1.jpg` | Endpoint |
|---|---|
| Total ATMs, cobertura, transacciones y utilización | `GET /metrics/summary` |
| Disponibilidad, uptime, bajo efectivo, mantenimiento, falta de comunicación | `GET /metrics/summary` |
| Mapa de cajeros | `GET /geo/locations?capa=atms` |
| Evolución de transacciones y uptime | `GET /metrics/atm-trends?agrupacion=month` |
| Evolución del efectivo y retiros por provincia | `GET /metrics/cash-trends` |
| Densidad por provincia/región | `GET /metrics/network-density` (sumar por `region` si se desea esa vista) |
| Tabla individual: efectivo, uptime y último mantenimiento | `GET /metrics/atms/status` |
| Búsqueda por código/nombre y filtros de estado | `GET /atms?search=ATM&estado=OPERATIVO` |
| Matriz comparativa | `GET /competitors/comparison` |
| Incidencias activas por prioridad | `GET /incidents` |
| Órdenes CIT | `GET /logistics?estado=PROGRAMADA` |

`efectivo_estimado` es capacidad × porcentaje registrado. `consumo_capacidad_por_hora_pct` es retiro agregado / capacidad acumulada de las lecturas horarias; no es una predicción de agotamiento. Para sparklines usa las series. Para variaciones entre periodos consulta ambos rangos; sin base histórica suficiente muestra “sin datos”, sin fijar valores YoY de las imágenes.

### Página 2 — Sucursales y colas

| Widget de `images/page2.jpg` | Endpoint |
|---|---|
| Espera media, SLA, utilización y visitantes | `GET /metrics/branches/summary` |
| Mapa y calor según cola | `GET /geo/locations?capa=sucursales` |
| SLA y espera a lo largo del tiempo | `GET /metrics/branches/trends?agrupacion=month` |
| Visitantes por hora local | `GET /metrics/branches/hourly-traffic` |
| Estado de oficinas, cajeros disponibles y cola | `GET /metrics/branches/status` |
| Detalle y ATMs de una oficina | `GET /branches/{id}` y `GET /branches/{id}/atms` |

La tabla de sucursales incluye fecha de la última lectura hasta el corte, si pertenece al periodo y si está desactualizada. `total_visitantes` es el acumulado del rango; para una tarjeta de visitantes de una hora concreta usa la serie correspondiente. No se presenta el acumulado mensual como tráfico en tiempo real.

### Página 3 — Planificación y geoespacial

| Widget de `images/page3.jpg` | Endpoint |
|---|---|
| Sucursales, cobertura, cuota de muestra, depósitos | `GET /metrics/planning/summary` |
| Mapa propio/competencia/candidatas | `GET /geo/locations?capa=todas` |
| Distribución de sucursales | `GET /metrics/network-density` |
| Ranking, densidad y competidores cercanos | `GET /planning/candidates?radio_km=5` |
| Detalles de una candidata | `GET /planning/candidates/{id}` |
| Comparación por entidad | `GET /competitors/comparison` |

## GeoJSON y mapa

`GET /geo/locations` devuelve `FeatureCollection` con `features`, `total`, `limit` y `offset`. Pagina hasta reunir `total` elementos si el mapa necesita la red completa.

- `capa`: `atms`, `sucursales`, `competencia`, `candidatos` o `todas`.
- `tipo`: `ATM` o `SUCURSAL`.
- `tipo_atm`: `DISPENSADOR` o `CDM_DEPOSITO`; aplicado exclusivamente a la capa ATM propia.
- `bbox`: `oeste,sur,este,norte`, por ejemplo `-71.9,17.4,-68.2,20.1`.
- Coordenadas GeoJSON: **[longitud, latitud]**.
- `properties`: capa, código, nombre, provincia, tipo, estado e intensidad.
- Intensidad: `100 - efectivo%` para ATMs; cola última conocida para sucursales; puntuación de candidatas; 1 para competencia. Usa escalas de calor independientes.

El frontend puede consumir estos puntos con MapLibre/Leaflet/Mapbox. El backend no incluye teselas ni polígonos provinciales: esas capas cartográficas deben provenir del proveedor elegido. Los puntos y sus métricas están listos para esas capas.

## Operaciones e ingestión

| Recurso | Operaciones |
|---|---|
| Auth | `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`, `POST /auth/change-password` |
| Usuarios | `GET, POST /users`; `PATCH /users/{id}` |
| Provincias | `GET, POST /catalogs/provinces`; `GET /catalogs/filters` |
| ATMs | `GET, POST /atms`; `GET /atms/{id}`; `PATCH /atms/{id}/status`; `POST /atms/{id}/heartbeat` |
| Telemetría ATM | `GET, POST /atms/{id}/readings` |
| Sucursales | `GET, POST /branches`; `GET, PATCH /branches/{id}`; `GET /branches/{id}/atms` |
| Colas y SLA | `GET, POST /branches/{id}/readings` |
| Saldos propios | `GET, POST /branches/{id}/financials` |
| Incidencias | `GET, POST /incidents`; `GET /incidents/{id}`; `PATCH /incidents/{id}/assign`; `PATCH /incidents/{id}/close` |
| CIT | `GET, POST /logistics`; `GET /logistics/{id}`; `PATCH /logistics/{id}/status` |
| Instituciones | `GET, POST /competitors/institutions` |
| Puntos competidores | `GET, POST /competitors/locations` |
| Cortes comparativos | `GET, POST /competitors/snapshots` |
| Candidatas | `GET, POST /planning/candidates`; `GET, PATCH /planning/candidates/{id}` |
| Auditoría | `GET /audit-logs?entidad=atms&entidad_id=<uuid>` |

### Ejemplo de telemetría ATM

`POST /atms/{id}/readings`:

```json
{
  "hora": "2026-01-15T09:00:00-04:00",
  "transacciones": 100,
  "transacciones_exitosas": 98,
  "monto_retirado": "245000.00",
  "nivel_efectivo_pct": 62.5,
  "segundos_observados": 3600,
  "segundos_disponible": 3540,
  "segundos_utilizado": 1800
}
```

Los importes monetarios se exponen como strings decimales para evitar pérdida de precisión en clientes JavaScript. Las lecturas duplicadas se rechazan con `409`, permitiendo detectar reintentos de una integración. Las cifras no se conectan automáticamente a un banco: los conectores operativos deben enviar heartbeats, lecturas y cortes a estos endpoints.

## Actualización y consistencia

Se puede refrescar el inventario/métricas mediante polling desde el frontend. La API no promete push/WebSocket ni integraciones de monitoreo ya instaladas. Cada actualización operativa se confirma en PostgreSQL junto con su auditoría; la finalización CIT usa bloqueo de filas para impedir ejecuciones simultáneas.
