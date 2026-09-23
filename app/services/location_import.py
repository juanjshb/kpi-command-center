from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ATM, Institution, Provincia, Subagente, Sucursal
from app.models.enums import ATMStatus, ATMType, BranchStatus

BHD_SOURCE = "bhd_public_locations_api"
MAIN_BANK_NAME = "BHD Leon"
MAIN_BANK_COLOR = "#35C83E"

# Capitales/cabeceras provinciales. Son una aproximacion local y reproducible para
# completar el catalogo provincial porque el API de BHD solo entrega coordenadas.
PROVINCE_CENTERS: dict[str, tuple[float, float]] = {
    "Distrito Nacional": (18.4861, -69.9312),
    "Santo Domingo": (18.4885, -69.8571),
    "Santiago": (19.4517, -70.6970),
    "La Vega": (19.2221, -70.5297),
    "Puerto Plata": (19.7934, -70.6884),
    "Espaillat": (19.3935, -70.5260),
    "Duarte": (19.3010, -70.2526),
    "Hermanas Mirabal": (19.3776, -70.4176),
    "María Trinidad Sánchez": (19.3832, -69.8474),
    "Samaná": (19.2056, -69.3369),
    "Sánchez Ramírez": (19.0527, -70.1490),
    "Monseñor Nouel": (18.9360, -70.4090),
    "Valverde": (19.5519, -71.0781),
    "Monte Cristi": (19.8483, -71.6459),
    "Dajabón": (19.5480, -71.7080),
    "Santiago Rodríguez": (19.4710, -71.3410),
    "San Cristóbal": (18.4167, -70.1060),
    "Peravia": (18.2796, -70.3310),
    "San José de Ocoa": (18.5466, -70.5063),
    "Azua": (18.4532, -70.7349),
    "San Juan": (18.8059, -71.2299),
    "Elías Piña": (18.8760, -71.7030),
    "Barahona": (18.2085, -71.1008),
    "Baoruco": (18.4814, -71.4197),
    "Independencia": (18.4917, -71.8502),
    "Pedernales": (18.0375, -71.7440),
    "La Altagracia": (18.6150, -68.7070),
    "La Romana": (18.4273, -68.9728),
    "El Seibo": (18.7658, -69.0389),
    "Hato Mayor": (18.7628, -69.2568),
    "San Pedro de Macorís": (18.4539, -69.3086),
    "Monte Plata": (18.8070, -69.7830),
}

PROVINCE_ALIASES: dict[str, tuple[str, ...]] = {
    "Distrito Nacional": ("distrito nacional", "d.n.", " d n "),
    "Santo Domingo": (
        "santo domingo este",
        "santo domingo oeste",
        "santo domingo norte",
        "villa mella",
        "boca chica",
        "los alcarrizos",
        "pedro brand",
    ),
    "Santiago": ("santiago de los caballeros", "santiago", "stgo"),
    "La Vega": ("la vega", "jarabacoa", "constanza"),
    "Puerto Plata": ("puerto plata", "sosua", "cabarete"),
    "Espaillat": ("espaillat", "moca"),
    "Duarte": ("san francisco de macoris", "provincia duarte"),
    "Hermanas Mirabal": ("hermanas mirabal", "salcedo"),
    "María Trinidad Sánchez": ("maria trinidad sanchez", "nagua", "cabrera"),
    "Samaná": ("samana", "las terrenas"),
    "Sánchez Ramírez": ("sanchez ramirez", "cotui"),
    "Monseñor Nouel": ("monsenor nouel", "bonao"),
    "Valverde": ("valverde", "mao"),
    "Monte Cristi": ("monte cristi", "montecristi", "castanuela"),
    "Dajabón": ("dajabon",),
    "Santiago Rodríguez": ("santiago rodriguez", "sabaneta"),
    "San Cristóbal": ("san cristobal", "haina"),
    "Peravia": ("peravia", "bani"),
    "San José de Ocoa": ("san jose de ocoa", "ocoa"),
    "Azua": ("azua",),
    "San Juan": ("san juan de la maguana", "provincia san juan"),
    "Elías Piña": ("elias pina", "comendador"),
    "Barahona": ("barahona",),
    "Baoruco": ("baoruco", "bahoruco", "neyba", "neiba"),
    "Independencia": ("provincia independencia", "jimani"),
    "Pedernales": ("pedernales",),
    "La Altagracia": ("la altagracia", "higuey", "punta cana", "bavaro"),
    "La Romana": ("la romana",),
    "El Seibo": ("el seibo", "miches"),
    "Hato Mayor": ("hato mayor", "sabana de la mar"),
    "San Pedro de Macorís": ("san pedro de macoris",),
    "Monte Plata": ("monte plata", "bayaguana", "yamasa"),
}


@dataclass
class ImportSummary:
    downloaded: int = 0
    inserted: Counter[str] = field(default_factory=Counter)
    updated: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "downloaded": self.downloaded,
            "inserted": dict(self.inserted),
            "updated": dict(self.updated),
            "skipped": dict(self.skipped),
            "errors": list(self.errors),
        }


def ensure_main_bank_institution(db: Session) -> Institution:
    institution = db.scalar(select(Institution).where(Institution.es_propia.is_(True)))
    if institution:
        return institution

    institution = db.scalar(
        select(Institution).where(func.lower(Institution.nombre) == MAIN_BANK_NAME.lower())
    )
    if institution:
        institution.es_propia = True
        institution.color = MAIN_BANK_COLOR
    else:
        institution = Institution(
            nombre=MAIN_BANK_NAME,
            es_propia=True,
            color=MAIN_BANK_COLOR,
        )
        db.add(institution)
    db.flush()
    return institution


def normalize_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def optional_text(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or None


def parse_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = normalize_text(value)
    if normalized in {"true", "1", "si", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def parse_json(value: Any) -> Any | None:
    if value in (None, ""):
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    text = optional_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def nearest_province(lat: float, lon: float, available: set[str]) -> str | None:
    candidates = {
        province: coordinates
        for province, coordinates in PROVINCE_CENTERS.items()
        if province in available
    }
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda province: (
            (lat - candidates[province][0]) ** 2
            + ((lon - candidates[province][1]) * math.cos(math.radians(lat))) ** 2
        ),
    )


def resolve_province(
    row: dict[str, Any], lat: float | None, lon: float | None, available: set[str]
) -> str | None:
    supplied = optional_text(row.get("province"))
    if supplied in available:
        return supplied

    haystack = f" {normalize_text(row.get('name'))} {normalize_text(row.get('address'))} "
    aliases = sorted(
        (
            (normalize_text(alias), province)
            for province, values in PROVINCE_ALIASES.items()
            if province in available
            for alias in values
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for alias, province in aliases:
        if f" {alias} " in haystack:
            return province
    if lat is not None and lon is not None:
        return nearest_province(lat, lon, available)
    return None


def location_type(row: dict[str, Any]) -> str:
    explicit = normalize_text(row.get("location_type"))
    category = normalize_text(row.get("category"))
    value = f"{explicit} {category}"
    if "subagent" in value or "subagente" in value:
        return "subagentes"
    if "atm" in value or "cajero" in value:
        return "atms"
    if "branch" in value or "sucursal" in value or "oficina" in value:
        return "sucursales"
    return "desconocidos"


def _find_existing(
    db: Session,
    model: type[Sucursal] | type[ATM] | type[Subagente],
    source_id: str,
    name: str,
    lat: float | None,
    lon: float | None,
) -> Sucursal | ATM | Subagente | None:
    existing = db.scalar(
        select(model).where(model.fuente == BHD_SOURCE, model.fuente_id == source_id)
    )
    if existing or lat is None or lon is None:
        return existing
    # Permite adoptar inventario BHD previamente cargado sin metadatos de origen.
    return db.scalars(
        select(model)
        .where(
            model.fuente.is_(None),
            func.lower(model.nombre) == name.lower(),
            func.abs(model.latitud - lat) < 0.00001,
            func.abs(model.longitud - lon) < 0.00001,
        )
        .limit(1)
    ).first()


def import_bhd_rows(db: Session, rows: list[dict[str, Any]]) -> ImportSummary:
    summary = ImportSummary(downloaded=len(rows))
    ensure_main_bank_institution(db)
    available_provinces = set(db.scalars(select(Provincia.nombre)))

    for index, row in enumerate(rows, start=1):
        kind = location_type(row)
        if kind == "desconocidos":
            summary.skipped[kind] += 1
            continue

        name = optional_text(row.get("name"))
        address = optional_text(row.get("address")) or "Dirección no publicada por BHD"
        source_id = optional_text(row.get("api_id")) or optional_text(row.get("record_id"))
        if not name or not source_id:
            summary.skipped[kind] += 1
            summary.errors.append(f"Fila {index}: faltan name/api_id")
            continue
        if "\ufffd" in name or "\ufffd" in address:
            summary.skipped[kind] += 1
            summary.errors.append(f"Fila {index} ({source_id}): texto con codificación inválida")
            continue

        lat = parse_float(row.get("latitude"))
        lon = parse_float(row.get("longitude"))
        if (lat is None) != (lon is None) or (
            lat is not None and lon is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180)
        ):
            summary.skipped[kind] += 1
            summary.errors.append(f"Fila {index} ({source_id}): coordenadas inválidas")
            continue
        if kind in {"sucursales", "atms"} and (lat is None or lon is None):
            summary.skipped[kind] += 1
            summary.errors.append(f"Fila {index} ({source_id}): ubicación sin coordenadas")
            continue

        province = resolve_province(row, lat, lon, available_provinces)
        if kind in {"sucursales", "atms"} and not province:
            summary.skipped[kind] += 1
            summary.errors.append(f"Fila {index} ({source_id}): no se pudo resolver provincia")
            continue
        municipality = optional_text(row.get("municipality")) or province
        services = (
            "\n".join(
                filter(
                    None,
                    (
                        optional_text(row.get("actions_performed")),
                        optional_text(row.get("special_instructions")),
                    ),
                )
            )
            or None
        )
        common = {
            "nombre": name,
            "provincia": province,
            "municipio": municipality,
            "direccion": address,
            "latitud": lat,
            "longitud": lon,
            "fuente": BHD_SOURCE,
            "fuente_id": source_id,
            "telefono": optional_text(row.get("phone")),
            "zona": optional_text(row.get("zone")),
            "horario_extendido": parse_bool(row.get("extended_hours")),
            "servicios": services,
            "horario": parse_json(row.get("weekday_schedule_json")),
            "actualizado_fuente_en": parse_datetime(
                row.get("updated_at_source") or row.get("published_at_source")
            ),
        }

        if kind == "sucursales":
            model = Sucursal
            create_values = {
                "codigo": f"BHD-BR-{source_id}"[:40],
                "estado": BranchStatus.SIN_DATOS,
                "total_cajeros_humanos": 0,
                "sla_objetivo_segundos": 600,
            }
        elif kind == "atms":
            model = ATM
            create_values = {
                "codigo_unico": f"BHD-ATM-{source_id}"[:40],
                "tipo": ATMType.DISPENSADOR,
                "nivel_efectivo_pct": 0,
                "capacidad_efectivo": Decimal("1.00"),
                "estado": ATMStatus.SIN_DATOS,
            }
        else:
            model = Subagente
            create_values = {
                "codigo_unico": f"BHD-SA-{source_id}"[:40],
                "activo": True,
            }

        existing = _find_existing(db, model, source_id, name, lat, lon)
        if existing:
            for key, value in common.items():
                setattr(existing, key, value)
            summary.updated[kind] += 1
        else:
            db.add(model(**common, **create_values))
            summary.inserted[kind] += 1

    db.flush()
    return summary


def read_bhd_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def import_bhd_csv(db: Session, path: Path) -> ImportSummary:
    return import_bhd_rows(db, read_bhd_csv(path))
