"""Contratos de las tarjetas, series, tablas y mapas del dashboard."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generic, Literal
from uuid import UUID

from app.schemas import ATMOut, BranchOut, CandidateOut, Page, Schema, T


class WithMeta(Schema):
    meta: dict[str, Any]


class Series(WithMeta, Generic[T]):
    items: list[T]


class DashboardPage(Page[T], WithMeta, Generic[T]):
    pass


class ATMSummary(WithMeta):
    total_atms: int
    atms_operando: int
    atms_fuera_servicio: int
    atms_mantenimiento: int
    por_estado: dict[str, int]
    disponibilidad_actual_pct: float | None
    uptime_pct: float | None
    incidencias_criticas_abiertas: int
    alertas_bajo_efectivo: int
    atms_sin_comunicacion_reciente: int
    total_transacciones: int
    transacciones_exitosas: int
    monto_retirado: Decimal
    utilizacion_pct: float | None
    lecturas: int
    cobertura_provincias_pct: float | None
    provincias_cubiertas: int
    provincias_catalogadas: int


class ATMTrend(Schema):
    periodo: str
    transacciones: int
    monto_retirado: Decimal
    uptime_pct: float | None
    utilizacion_pct: float | None
    lecturas: int


class ATMStatusRow(ATMOut):
    uptime_pct: float | None
    utilizacion_pct: float | None
    transacciones: int
    lecturas: int
    efectivo_estimado: Decimal


class CashTrend(Schema):
    periodo: str
    provincia: str
    efectivo_promedio_pct: float
    monto_retirado: Decimal
    consumo_capacidad_por_hora_pct: float | None
    lecturas: int


class Density(Schema):
    provincia: str
    region: str
    atms: int
    sucursales: int
    poblacion: int | None
    atms_por_100000_habitantes: float | None
    sucursales_por_100000_habitantes: float | None
    fuente_demografia: str | None


class BranchSummary(WithMeta):
    total_sucursales: int
    espera_promedio_minutos: float | None
    cumplimiento_sla_pct: float | None
    utilizacion_cajeros_pct: float | None
    total_visitantes: int
    clientes_atendidos: int
    lecturas: int


class BranchTrend(Schema):
    periodo: str
    visitantes: int
    espera_promedio_minutos: float | None
    cumplimiento_sla_pct: float | None


class HourlyTraffic(Schema):
    hora: int
    visitantes: int
    lecturas: int


class BranchStatusRow(BranchOut):
    hora_lectura: datetime | None
    cajeros_disponibles: int | None
    cola_actual: int | None
    lectura_en_periodo: bool
    lectura_desactualizada: bool


class PlanningSummary(WithMeta):
    total_sucursales: int
    cobertura_provincias_pct: float | None
    provincias_cubiertas: int
    provincias_catalogadas: int
    total_depositos: Decimal | None
    total_prestamos: Decimal | None
    sucursales_con_saldos: int
    fecha_saldo_min: date | None
    fecha_saldo_max: date | None
    total_sucursales_mercado: int
    cuota_sucursales_pct: float | None


class Comparison(Schema):
    institucion_id: UUID
    nombre: str
    es_propia: bool
    color: str
    fecha_corte: date | None
    total_atms: int | None
    total_sucursales: int | None
    depositos: Decimal | None
    prestamos: Decimal | None
    transacciones: int | None
    utilizacion_pct: float | None
    cuota_sucursales_pct: float | None
    provincias_reportadas: int
    fuentes: list[str]


class CandidateRow(CandidateOut):
    competidores_cercanos: int
    distancia_red_propia_km: float | None


class Point(Schema):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class Feature(Schema):
    type: Literal["Feature"] = "Feature"
    id: UUID
    geometry: Point
    properties: dict[str, Any]


class FeatureCollection(Schema):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    meta: dict[str, Any] = {}
    total: int
    limit: int
    offset: int
    features: list[Feature]
