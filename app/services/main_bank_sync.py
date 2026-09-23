from __future__ import annotations

import hashlib
import json
import math
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BHD_API_URL = "https://backend.bhd.com.do/api/locations"
BHD_PAGE_SIZE = 100
BHD_TIMEOUT = 30
BHD_MAX_PAGES = 100
DR_BOUNDS = (17.3, 20.2, -72.2, -68.0)

ProgressCallback = Callable[[int, int | None, str], None]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def make_id(*values: Any) -> str:
    raw = "|".join(clean_text(value) for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def to_float(value: Any) -> float | None:
    try:
        result = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def get_attributes(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes")
    return attributes if isinstance(attributes, dict) else item


def infer_location_type(category: Any, name: Any) -> str:
    combined = f"{normalize_text(category)} {normalize_text(name)}"
    if "subagente" in combined:
        return "subagent"
    if "cajero" in combined or re.search(r"\batm\b", combined):
        return "atm"
    if "sucursal" in combined or "oficina" in combined:
        return "branch"
    return "location"


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Accept-Language": "es-DO,es;q=0.9",
        }
    )
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


def request_page(session: requests.Session, page: int) -> tuple[dict[str, Any], str]:
    response = session.get(
        BHD_API_URL,
        params={
            "populate": "deep",
            "pagination[pageSize]": BHD_PAGE_SIZE,
            "pagination[page]": page,
        },
        timeout=BHD_TIMEOUT,
    )
    response.raise_for_status()
    try:
        payload = json.loads(response.content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"BHD devolvió JSON inválido en la página {page}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data", []), list):
        raise RuntimeError(f"Estructura inesperada del API BHD en la página {page}")
    return payload, response.url


def item_to_row(item: dict[str, Any], source_url: str) -> dict[str, Any] | None:
    attributes = get_attributes(item)
    api_id = clean_text(item.get("id") or attributes.get("id"))
    name = clean_text(attributes.get("name"))
    if not name:
        return None
    address = clean_text(attributes.get("address"))
    category = clean_text(attributes.get("category"))
    lat = to_float(attributes.get("lat"))
    lon = to_float(attributes.get("long"))
    if lat is None or lon is None:
        lat = lon = None
    else:
        min_lat, max_lat, min_lon, max_lon = DR_BOUNDS
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            lat = lon = None
    return {
        "record_id": make_id("bhd", api_id or name, address),
        "bank": "Banco BHD",
        "location_type": infer_location_type(category, name),
        "name": name,
        "zone": clean_text(attributes.get("zone")),
        "address": address,
        "phone": clean_text(attributes.get("phone_number")),
        "municipality": "",
        "province": "",
        "latitude": lat,
        "longitude": lon,
        "source": "bhd_public_locations_api",
        "source_url": source_url,
        "api_id": api_id,
        "category": category,
        "extended_hours": attributes.get("horario_extendido"),
        "actions_performed": clean_text(attributes.get("actions_performed")),
        "special_instructions": clean_text(attributes.get("special_instructions")),
        "weekday_schedule_json": attributes.get("weekdaysTime") or [],
        "created_at_source": clean_text(attributes.get("createdAt")),
        "updated_at_source": clean_text(attributes.get("updatedAt")),
        "published_at_source": clean_text(attributes.get("publishedAt")),
    }


def fetch_bhd_rows(
    progress: ProgressCallback | None = None,
    delay_seconds: float = 0.1,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session = build_session()
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    page = 1
    page_count: int | None = None
    reported_total: int | None = None
    last_url = BHD_API_URL
    try:
        while page <= BHD_MAX_PAGES:
            payload, last_url = request_page(session, page)
            data = payload.get("data", [])
            pagination = (payload.get("meta") or {}).get("pagination") or {}
            if isinstance(pagination.get("pageCount"), int):
                page_count = pagination["pageCount"]
            if isinstance(pagination.get("total"), int):
                reported_total = pagination["total"]

            for item in data:
                if not isinstance(item, dict):
                    continue
                api_id = clean_text(item.get("id")) or make_id(item)
                if api_id not in seen_ids:
                    items.append(item)
                    seen_ids.add(api_id)

            if progress:
                progress(page, page_count, f"Descargando página {page} de {page_count or '?'}")
            if not data or (page_count is not None and page >= page_count):
                break
            if page_count is None and len(data) < BHD_PAGE_SIZE:
                break
            page += 1
            if delay_seconds:
                time.sleep(delay_seconds)
        else:
            raise RuntimeError("La paginación BHD excedió el límite de seguridad")
    finally:
        session.close()

    rows = [row for item in items if (row := item_to_row(item, last_url)) is not None]
    category_counts = Counter(row["location_type"] for row in rows)
    metadata = {
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "endpoint": BHD_API_URL,
        "reported_total": reported_total,
        "downloaded": len(items),
        "rows": len(rows),
        "pages": page,
        "categories": dict(category_counts),
    }
    return rows, metadata
