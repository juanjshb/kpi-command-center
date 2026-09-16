from fastapi import APIRouter

from app.api.v1 import (
    atms,
    auth,
    branches,
    catalogs,
    competitors,
    geo,
    incidents,
    logistics,
    metrics,
    planning,
    users,
)

router = APIRouter(prefix="/api/v1")
for module in (
    auth,
    users,
    catalogs,
    atms,
    branches,
    incidents,
    logistics,
    metrics,
    competitors,
    planning,
    geo,
):
    router.include_router(module.router)
