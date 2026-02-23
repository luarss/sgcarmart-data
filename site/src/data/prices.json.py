#!/usr/bin/env python3
"""Data loader for Observable Framework.

Walks data/pricelists/{brand}/{year}/*.json, normalizes names, deduplicates,
and writes a single JSON object to stdout.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PRICELISTS_DIR = Path(__file__).resolve().parents[3] / "data" / "pricelists"


def slugify(name: str) -> str:
    return re.sub(r"\s+", "-", name.strip().lower())


def brand_display(brand_folder: str) -> str:
    """Convert folder name to display name (e.g. mercedes-benz -> Mercedes-Benz)."""
    return "-".join(word.capitalize() for word in brand_folder.split("-"))


def main() -> None:
    # key -> (list_price, record) — keep lowest list_price per (brand, model_key, variant_key, date)
    best: dict[tuple, tuple] = {}

    for json_path in sorted(PRICELISTS_DIR.glob("*/*/*.json")):
        try:
            data = json.loads(json_path.read_text())
        except Exception:
            continue

        meta = data.get("metadata", {})
        pricelist = data.get("pricelist", {})

        brand_folder = meta.get("brand_folder") or json_path.parts[-3]
        dealer_id = meta.get("dealer_id", "")
        pdf_date = meta.get("pdf_date", "")

        if not pdf_date:
            continue

        for car in pricelist.get("models", []):
            model_name = car.get("model_name", "").strip()
            category = car.get("category") or ""
            model_key = slugify(model_name)

            for variant in car.get("variants", []):
                variant_name = variant.get("variant_name", "").strip()
                variant_key = slugify(variant_name)
                vehicle_type = variant.get("vehicle_type") or "ICE"
                list_price = variant.get("list_price")
                final_price = variant.get("final_price")

                if list_price is None:
                    continue

                dedup_key = (brand_folder, model_key, variant_key, pdf_date)
                lp = int(list_price)

                if dedup_key not in best or lp < best[dedup_key][0]:
                    record = {
                        "date": pdf_date,
                        "brand": brand_folder,
                        "brand_display": brand_display(brand_folder),
                        "dealer_id": dealer_id,
                        "model": model_name,
                        "model_key": model_key,
                        "category": category,
                        "variant": variant_name,
                        "variant_key": variant_key,
                        "vehicle_type": vehicle_type,
                        "list_price": lp,
                        "final_price": int(final_price) if final_price is not None else None,
                    }
                    best[dedup_key] = (lp, record)

    snapshots = [record for _key, (_lp, record) in sorted(best.items())]

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": snapshots,
    }

    json.dump(output, sys.stdout, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
