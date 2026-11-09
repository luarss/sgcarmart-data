import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from analysis.value_scorer import DEFAULT_WEIGHTS, load_and_score  # noqa: E402

WATCH_DIR = PROJECT_ROOT / "data" / "used_cars" / "sgd-passenger"
SNAPSHOT_GLOB = "20[2-9][0-9]-[01][0-9]-[0-3][0-9].json"

ROUNDED_FIELDS = {
    "price": 0,
    "depreciation": 0,
    "age_years": 2,
    "coe_years_left": 2,
    "mileage_km": 0,
    "annual_mileage": 0,
    "body_price": 0,
    "body_depreciation_rate": 4,
    "value_retention": 4,
    "body_price_per_coe_year": 0,
    "depreciation_per_cc": 2,
    "composite_score": 4,
}

PASSTHROUGH_FIELDS = [
    "id",
    "title",
    "brand",
    "url",
    "reg_date",
    "coe_category",
    "num_owners",
    "is_direct_owner",
    "days_on_market",
    "road_tax",
]

RAW_FIELDS = ["dealer", "eng_cap", "instalment", "is_import_used", "description"]


def load_price_histories(snapshot_files):
    histories = {}
    for snapshot_file in snapshot_files:
        snapshot_date = snapshot_file.stem
        listings = json.loads(snapshot_file.read_text()).get("listings", {})
        for listing_id, entry in listings.items():
            if not isinstance(entry, dict):
                continue
            price = entry.get("price")
            record = histories.setdefault(listing_id, {"first_seen": snapshot_date, "days_seen": 0, "prices": []})
            record["days_seen"] += 1
            record["last_seen"] = snapshot_date
            if price and (not record["prices"] or record["prices"][-1][1] != price):
                record["prices"].append([snapshot_date, price])
    return histories


def summarise_row(row, raw_listing, history):
    summary = {field: row.get(field) for field in PASSTHROUGH_FIELDS}
    for field, digits in ROUNDED_FIELDS.items():
        value = row.get(field)
        summary[field] = None if value is None else round(value, digits) if digits else round(value)
    summary["metric_scores"] = {metric: round(score, 4) for metric, score in row["metric_scores"].items()}
    for field in RAW_FIELDS:
        summary[field] = raw_listing.get(field)
    prices = history["prices"] if history else []
    summary["first_seen"] = history["first_seen"] if history else None
    summary["days_seen"] = history["days_seen"] if history else 1
    summary["price_history"] = prices
    summary["first_price"] = prices[0][1] if prices else summary["price"]
    summary["peak_price"] = max((price for _, price in prices), default=summary["price"])
    return summary


def main():
    watchlist = json.loads((WATCH_DIR / "watchlist.json").read_text())
    reference_date = date.fromisoformat(watchlist["reference_date"])
    scored, stats = load_and_score(PROJECT_ROOT, "sgd-passenger", reference_date)

    raw_listings = json.loads((WATCH_DIR / "latest.json").read_text())
    snapshot_files = sorted(WATCH_DIR.glob(SNAPSHOT_GLOB))
    histories = load_price_histories(snapshot_files)

    rows = [summarise_row(row, raw_listings.get(row["id"], {}), histories.get(row["id"])) for row in scored]
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row["percentile"] = round(1 - (rank - 1) / len(rows), 4)

    result = {
        "generated_at": watchlist["generated_at"],
        "reference_date": watchlist["reference_date"],
        "total_source_listings": stats["total_source_listings"],
        "scored_listings": stats["scored_listings"],
        "excluded": {name.removeprefix("excluded_"): n for name, n in stats.items() if name.startswith("excluded_")},
        "weights": DEFAULT_WEIGHTS,
        "coe": watchlist["coe_premiums_used"],
        "filters": json.loads(snapshot_files[-1].read_text()).get("filters", {}) if snapshot_files else {},
        "listings": rows,
    }
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))


main()
