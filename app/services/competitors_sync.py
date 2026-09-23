from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.models import CompetitorLocation, Institution, Provincia
from app.models.enums import LocationType
from app.services.location_import import optional_text, parse_float, resolve_province

SCOTIABANK_NAME = "Scotiabank"
SCOTIABANK_COLOR = "#EC111A"
SCOTIABANK_SOURCE = "scotiabank_official"

ProgressCallback = Callable[[int, int | None, str], None]


@dataclass
class CompetitorSyncSummary:
    downloaded: int = 0
    institution_id: UUID | None = None
    inserted: Counter[str] = field(default_factory=Counter)
    updated: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "downloaded": self.downloaded,
            "institution_id": str(self.institution_id) if self.institution_id else None,
            "inserted": dict(self.inserted),
            "updated": dict(self.updated),
            "skipped": dict(self.skipped),
            "errors": list(self.errors),
        }


def read_competitor_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def fetch_scotiabank_branches(
    *,
    geocode: bool = True,
    refresh_cache: bool = False,
    headed: bool = False,
    browser: str = "auto",
    timeout_ms: int = 20_000,
    checkpoint_file: Path | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the existing Scotia scraper and return only official branch rows."""
    from scripts.scrapers import scotia_sucursales as scraper

    if progress:
        progress(0, None, "Descargando sucursales oficiales de Scotiabank")

    session = requests.Session()
    session.headers.update(scraper.HEADERS)
    try:
        soup = scraper.get_scotiabank_page(session)
    finally:
        session.close()

    branches = scraper.extract_branch_tables(soup)
    if not branches:
        raise RuntimeError(
            "Scotiabank no devolvió sucursales; la estructura de la página puede haber cambiado"
        )

    if checkpoint_file is not None:
        scraper.export_csv(branches, checkpoint_file, announce=False)

    if geocode:
        cache = {} if refresh_cache else scraper.load_cache()
        scraper.geocode_branches_with_google_maps(
            branches=branches,
            cache=cache,
            headed=headed,
            browser_choice=browser,
            timeout_ms=max(5_000, timeout_ms),
            checkpoint_file=checkpoint_file,
        )

    with_coordinates = sum(
        row.get("latitude") is not None and row.get("longitude") is not None for row in branches
    )
    metadata = {
        "bank": SCOTIABANK_NAME,
        "location_type": "branch",
        "source": SCOTIABANK_SOURCE,
        "source_url": scraper.SCOTIABANK_URL,
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "downloaded": len(branches),
        "with_coordinates": with_coordinates,
        "without_coordinates": len(branches) - with_coordinates,
    }
    if progress:
        progress(len(branches), len(branches), "Sucursales Scotiabank extraídas")
    return branches, metadata


def _scotiabank_institution(db: Session) -> Institution:
    institution = db.scalar(
        select(Institution).where(func.lower(Institution.nombre) == SCOTIABANK_NAME.lower())
    )
    if institution:
        if institution.es_propia:
            raise RuntimeError("Scotiabank está registrada como institución propia")
        return institution

    institution = Institution(
        nombre=SCOTIABANK_NAME,
        es_propia=False,
        color=SCOTIABANK_COLOR,
    )
    db.add(institution)
    db.flush()
    return institution


def import_scotiabank_branches(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    verified_at: datetime | None = None,
) -> CompetitorSyncSummary:
    """Upsert only Scotiabank branches into competitor_locations."""
    summary = CompetitorSyncSummary(downloaded=len(rows))
    institution = _scotiabank_institution(db)
    summary.institution_id = institution.id
    available_provinces = set(db.scalars(select(Provincia.nombre)))
    verification_date = (verified_at or datetime.now(UTC)).date()

    for index, row in enumerate(rows, start=1):
        location_type = optional_text(row.get("location_type"))
        if not location_type or location_type.lower() != "branch":
            summary.skipped["unsupported_location_type"] += 1
            continue

        source_id = optional_text(row.get("record_id"))
        name = optional_text(row.get("name"))
        lat = parse_float(row.get("latitude"))
        lon = parse_float(row.get("longitude"))
        if not source_id or not name:
            summary.skipped["invalid_identity"] += 1
            summary.errors.append(f"Fila {index}: faltan record_id/name")
            continue
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            summary.skipped["without_coordinates"] += 1
            summary.errors.append(f"Fila {index} ({source_id}): sucursal sin coordenadas válidas")
            continue

        # Scotia addresses frequently contain province names as street names
        # (for example, "C/ Santiago" in Distrito Nacional). Prefer an explicit
        # province or a place contained in the branch name, then fall back to
        # the verified coordinates instead of inferring from the street.
        province_row = {**row, "address": ""}
        province = resolve_province(province_row, lat, lon, available_provinces)
        if not province:
            summary.skipped["without_province"] += 1
            summary.errors.append(f"Fila {index} ({source_id}): no se pudo resolver provincia")
            continue

        code = f"SCOTIA-BR-{source_id}"[:80]
        values = {
            "nombre": name,
            "provincia": province,
            "tipo": LocationType.SUCURSAL,
            "latitud": lat,
            "longitud": lon,
            "fuente": optional_text(row.get("source_url")) or SCOTIABANK_SOURCE,
            "fecha_verificacion": verification_date,
        }
        existing = db.scalar(
            select(CompetitorLocation).where(
                CompetitorLocation.institucion_id == institution.id,
                CompetitorLocation.codigo == code,
            )
        )
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
            summary.updated["branches"] += 1
        else:
            db.add(
                CompetitorLocation(
                    institucion_id=institution.id,
                    codigo=code,
                    **values,
                )
            )
            summary.inserted["branches"] += 1

    db.flush()
    return summary


def sync_scotiabank_branches(
    db: Session,
    *,
    input_file: Path | None = None,
    geocode: bool = True,
    refresh_cache: bool = False,
    headed: bool = False,
    browser: str = "auto",
    timeout_ms: int = 20_000,
    checkpoint_file: Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    if input_file is not None:
        rows = read_competitor_csv(input_file)
        extraction = {
            "bank": SCOTIABANK_NAME,
            "location_type": "branch",
            "source": str(input_file),
            "downloaded": len(rows),
        }
    else:
        rows, extraction = fetch_scotiabank_branches(
            geocode=geocode,
            refresh_cache=refresh_cache,
            headed=headed,
            browser=browser,
            timeout_ms=timeout_ms,
            checkpoint_file=checkpoint_file,
            progress=progress,
        )
    load = import_scotiabank_branches(db, rows)
    return {"extraction": extraction, "load": load.to_dict()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza sucursales Scotiabank competidoras")
    parser.add_argument("--input", type=Path, help="CSV ya generado por scotia_sucursales.py")
    parser.add_argument("--no-geocode", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--browser", choices=("auto", "chrome", "msedge", "chromium"), default="auto"
    )
    parser.add_argument("--timeout", type=int, default=20_000)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with get_session_factory()() as db:
        result = sync_scotiabank_branches(
            db,
            input_file=args.input,
            geocode=not args.no_geocode,
            refresh_cache=args.refresh_cache,
            headed=args.headed,
            browser=args.browser,
            timeout_ms=args.timeout,
            checkpoint_file=args.checkpoint,
        )
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
