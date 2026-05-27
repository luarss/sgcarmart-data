#!/usr/bin/env python3
"""
Daily value watchlist — ranks used car listings by composite value score.

Usage:
    uv run python watchlist.py                        # human-readable summary
    uv run python watchlist.py --json                 # JSON to stdout
    uv run python watchlist.py --name sgd-passenger   # named watch
    uv run python watchlist.py --top 50               # limit output rows
    uv run python watchlist.py --date 2026-05-27      # backfill a snapshot date
"""

import argparse
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

from analysis.value_scorer import DEFAULT_WEIGHTS, load_and_score, load_coe_lookup

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "used_cars"
DEFAULT_WATCH = "sgd-passenger"
DEFAULT_TOP = 100


def _serialise(obj):
    """JSON serialiser: dates -> ISO string, NaN/Inf -> null."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _format_price(v: int | None) -> str:
    if v is None:
        return "N/A"
    return f"${v:,}"


def _format_pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:.1%}"


def run_watchlist(
    watch_name: str = DEFAULT_WATCH,
    reference_date: date | None = None,
    top_n: int = DEFAULT_TOP,
) -> dict:
    """Run the value scoring pipeline and produce the watchlist output."""
    if reference_date is None:
        reference_date = date.today()

    source_file = DATA_DIR / watch_name / "latest.json"
    if not source_file.exists():
        raise FileNotFoundError(f"No data found for watch '{watch_name}' at {source_file}")

    scored, stats = load_and_score(PROJECT_ROOT, watch_name, reference_date)

    coe_lookup = load_coe_lookup(PROJECT_ROOT)
    latest_premiums: dict[str, dict] = {}
    for (ym, cat), prem in coe_lookup.items():
        if cat not in latest_premiums or ym > latest_premiums[cat]["month"]:
            latest_premiums[cat] = {"month": ym, "premium": prem}

    # Build output fields for top-N cars
    output_fields = [
        "id", "title", "brand", "url", "price", "depreciation",
        "reg_date", "age_years", "coe_years_left", "coe_category",
        "mileage_km", "annual_mileage", "num_owners",
        "is_direct_owner", "is_premium_ad",
        "body_price", "body_depreciation_rate", "value_retention",
        "depreciation_rate", "body_price_per_coe_year",
        "depreciation_per_km", "price_per_owner", "days_on_market",
        "composite_score", "metric_scores",
    ]

    top_listings = []
    for row in scored[:top_n]:
        entry = {k: row.get(k) for k in output_fields}
        entry["rank"] = row.get("rank", 0)  # will be overwritten
        top_listings.append(entry)

    # Assign ranks
    for i, entry in enumerate(top_listings):
        entry["rank"] = i + 1

    snapshot_name = f"{reference_date.isoformat()}.json"
    snapshot_path = DATA_DIR / watch_name / snapshot_name
    source_ref = str(snapshot_path.relative_to(PROJECT_ROOT)) if snapshot_path.exists() else "latest.json"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_date": reference_date.isoformat(),
        "source_snapshot": source_ref,
        "total_source_listings": stats["total_source_listings"],
        "scored_listings": stats["scored_listings"],
        "excluded": {
            "parse_errors": stats["excluded_parse_errors"],
            "brands": stats.get("excluded_brands", 0),
            "retro_models": stats.get("excluded_retro_models", 0),
            "opc": stats.get("excluded_opc", 0),
            "suspicious_metrics": stats["excluded_suspicious_metrics"],
            "low_body_price": stats["excluded_low_body_price"],
            "missing_fields": stats["excluded_missing_fields"],
        },
        "scoring_weights": DEFAULT_WEIGHTS,
        "coe_premiums_used": {
            "category_a_latest": latest_premiums.get("Category A"),
            "category_b_latest": latest_premiums.get("Category B"),
        },
        "top_listings": top_listings,
    }


def _print_summary(result: dict) -> None:
    """Print a human-readable summary of the watchlist."""
    stats = result
    print(f"Value Watchlist — {stats['reference_date']}")
    print(f"Generated: {stats['generated_at']}")
    print(f"Source:   {stats['source_snapshot']}")
    coe = stats["coe_premiums_used"]
    cat_a = coe.get("category_a_latest", {})
    cat_b = coe.get("category_b_latest", {})
    if cat_a:
        print(f"COE Cat A: ${cat_a['premium']:,} ({cat_a['month']})")
    if cat_b:
        print(f"COE Cat B: ${cat_b['premium']:,} ({cat_b['month']})")
    print()
    print(f"Scored: {stats['scored_listings']} / {stats['total_source_listings']} listings")
    excl = stats["excluded"]
    if any(excl.values()):
        parts = []
        if excl.get("brands"):
            parts.append(f"{excl['brands']} excluded brands")
        if excl.get("retro_models"):
            parts.append(f"{excl['retro_models']} retro/classic models")
        if excl.get("opc"):
            parts.append(f"{excl['opc']} OPC")
        if excl["parse_errors"]:
            parts.append(f"{excl['parse_errors']} parse errors")
        if excl["suspicious_metrics"]:
            parts.append(f"{excl['suspicious_metrics']} suspicious")
        if excl["low_body_price"]:
            parts.append(f"{excl['low_body_price']} low body price")
        if excl["missing_fields"]:
            parts.append(f"{excl['missing_fields']} missing fields")
        print(f"Excluded: {', '.join(parts)}")
    print()

    listings = stats["top_listings"]
    if not listings:
        print("No listings to display.")
        return

    print(f"Top {len(listings)} — Composite Value Score")
    print("-" * 100)
    print(
        f"{'#':>3}  {'Title':<45} {'Price':>10} {'BodyDepr':>8} "
        f"{'Retention':>9} {'Body$/yr':>9} {'Score':>6}"
    )
    print("-" * 100)
    for row in listings:
        title = row["title"][:44]
        print(
            f"{row['rank']:>3}. {title:<45} "
            f"{_format_price(row['price']):>10} "
            f"{_format_pct(row['body_depreciation_rate']):>8} "
            f"{_format_pct(row['value_retention']):>9} "
            f"{_format_price(int(row['body_price_per_coe_year'])) if row.get('body_price_per_coe_year') else 'N/A':>9} "
            f"{row['composite_score']:.3f}"
        )


def main() -> dict:
    parser = argparse.ArgumentParser(description="Generate value watchlist from used car listings")
    parser.add_argument("--name", default=DEFAULT_WATCH, help=f"Watch name (default: {DEFAULT_WATCH})")
    parser.add_argument("--date", type=str, default=None, help="Reference date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help=f"Number of top listings to include (default: {DEFAULT_TOP})")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout instead of summary")
    args = parser.parse_args()

    ref_date = date.fromisoformat(args.date) if args.date else date.today()

    result = run_watchlist(watch_name=args.name, reference_date=ref_date, top_n=args.top)

    watch_dir = DATA_DIR / args.name
    watch_dir.mkdir(parents=True, exist_ok=True)
    output_path = watch_dir / "watchlist.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=_serialise)
    print(f"Saved: {output_path.relative_to(PROJECT_ROOT)}")

    if args.json:
        print(json.dumps(result, indent=2, default=_serialise))
    else:
        _print_summary(result)

    return result


if __name__ == "__main__":
    main()
