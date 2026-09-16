from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select

from app.db.base import utcnow
from app.models import ATM, Provincia, Sucursal

LOCAL_TZ = ZoneInfo("America/Santo_Domingo")


class Filters:
    def __init__(
        self,
        provincia: str | None = Query(None, max_length=100),
        region: str | None = Query(None, max_length=100),
        desde: date | None = None,
        hasta: date | None = None,
    ):
        self.provincia, self.region = provincia, region
        self.hasta = hasta or utcnow().astimezone(LOCAL_TZ).date()
        if (
            self.hasta < date(1900, 1, 1)
            or self.hasta > date(9999, 12, 30)
            or (desde and desde < date(1900, 1, 1))
        ):
            raise HTTPException(422, "Fechas fuera del rango soportado")
        self.desde = desde or (self.hasta - timedelta(days=29))
        if self.desde > self.hasta or (self.hasta - self.desde).days > 730:
            raise HTTPException(422, "Rango inválido: desde <= hasta, máximo 731 días")
        self.start = datetime.combine(self.desde, time.min, LOCAL_TZ).astimezone(UTC)
        self.end = datetime.combine(self.hasta + timedelta(days=1), time.min, LOCAL_TZ).astimezone(
            UTC
        )

    def scope(self, stmt, model):
        if self.provincia:
            stmt = stmt.where(model.provincia == self.provincia)
        if self.region:
            stmt = stmt.where(
                model.provincia.in_(select(Provincia.nombre).where(Provincia.region == self.region))
            )
        return stmt

    def provinces(self):
        stmt = select(Provincia)
        if self.provincia:
            stmt = stmt.where(Provincia.nombre == self.provincia)
        if self.region:
            stmt = stmt.where(Provincia.region == self.region)
        return stmt

    def atms(self, tipo=None):
        stmt = self.scope(select(ATM.id), ATM)
        return stmt.where(ATM.tipo == tipo) if tipo else stmt

    def branches(self):
        return self.scope(select(Sucursal.id), Sucursal)

    def period(self, stmt, column):
        return stmt.where(column >= self.start, column < self.end)

    def metadata(self):
        return {
            "desde": self.desde,
            "hasta": self.hasta,
            "provincia": self.provincia,
            "region": self.region,
            "zona_horaria": "America/Santo_Domingo",
            "moneda": "DOP",
            "generado_en": utcnow(),
        }


DashboardFilters = Annotated[Filters, Depends()]
