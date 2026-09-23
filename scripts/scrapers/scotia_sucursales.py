from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, unquote

import requests
from bs4 import BeautifulSoup

# =========================================================
# CONFIGURATION
# =========================================================

SCOTIABANK_URL = (
    "https://do.scotiabank.com/acerca-de-scotiabank/conectate-con-scotia/sucursales-y-atms.html"
)

GOOGLE_MAPS_SEARCH_URL = "https://www.google.com/maps/search/{}"


def find_project_root(start: Path) -> Path:
    """Find the Git project root so data is saved in <project>/data."""
    current = start.resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate

    # If the script is not inside a Git repository, use its own directory.
    return current


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = find_project_root(SCRIPT_DIR)
OUTPUT_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CACHE_FILE = OUTPUT_DIR / "scotiabank_google_maps_cache.json"
DEFAULT_OUTPUT_FILE = OUTPUT_DIR / "scotiabank_branches_rd.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-DO,es;q=0.9,en;q=0.8",
}

# Sanity check only. Coordinates outside this box are rejected.
DR_BOUNDS = {
    "min_lat": 17.3,
    "max_lat": 20.2,
    "min_lon": -72.2,
    "max_lon": -68.0,
}

MAPS_DELAY_SECONDS = 1.5
MAPS_TIMEOUT_MS = 20_000


# =========================================================
# CLI
# =========================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract official Scotiabank branches in Dominican Republic and "
            "obtain coordinates directly from the final Google Maps place URL."
        )
    )

    parser.add_argument(
        "--no-geocode",
        action="store_true",
        help="Extract official branches without opening Google Maps.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore saved Google Maps results and search again.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_FILE),
        help=f"Output CSV file. Default: {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print extracted branches to the console.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help=(
            "Show the browser window. Useful on the first run if Google "
            "shows a consent page or CAPTCHA."
        ),
    )
    parser.add_argument(
        "--browser",
        choices=("auto", "chrome", "msedge", "chromium"),
        default="auto",
        help="Browser used by Playwright. Default: auto.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=MAPS_TIMEOUT_MS,
        help=f"Maximum wait per Google Maps query in milliseconds. Default: {MAPS_TIMEOUT_MS}.",
    )

    return parser.parse_args()


# =========================================================
# TEXT UTILITIES
# =========================================================


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return value.strip()


def make_id(*values: Any) -> str:
    raw = "|".join(str(value or "") for value in values)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def normalize_header(value: str) -> str:
    value = normalize_text(value)

    aliases = {
        "nombre": "name",
        "sucursal": "name",
        "direccion": "address",
        "telefono": "phone",
        "telefonos": "phone",
    }

    return aliases.get(value, value)


def normalize_rd_address(value: str | None) -> str:
    """Expand common Dominican address abbreviations for search queries."""
    text = clean_text(value)
    if not text:
        return ""

    replacements = [
        (r"\bAv\.?\s*", "Avenida "),
        (r"\bAut\.?\s*", "Autopista "),
        (r"\bC/\s*", "Calle "),
        (r"\bNo\.?\s*", "Número "),
        (r"\besq\.?\s*", "esquina "),
    ]

    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return clean_text(text)


def branch_city_hints(row: dict) -> list[str]:
    zone = normalize_text(row.get("zone"))
    combined = normalize_text(f"{row.get('name', '')} {row.get('address', '')}")

    hints: list[str] = []

    if "metropolitana" in zone:
        hints.append("Santo Domingo")

    known_places = [
        ("santiago", "Santiago de los Caballeros"),
        ("la romana", "La Romana"),
        ("higuey", "Higüey"),
        ("bavaro", "Bávaro"),
        ("punta cana", "Punta Cana"),
        ("san cristobal", "San Cristóbal"),
        ("azua", "Azua"),
        ("bani", "Baní"),
        ("san francisco de macoris", "San Francisco de Macorís"),
        ("moca", "Moca"),
        ("la vega", "La Vega"),
        ("bonao", "Bonao"),
        ("nagua", "Nagua"),
        ("puerto plata", "Puerto Plata"),
        ("las terrenas", "Las Terrenas"),
        ("samana", "Samaná"),
    ]

    for needle, city in known_places:
        if needle in combined:
            hints.insert(0, city)
            break

    unique: list[str] = []
    seen = set()
    for item in hints:
        key = normalize_text(item)
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


# =========================================================
# OFFICIAL SCOTIABANK PAGE
# =========================================================


def get_scotiabank_page(session: requests.Session) -> BeautifulSoup:
    print("\nDownloading official Scotiabank branch list...")

    try:
        response = session.get(SCOTIABANK_URL, timeout=30)
        print(f"HTTP: {response.status_code}")
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            "Could not download the official Scotiabank branch page. "
            "Check your Internet connection and try again."
        ) from exc

    return BeautifulSoup(response.text, "html.parser")


def get_table_headers(table) -> list[str]:
    first_header_row = table.find("tr")
    if not first_header_row:
        return []

    header_cells = first_header_row.find_all(["th", "td"])
    return [normalize_header(clean_text(cell.get_text(" ", strip=True))) for cell in header_cells]


def row_to_dict(headers: list[str], cells: list[str]) -> dict[str, str]:
    row = {}
    for index, value in enumerate(cells):
        key = headers[index] if index < len(headers) else f"column_{index + 1}"
        row[key] = value
    return row


def extract_branch_tables(soup: BeautifulSoup) -> list[dict]:
    """Extract only Scotiabank branches from the official branch tables."""
    results: list[dict] = []
    current_zone = ""
    seen = set()

    for element in soup.find_all(["h2", "h3", "h4", "h5", "h6", "table"]):
        if element.name != "table":
            heading = clean_text(element.get_text(" ", strip=True))
            if normalize_text(heading).startswith("zona "):
                current_zone = heading
            continue

        headers = get_table_headers(element)
        if not headers or "name" not in headers or "address" not in headers:
            continue

        for html_row in element.find_all("tr")[1:]:
            cells = [
                clean_text(cell.get_text(" ", strip=True))
                for cell in html_row.find_all(["td", "th"])
            ]
            if not cells:
                continue

            parsed = row_to_dict(headers, cells)
            name = clean_text(parsed.get("name"))
            address = clean_text(parsed.get("address"))
            phone = clean_text(parsed.get("phone"))

            if not name or not address:
                continue
            if "scotiabank" not in normalize_text(name):
                continue

            dedupe_key = (normalize_text(name), normalize_text(address))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            results.append(
                {
                    "record_id": make_id("scotiabank", "branch", name, address),
                    "bank": "Scotiabank",
                    "location_type": "branch",
                    "name": name,
                    "zone": current_zone,
                    "address": address,
                    "phone": phone,
                    "municipality": "",
                    "province": "",
                    "country": "Dominican Republic",
                    "country_code": "DO",
                    "latitude": None,
                    "longitude": None,
                    "geocoded_address": "",
                    "geocode_query": "",
                    "geocode_quality": "",
                    "coordinate_source": "",
                    "google_maps_url": "",
                    "google_maps_coordinate_pattern": "",
                    "source": "scotiabank_official",
                    "source_url": SCOTIABANK_URL,
                }
            )

    return results


# =========================================================
# CACHE
# =========================================================


def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}

    try:
        with CACHE_FILE.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict) -> None:
    with CACHE_FILE.open("w", encoding="utf-8") as file:
        json.dump(cache, file, indent=2, ensure_ascii=False)


# =========================================================
# GOOGLE MAPS URL GEOLOCATION
# =========================================================


def is_inside_dominican_republic(lat: float, lon: float) -> bool:
    return (
        DR_BOUNDS["min_lat"] <= lat <= DR_BOUNDS["max_lat"]
        and DR_BOUNDS["min_lon"] <= lon <= DR_BOUNDS["max_lon"]
    )


def parse_google_maps_coordinates(url: str) -> tuple[float, float, str] | None:
    """
    Extract coordinates from a Google Maps PLACE URL.

    Priority:
      1) !3dLAT!4dLON  -> actual place pin when present.
      2) /@LAT,LON     -> fallback only when URL is already /maps/place/.

    Search-result map centers are deliberately rejected.
    """
    decoded = unquote(url or "")

    if "/maps/place/" not in decoded:
        return None

    pin_match = re.search(
        r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)",
        decoded,
    )
    if pin_match:
        lat = float(pin_match.group(1))
        lon = float(pin_match.group(2))
        if is_inside_dominican_republic(lat, lon):
            return lat, lon, "place_pin_3d4d"

    viewport_match = re.search(
        r"/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)(?:,|/)",
        decoded,
    )
    if viewport_match:
        lat = float(viewport_match.group(1))
        lon = float(viewport_match.group(2))
        if is_inside_dominican_republic(lat, lon):
            return lat, lon, "place_url_at"

    return None


def build_maps_queries(row: dict) -> list[tuple[str, str]]:
    """
    Start with exactly the approach requested by the user:
    https://www.google.com/maps/search/Scotiabank+Duarte+Sur

    More specific variants are only attempted if the branch-name search
    does not resolve to a /maps/place/ URL.
    """
    name = clean_text(row.get("name"))
    address = clean_text(row.get("address"))
    normalized_address = normalize_rd_address(address)
    city_hints = branch_city_hints(row)

    queries: list[tuple[str, str]] = [
        (name, "maps_branch_name"),
    ]

    for city in city_hints:
        queries.append((f"{name}, {city}, República Dominicana", "maps_branch_name_city"))

    if normalized_address:
        if city_hints:
            for city in city_hints:
                queries.append(
                    (
                        f"{name}, {normalized_address}, {city}, República Dominicana",
                        "maps_name_address_city",
                    )
                )
        queries.append(
            (
                f"{name}, {normalized_address}, República Dominicana",
                "maps_name_address_country",
            )
        )

    unique: list[tuple[str, str]] = []
    seen = set()
    for query, quality in queries:
        key = normalize_text(query)
        if key and key not in seen:
            seen.add(key)
            unique.append((query, quality))

    return unique


def make_maps_search_url(query: str) -> str:
    return GOOGLE_MAPS_SEARCH_URL.format(quote_plus(clean_text(query)))


def try_accept_google_consent(page) -> None:
    """Best-effort handling of common Google consent dialogs."""
    labels = [
        "Accept all",
        "Aceptar todo",
        "I agree",
        "Acepto",
    ]

    for label in labels:
        try:
            button = page.get_by_role("button", name=label, exact=True)
            if button.count() > 0:
                button.first.click(timeout=1500)
                page.wait_for_timeout(500)
                return
        except Exception:
            pass


def wait_for_place_url(page, timeout_ms: int) -> str:
    """Wait for Maps to resolve search -> place, then return current URL."""
    deadline = time.monotonic() + (timeout_ms / 1000.0)

    while time.monotonic() < deadline:
        current_url = page.url
        if "/maps/place/" in unquote(current_url):
            # Give Maps a moment to enrich the URL with !3d/!4d data.
            page.wait_for_timeout(800)
            return page.url

        page.wait_for_timeout(250)

    return page.url


def open_first_place_result_if_needed(page) -> bool:
    """
    If Maps stays on a search-results page, open the first Maps place link.
    This is only a fallback; exact branch-name searches often redirect directly.
    """
    try:
        links = page.locator('a[href*="/maps/place/"]')
        count = min(links.count(), 10)

        for index in range(count):
            href = links.nth(index).get_attribute("href")
            if not href or "/maps/place/" not in href:
                continue

            page.goto(href, wait_until="domcontentloaded", timeout=MAPS_TIMEOUT_MS)
            return True
    except Exception:
        pass

    return False


def query_google_maps_browser(
    page,
    query: str,
    cache: dict,
    timeout_ms: int,
) -> dict | None:
    cache_key = "google_maps_browser|" + normalize_text(query)

    if cache_key in cache:
        return cache[cache_key]

    search_url = make_maps_search_url(query)

    try:
        page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )

        try_accept_google_consent(page)
        final_url = wait_for_place_url(page, timeout_ms)

        # Some searches show a result list instead of redirecting.
        if "/maps/place/" not in unquote(final_url):
            if open_first_place_result_if_needed(page):
                final_url = wait_for_place_url(page, timeout_ms)

        coordinates = parse_google_maps_coordinates(final_url)

        if not coordinates:
            result = None
        else:
            lat, lon, pattern = coordinates
            result = {
                "latitude": lat,
                "longitude": lon,
                "final_url": final_url,
                "coordinate_pattern": pattern,
                "search_url": search_url,
            }

        cache[cache_key] = result
        save_cache(cache)
        time.sleep(MAPS_DELAY_SECONDS)
        return result

    except Exception as exc:
        print(f"   Browser error: {exc}")
        return None


def launch_maps_browser(playwright, headed: bool, browser_choice: str):
    """Launch one browser and reuse it for every branch."""
    launch_args = {
        "headless": not headed,
        "args": ["--start-maximized"],
    }

    if browser_choice == "chrome":
        return playwright.chromium.launch(channel="chrome", **launch_args)

    if browser_choice == "msedge":
        return playwright.chromium.launch(channel="msedge", **launch_args)

    if browser_choice == "chromium":
        return playwright.chromium.launch(**launch_args)

    # auto: prefer installed Chrome, then Edge, then Playwright Chromium.
    for channel in ("chrome", "msedge"):
        try:
            return playwright.chromium.launch(channel=channel, **launch_args)
        except Exception:
            continue

    return playwright.chromium.launch(**launch_args)


def apply_maps_result(
    row: dict,
    result: dict,
    query: str,
    quality: str,
) -> None:
    row["latitude"] = float(result["latitude"])
    row["longitude"] = float(result["longitude"])
    row["geocode_query"] = query
    row["geocode_quality"] = quality
    row["coordinate_source"] = "google_maps_browser_url"
    row["google_maps_url"] = clean_text(result.get("final_url"))
    row["google_maps_coordinate_pattern"] = clean_text(result.get("coordinate_pattern"))


def geocode_branches_with_google_maps(
    branches: list[dict],
    cache: dict,
    headed: bool,
    browser_choice: str,
    timeout_ms: int,
    checkpoint_file: Path | None = None,
) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for Google Maps browser geolocation.\n"
            "Install it with:\n"
            "  pip install playwright\n"
            "If no Chrome/Edge is installed, also run:\n"
            "  python -m playwright install chromium"
        ) from exc

    print("\n" + "=" * 72)
    print("GOOGLE MAPS BROWSER GEOLOCATION")
    print("=" * 72)
    print("Source            : Google Maps final /maps/place/ URL")
    print("Preferred pattern : !3dLAT!4dLON")
    print("Fallback pattern  : @LAT,LON, but only inside /maps/place/")

    total = len(branches)
    found = 0

    with sync_playwright() as playwright:
        browser = launch_maps_browser(playwright, headed, browser_choice)
        context = browser.new_context(
            locale="es-DO",
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            for index, branch in enumerate(branches, start=1):
                print(f"\n[{index}/{total}] {branch['name']}")
                geocoded = False

                for query, quality in build_maps_queries(branch):
                    search_url = make_maps_search_url(query)
                    print(f"   Searching: {search_url}")

                    result = query_google_maps_browser(
                        page,
                        query,
                        cache,
                        timeout_ms,
                    )

                    if not result:
                        print("   -> no /maps/place/ coordinates found")
                        continue

                    apply_maps_result(branch, result, query, quality)
                    found += 1
                    geocoded = True

                    print(
                        f"   -> {branch['latitude']}, {branch['longitude']} "
                        f"[{branch['google_maps_coordinate_pattern']}]"
                    )
                    print(f"   -> {branch['google_maps_url']}")
                    break

                if not geocoded:
                    branch["geocode_quality"] = "not_found"
                    print("   -> LOCATION NOT FOUND")

                # Persist progress after EVERY branch. If the browser is closed,
                # Google blocks a later query, or the process is interrupted,
                # everything found up to this point is already on disk.
                if checkpoint_file is not None:
                    export_csv(branches, checkpoint_file, announce=False)
                    print(f"   -> checkpoint saved [{index}/{total}]: {checkpoint_file}")

        finally:
            context.close()
            browser.close()

    print("\n" + "-" * 72)
    print(f"Geocoded: {found}/{total}")
    print(f"Missing  : {total - found}/{total}")


# =========================================================
# OUTPUT
# =========================================================

CSV_COLUMNS = [
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
]


def export_csv(
    branches: list[dict],
    filepath: Path,
    announce: bool = True,
) -> None:
    filepath = filepath.expanduser().resolve()
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temporary file first and replace atomically. This avoids
    # leaving a partially written CSV if the process is interrupted.
    temp_file = filepath.with_suffix(filepath.suffix + ".tmp")

    with temp_file.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CSV_COLUMNS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(branches)

    temp_file.replace(filepath)

    if announce:
        print(f"\n{len(branches)} branches -> {filepath}")


def resolve_output_file(value: str) -> Path:
    """Resolve relative --output paths from the project root, not the CWD."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def print_branches(branches: list[dict]) -> None:
    print("\n" + "=" * 110)
    print("SCOTIABANK BRANCHES - DOMINICAN REPUBLIC")
    print("=" * 110)

    for branch in branches:
        coords = ""
        if branch.get("latitude") is not None and branch.get("longitude") is not None:
            coords = f" | {branch['latitude']:.7f}, {branch['longitude']:.7f}"

        print(f"{branch['zone']:<20} | {branch['name']:<48} | {branch['address']}{coords}")


def print_summary(branches: list[dict]) -> None:
    geocoded = [
        row
        for row in branches
        if row.get("latitude") is not None and row.get("longitude") is not None
    ]

    zones: dict[str, int] = {}
    for row in branches:
        zone = row.get("zone") or "Sin zona"
        zones[zone] = zones.get(zone, 0) + 1

    print("\n" + "=" * 72)
    print("SCOTIABANK BRANCH EXTRACTION SUMMARY")
    print("=" * 72)
    print(f"Branches found     : {len(branches)}")
    print(f"With coordinates   : {len(geocoded)}")
    print(f"Without coordinates: {len(branches) - len(geocoded)}")

    for zone, count in zones.items():
        print(f"{zone:<20}: {count}")

    print("=" * 72)


# =========================================================
# MAIN
# =========================================================


def main() -> int:
    args = parse_args()

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        soup = get_scotiabank_page(session)
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        return 1

    branches = extract_branch_tables(soup)
    print(f"\nOfficial branches extracted: {len(branches)}")

    if not branches:
        print(
            "WARNING: no branches were extracted. The Scotiabank page structure may have changed."
        )
        return 2

    output_file = resolve_output_file(args.output)

    print("\nOUTPUT CONFIGURATION")
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Data folder  : {OUTPUT_DIR}")
    print(f"CSV file     : {output_file}")
    print(f"Cache file   : {CACHE_FILE}")

    # Create the CSV immediately. From this point onward there is always
    # a file on disk even if browser geolocation later fails.
    export_csv(branches, output_file)
    print("Initial CSV created before geolocation.")

    if not args.no_geocode:
        cache = {} if args.refresh_cache else load_cache()

        try:
            geocode_branches_with_google_maps(
                branches=branches,
                cache=cache,
                headed=args.headed,
                browser_choice=args.browser,
                timeout_ms=max(5_000, args.timeout),
                checkpoint_file=output_file,
            )
        except RuntimeError as exc:
            # The initial CSV and any checkpoints remain available.
            export_csv(branches, output_file)
            print(f"\nERROR: {exc}")
            print(f"Partial data preserved at: {output_file}")
            return 3

    # Final save after the complete run.
    export_csv(branches, output_file)
    print_summary(branches)

    if args.show:
        print_branches(branches)

    print("\nBranch source:")
    print(SCOTIABANK_URL)
    print("\nCoordinate source:")
    print("Google Maps final place URL (/maps/place/)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
