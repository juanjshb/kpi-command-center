from typing import Literal

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser, Paging
from app.dashboard_schemas import (
    ATMStatusRow,
    ATMSummary,
    ATMTrend,
    BranchStatusRow,
    BranchSummary,
    BranchTrend,
    CashTrend,
    DashboardPage,
    Density,
    HourlyTraffic,
    PlanningSummary,
    Series,
)
from app.models.enums import ATMType
from app.services import metrics
from app.services.filters import DashboardFilters

router = APIRouter(prefix="/metrics", tags=["Métricas dashboard"])


@router.get("/summary", response_model=ATMSummary)
def summary(db: DB, user: CurrentUser, filters: DashboardFilters, tipo: ATMType | None = None):
    return {
        "meta": {**filters.metadata(), "tipo": tipo, "estado_red": "actual"},
        **metrics.atm_totals(db, filters, tipo),
    }


@router.get("/atm-trends", response_model=Series[ATMTrend])
def atm_trends(
    db: DB,
    user: CurrentUser,
    filters: DashboardFilters,
    tipo: ATMType | None = None,
    agrupacion: Literal["day", "month"] = "day",
):
    return {"meta": filters.metadata(), "items": metrics.atm_trend(db, filters, tipo, agrupacion)}


@router.get("/atms/status", response_model=DashboardPage[ATMStatusRow])
def atm_status(
    db: DB,
    user: CurrentUser,
    filters: DashboardFilters,
    paging: Paging,
    tipo: ATMType | None = None,
):
    return {"meta": filters.metadata(), **metrics.atm_status(db, filters, paging, tipo)}


@router.get("/cash-trends", response_model=Series[CashTrend])
def cash_trends(db: DB, user: CurrentUser, filters: DashboardFilters, tipo: ATMType | None = None):
    return {"meta": filters.metadata(), "items": metrics.cash_trend(db, filters, tipo)}


@router.get("/network-density", response_model=Series[Density])
def density(db: DB, user: CurrentUser, filters: DashboardFilters, tipo: ATMType | None = None):
    return {
        "meta": {**filters.metadata(), "inventario": "actual"},
        "items": metrics.density(db, filters, tipo),
    }


@router.get("/branches/summary", response_model=BranchSummary)
def branches_summary(db: DB, user: CurrentUser, filters: DashboardFilters):
    return {"meta": filters.metadata(), **metrics.branch_summary(db, filters)}


@router.get("/branches/trends", response_model=Series[BranchTrend])
def branches_trends(
    db: DB,
    user: CurrentUser,
    filters: DashboardFilters,
    agrupacion: Literal["day", "month"] = "day",
):
    return {"meta": filters.metadata(), "items": metrics.branch_trend(db, filters, agrupacion)}


@router.get("/branches/hourly-traffic", response_model=Series[HourlyTraffic])
def hourly_traffic(db: DB, user: CurrentUser, filters: DashboardFilters):
    return {"meta": filters.metadata(), "items": metrics.hourly_traffic(db, filters)}


@router.get("/branches/status", response_model=DashboardPage[BranchStatusRow])
def branch_status(db: DB, user: CurrentUser, filters: DashboardFilters, paging: Paging):
    return {"meta": filters.metadata(), **metrics.branch_status(db, filters, paging)}


@router.get("/planning/summary", response_model=PlanningSummary)
def planning_summary(db: DB, user: CurrentUser, filters: DashboardFilters):
    return {"meta": filters.metadata(), **metrics.planning_summary(db, filters)}
