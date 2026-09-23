from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import get_session_factory
from app.services.location_import import import_bhd_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Carga idempotente de sucursales, cajeros y subagentes BHD desde CSV."
    )
    parser.add_argument("--input", type=Path, required=True, help="CSV generado por el scraper BHD")
    parser.add_argument(
        "--dry-run", action="store_true", help="Valida y muestra el resultado sin confirmar cambios"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"No existe el archivo: {input_path}")

    session_factory = get_session_factory()
    with session_factory() as db:
        try:
            result = import_bhd_csv(db, input_path)
            if args.dry_run:
                db.rollback()
            else:
                db.commit()
        except Exception:
            db.rollback()
            raise

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    print("Modo: validación sin cambios" if args.dry_run else "Carga confirmada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
