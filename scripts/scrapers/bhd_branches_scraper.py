from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================================================
# CONFIGURATION
# =========================================================

BHD_API_URL = "https://backend.bhd.com.do/api/locations"

DEFAULT_PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_DELAY_SECONDS = 0.15

DR_BOUNDS = {
    "min_lat": 17.3,
    "max_lat": 20.2,
    "min_lon": -72.2,
    "max_lon": -68.0,
}

BRANCH_CATEGORY_HINTS = (
    "sucursal",
    "sucursales",
    "oficina",
    "oficinas",
)

EXCLUDED_CATEGORY_HINTS = (
    "subagente",
    "subagentes",
    "cajero",
    "cajeros",
    "atm",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-DO,es;q=0.9,en;q=0.8",
}


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate

    return current


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = find_project_root(SCRIPT_DIR)
OUTPUT_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_OUTPUT_FILE = OUTPUT_DIR / "bhd_locations_rd.csv"
DEFAULT_RAW_FILE = OUTPUT_DIR / "bhd_locations_raw.json"


CSV_COLUMNS = [
    # Common branch schema used by the previous bank scrapers.
    "record_id",
    "bank",
    "location_type",
    "name",
    "zone",
    "address",
    "phone",
    "municipality",
    "province",
    "country",
    "country_code",
    "latitude",
    "longitude",
    "geocoded_address",
    "geocode_query",
    "geocode_quality",
    "coordinate_source",
    "google_maps_coordinate_pattern",
    "google_maps_url",
    "source",
    "source_url",
    # BHD-specific data.
    "api_id",
    "category",
    "extended_hours",
    "actions_performed",
    "fax",
    "special_instructions",
    "weekday_schedule_json",
    "created_at_source",
    "updated_at_source",
    "published_at_source",
]


# =========================================================
# CLI
# =========================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download Banco BHD locations from the bank's public paginated API "
            "and export branches/offices to CSV."
        )
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_FILE),
        help=f"Output CSV file. Default: {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--raw-output",
        default=str(DEFAULT_RAW_FILE),
        help=f"Raw API JSON file. Default: {DEFAULT_RAW_FILE}",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"API page size. Default: {DEFAULT_PAGE_SIZE}",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="First API page to download. Default: 1",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Maximum pages to download; 0 means no artificial limit.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Delay between API pages in seconds. Default: {DEFAULT_DELAY_SECONDS}",
    )
    parser.add_argument(
        "--all-locations",
        action="store_true",
        help=(
            "Export every BHD location returned by the API, including ATMs and "
            "subagents. By default only branches/offices are exported."
        ),
    )
    parser.add_argument(
        "--categories",
        default="",
        help=(
            "Optional comma-separated exact categories to export, e.g. "
            "'sucursales,oficinas'. Overrides the default branch-category classifier."
        ),
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print exported locations to the console.",
    )
    parser.add_argument(
        "--load-db",
        action="store_true",
        help=(
            "Load the exported locations into PostgreSQL. Without --categories, "
            "this automatically includes branches, ATMs and subagents."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the database load and roll it back (requires --load-db).",
    )

    return parser.parse_args()


# =========================================================
# TEXT / VALUE UTILITIES
# =========================================================


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_text(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def make_id(*values: Any) -> str:
    raw = "|".join(clean_text(value) for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def is_inside_dominican_republic(lat: float, lon: float) -> bool:
    return (
        DR_BOUNDS["min_lat"] <= lat <= DR_BOUNDS["max_lat"]
        and DR_BOUNDS["min_lon"] <= lon <= DR_BOUNDS["max_lon"]
    )


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# =========================================================
# HTTP / PAGINATION
# =========================================================


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)

    retries = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def request_page(
    session: requests.Session,
    page: int,
    page_size: int,
    timeout: int,
) -> tuple[dict[str, Any], str]:
    params = {
        "populate": "deep",
        "pagination[pageSize]": page_size,
        "pagination[page]": page,
    }

    response = session.get(BHD_API_URL, params=params, timeout=timeout)
    print(f"   HTTP {response.status_code}: {response.url}")
    response.raise_for_status()

    try:
        # requests may infer ISO-8859-1 when the endpoint omits a charset. The
        # BHD payload is UTF-8, so decoding it explicitly preserves accents.
        payload = json.loads(response.content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        preview = response.content[:500].decode("utf-8", errors="replace").replace("\n", " ")
        raise RuntimeError(f"BHD returned a non-JSON response on page {page}: {preview}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected BHD response on page {page}: expected JSON object.")

    return payload, response.url


def get_pagination(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return {}

    pagination = meta.get("pagination")
    return pagination if isinstance(pagination, dict) else {}


def fetch_all_locations(
    session: requests.Session,
    start_page: int,
    page_size: int,
    timeout: int,
    delay: float,
    max_pages: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_items: list[dict[str, Any]] = []
    page_summaries: list[dict[str, Any]] = []

    page = max(1, start_page)
    pages_downloaded = 0
    seen_api_ids: set[str] = set()
    last_known_page_count: int | None = None
    last_known_total: int | None = None
    last_url = BHD_API_URL

    print("\n" + "=" * 76)
    print("BANCO BHD - PUBLIC LOCATIONS API")
    print("=" * 76)
    print(f"Endpoint : {BHD_API_URL}")
    print(f"Page size: {page_size}")

    while True:
        if max_pages > 0 and pages_downloaded >= max_pages:
            print(f"\nReached --max-pages={max_pages}; stopping.")
            break

        print(f"\nDownloading page {page}...")
        payload, request_url = request_page(session, page, page_size, timeout)
        last_url = request_url

        data = payload.get("data", [])
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected BHD response on page {page}: 'data' is not a list.")

        pagination = get_pagination(payload)
        page_count = pagination.get("pageCount")
        total = pagination.get("total")
        current_page = pagination.get("page", page)
        returned_page_size = pagination.get("pageSize", page_size)

        if isinstance(page_count, int) and page_count > 0:
            last_known_page_count = page_count
        if isinstance(total, int) and total >= 0:
            last_known_total = total

        page_summaries.append(
            {
                "requested_page": page,
                "reported_page": current_page,
                "reported_page_size": returned_page_size,
                "page_count": page_count,
                "total": total,
                "items_returned": len(data),
                "url": request_url,
            }
        )

        if not data:
            print("   -> 0 records; pagination complete.")
            break

        added = 0
        for item in data:
            if not isinstance(item, dict):
                continue

            api_id = clean_text(item.get("id"))
            dedupe_key = api_id or make_id(item)
            if dedupe_key in seen_api_ids:
                continue

            seen_api_ids.add(dedupe_key)
            all_items.append(item)
            added += 1

        pages_downloaded += 1
        print(f"   -> returned: {len(data)} | new: {added} | accumulated: {len(all_items)}")

        if last_known_page_count is not None:
            print(
                f"   -> API pagination: page {current_page}/{last_known_page_count}"
                + (f" | total={last_known_total}" if last_known_total is not None else "")
            )
            if page >= last_known_page_count:
                break
        else:
            effective_page_size = (
                returned_page_size
                if isinstance(returned_page_size, int) and returned_page_size > 0
                else page_size
            )
            if len(data) < effective_page_size:
                # Safe fallback when pageCount is absent.
                print("   -> final partial page detected.")
                break

        page += 1
        if delay > 0:
            time.sleep(delay)

    metadata = {
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "source": "bhd_public_locations_api",
        "endpoint": BHD_API_URL,
        "last_request_url": last_url,
        "requested_page_size": page_size,
        "start_page": start_page,
        "pages_downloaded": pages_downloaded,
        "page_count": last_known_page_count,
        "reported_total": last_known_total,
        "unique_records_downloaded": len(all_items),
        "pages": page_summaries,
    }

    return all_items, metadata


# =========================================================
# BHD RECORD PARSING
# =========================================================


def get_attributes(item: dict[str, Any]) -> dict[str, Any]:
    """
    Support both Strapi v4 style:
      {"id": 1, "attributes": {...}}

    and flatter payloads in case the backend is upgraded later:
      {"id": 1, "name": "...", ...}
    """
    attrs = item.get("attributes")
    if isinstance(attrs, dict):
        return attrs
    return item


def infer_location_type(category: Any, name: Any = "") -> str:
    normalized = normalize_text(category)
    normalized_name = normalize_text(name)
    combined = f"{normalized} {normalized_name}".strip()

    if "subagente" in combined:
        return "subagent"
    if "cajero" in combined or re.search(r"\batm\b", combined):
        return "atm"
    if "sucursal" in combined or "oficina" in combined:
        return "branch"

    return normalized.replace(" ", "_") or "location"


def is_branch_location(item: dict[str, Any]) -> bool:
    attrs = get_attributes(item)
    category = normalize_text(attrs.get("category"))
    name = normalize_text(attrs.get("name"))

    # Explicitly reject known non-branch channels first.
    if any(hint in category for hint in EXCLUDED_CATEGORY_HINTS):
        return False

    if any(hint in category for hint in BRANCH_CATEGORY_HINTS):
        return True

    # Fallback for unexpected category naming.
    return "sucursal" in name or "oficina" in name


def category_matches_exact(item: dict[str, Any], requested: set[str]) -> bool:
    attrs = get_attributes(item)
    category = normalize_text(attrs.get("category"))
    return category in requested


def item_to_row(item: dict[str, Any], source_url: str) -> dict[str, Any] | None:
    attrs = get_attributes(item)

    api_id = clean_text(item.get("id") or attrs.get("id"))
    name = clean_text(attrs.get("name"))
    address = clean_text(attrs.get("address"))
    category = clean_text(attrs.get("category"))
    zone = clean_text(attrs.get("zone"))
    phone = clean_text(attrs.get("phone_number"))

    if not name:
        return None

    lat = to_float(attrs.get("lat"))
    lon = to_float(attrs.get("long"))

    coordinate_quality = "missing"
    latitude: float | None = None
    longitude: float | None = None

    if lat is not None and lon is not None:
        if is_inside_dominican_republic(lat, lon):
            latitude = lat
            longitude = lon
            coordinate_quality = "official_api"
        else:
            coordinate_quality = "official_api_outside_dr_bounds"

    location_type = infer_location_type(category, name)

    return {
        "record_id": make_id("bhd", api_id or name, address),
        "bank": "Banco BHD",
        "location_type": location_type,
        "name": name,
        "zone": zone,
        "address": address,
        "phone": phone,
        "municipality": "",
        "province": "",
        "country": "Dominican Republic",
        "country_code": "DO",
        "latitude": latitude,
        "longitude": longitude,
        "geocoded_address": address,
        "geocode_query": "",
        "geocode_quality": coordinate_quality,
        "coordinate_source": "bhd_official_api" if latitude is not None else "",
        "google_maps_coordinate_pattern": "",
        "google_maps_url": "",
        "source": "bhd_public_locations_api",
        "source_url": source_url,
        "api_id": api_id,
        "category": category,
        "extended_hours": attrs.get("horario_extendido"),
        "actions_performed": clean_text(attrs.get("actions_performed")),
        "fax": clean_text(attrs.get("fax")),
        "special_instructions": clean_text(attrs.get("special_instructions")),
        "weekday_schedule_json": safe_json(attrs.get("weekdaysTime") or []),
        "created_at_source": clean_text(attrs.get("createdAt")),
        "updated_at_source": clean_text(attrs.get("updatedAt")),
        "published_at_source": clean_text(attrs.get("publishedAt")),
    }


def extract_rows(
    items: list[dict[str, Any]],
    source_url: str,
    all_locations: bool,
    exact_categories: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in items:
        if exact_categories:
            if not category_matches_exact(item, exact_categories):
                continue
        elif not all_locations and not is_branch_location(item):
            continue

        row = item_to_row(item, source_url)
        if not row:
            continue

        key = row["api_id"] or row["record_id"]
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    rows.sort(
        key=lambda row: (
            normalize_text(row.get("zone")),
            normalize_text(row.get("name")),
            normalize_text(row.get("address")),
        )
    )
    return rows


def get_category_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        attrs = get_attributes(item)
        category = clean_text(attrs.get("category")) or "(sin categoría)"
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: normalize_text(pair[0])))


# =========================================================
# OUTPUT
# =========================================================


def save_raw_json(
    filepath: Path,
    items: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    temp_file = filepath.with_suffix(filepath.suffix + ".tmp")

    payload = {
        "metadata": metadata,
        "data": items,
    }

    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)

    temp_file.replace(filepath)
    print(f"Raw JSON      : {filepath}")


def export_csv(rows: list[dict[str, Any]], filepath: Path) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    temp_file = filepath.with_suffix(filepath.suffix + ".tmp")

    with temp_file.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CSV_COLUMNS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

    temp_file.replace(filepath)
    print(f"CSV            : {filepath}")


def print_summary(
    all_items: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    coordinates = [
        row for row in rows if row.get("latitude") is not None and row.get("longitude") is not None
    ]

    print("\n" + "=" * 76)
    print("BANCO BHD EXTRACTION SUMMARY")
    print("=" * 76)
    print(f"Pages downloaded       : {metadata.get('pages_downloaded', 0)}")
    print(f"API records downloaded : {len(all_items)}")
    if metadata.get("reported_total") is not None:
        print(f"API reported total     : {metadata['reported_total']}")
    print(f"Rows exported          : {len(rows)}")
    print(f"With coordinates       : {len(coordinates)}")
    print(f"Without coordinates    : {len(rows) - len(coordinates)}")

    print("\nCategories returned by BHD:")
    category_counts = get_category_counts(all_items)
    for category, count in category_counts.items():
        print(f"  {category:<30} {count:>5}")

    print("=" * 76)


def print_rows(rows: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 120)
    print("BANCO BHD LOCATIONS")
    print("=" * 120)

    for row in rows:
        coords = ""
        if row.get("latitude") is not None and row.get("longitude") is not None:
            coords = f" | {row['latitude']:.7f}, {row['longitude']:.7f}"

        print(
            f"{row.get('category', ''):<18} | "
            f"{row.get('zone', ''):<20} | "
            f"{row.get('name', ''):<45} | "
            f"{row.get('address', '')}{coords}"
        )


# =========================================================
# MAIN
# =========================================================


def main() -> int:
    args = parse_args()

    if args.dry_run and not args.load_db:
        print("ERROR: --dry-run requires --load-db")
        return 2

    page_size = max(1, args.page_size)
    start_page = max(1, args.start_page)
    timeout = max(5, args.timeout)
    delay = max(0.0, args.delay)
    max_pages = max(0, args.max_pages)

    output_file = resolve_path(args.output)
    raw_file = resolve_path(args.raw_output)

    exact_categories = {
        normalize_text(value) for value in args.categories.split(",") if normalize_text(value)
    }

    print("OUTPUT CONFIGURATION")
    print(f"Project root   : {PROJECT_ROOT}")
    print(f"Data folder    : {OUTPUT_DIR}")
    print(f"CSV output     : {output_file}")
    print(f"Raw JSON output: {raw_file}")

    all_locations = args.all_locations or (args.load_db and not exact_categories)

    if exact_categories:
        print("Category filter: " + ", ".join(sorted(exact_categories)))
    elif all_locations:
        print("Category filter: ALL LOCATIONS")
    else:
        print("Category filter: branches/offices only")

    session = build_session()

    try:
        all_items, metadata = fetch_all_locations(
            session=session,
            start_page=start_page,
            page_size=page_size,
            timeout=timeout,
            delay=delay,
            max_pages=max_pages,
        )
    except (requests.RequestException, RuntimeError) as exc:
        print(f"\nERROR: {exc}")
        return 1

    save_raw_json(raw_file, all_items, metadata)

    source_url = BHD_API_URL
    rows = extract_rows(
        items=all_items,
        source_url=source_url,
        all_locations=all_locations,
        exact_categories=exact_categories,
    )

    export_csv(rows, output_file)
    print_summary(all_items, rows, metadata)

    if not rows and all_items and not all_locations:
        print(
            "\nWARNING: the API returned records, but none matched the default "
            "branch/office classifier. Review the category list above and rerun "
            "with --categories '<exact-category>' or --all-locations."
        )

    if args.show:
        print_rows(rows)

    if args.load_db:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        try:
            from app.db.session import get_session_factory
            from app.services.location_import import import_bhd_rows

            with get_session_factory()() as db:
                result = import_bhd_rows(db, rows)
                if args.dry_run:
                    db.rollback()
                else:
                    db.commit()
            print("\nDATABASE LOAD")
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
            print("Mode: validation only (rolled back)" if args.dry_run else "Mode: committed")
        except Exception as exc:
            print(f"\nDATABASE ERROR: {exc}")
            return 1

    print("\nSource:")
    print(BHD_API_URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
