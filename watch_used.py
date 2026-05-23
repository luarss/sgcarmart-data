"""
Daily used car listing tracker — idempotent snapshot & diff.

Usage:
    uv run python watch_used.py
    uv run python watch_used.py --name my-watch --json
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sgcarmart.core.used import UsedCarSearch

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "used_cars"

# ── Tunable watch configuration ─────────────────────────────────────────────
# Modify these values to change what listings are tracked.
DEFAULT_CONFIG = {
    "name": "sgd-60k-80k-newest",
    "filters": {
        "min_price": 60000,
        "max_price": 80000,
        "year_from": 2016,         # exclude COE-renewed cars (only cars ≤10 yrs old)
        "avl": "a",                # available listings only
        "sortby": "REG_DESC",      # newest registration first
        "limit": 100,
    },
    "max_pages": 50,               # fetch all matching listings (100 × 50 = 5000 max)
}


def _listing_id(href: str) -> str:
    """Extract numeric listing ID from an info URL."""
    if not href:
        return ""
    # e.g. /used-cars/info/mercedes-benz-c-class-...-1504441/
    import re
    m = re.search(r"-(\d{6,})/", href)
    return m.group(1) if m else ""


def run_watch(config: dict) -> dict:
    """Fetch current listings, diff against previous snapshot, save new snapshot."""
    name = config["name"]
    filters = config["filters"]
    max_pages = config.get("max_pages", 10)

    watch_dir = DATA_DIR / name
    watch_dir.mkdir(parents=True, exist_ok=True)

    # Persist config
    with open(watch_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2, default=str)

    # Fetch current listings
    current = {}
    with UsedCarSearch(headless=True) as s:
        s.search(**filters)
        for _ in range(max_pages):
            cards = s.get_listings()
            if not cards:
                break
            for card in cards:
                lid = _listing_id(card.url)
                if lid:
                    current[lid] = {
                        "id": lid,
                        "title": card.title,
                        "url": card.url,
                        "price": card.price,
                        "depreciation": card.depreciation,
                        "reg_date": card.reg_date,
                        "coe_left": card.coe_left,
                        "mileage": card.mileage,
                        "eng_cap": card.eng_cap,
                        "owners": card.owners,
                        "is_direct_owner": card.is_direct_owner,
                        "is_premium_ad": card.is_premium_ad,
                        "dealer": card.dealer,
                        "posted_date": card.posted_date,
                        "description": card.description,
                    }
            if not s.next_page():
                break

    # Load previous snapshot
    previous_path = watch_dir / "latest.json"
    previous = {}
    if previous_path.exists():
        with open(previous_path) as f:
            previous = json.load(f)

    # Compute diff
    current_ids = set(current.keys())
    previous_ids = set(previous.keys())

    added_ids = current_ids - previous_ids
    removed_ids = previous_ids - current_ids
    unchanged_ids = current_ids & previous_ids

    # Detect price changes in surviving listings
    price_changes = []
    for lid in unchanged_ids:
        prev_price = previous[lid].get("price")
        curr_price = current[lid].get("price")
        if prev_price != curr_price and prev_price is not None and curr_price is not None:
            price_changes.append({
                "id": lid,
                "title": current[lid]["title"],
                "url": current[lid]["url"],
                "previous_price": prev_price,
                "current_price": curr_price,
            })

    # Write dated snapshot
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot = {
        "date": today,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters,
        "total_listings": len(current),
        "listings": current,
    }
    snapshot_path = watch_dir / f"{today}.json"
    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)

    # Update latest
    with open(previous_path, "w") as f:
        json.dump(current, f, indent=2, default=str)

    summary = {
        "watch": name,
        "date": today,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters,
        "current_count": len(current),
        "previous_count": len(previous),
        "added": len(added_ids),
        "removed": len(removed_ids),
        "unchanged": len(unchanged_ids),
        "price_changes": len(price_changes),
        "added_ids": sorted(added_ids),
        "removed_ids": sorted(removed_ids),
        "price_change_details": price_changes,
        "snapshot_file": str(snapshot_path.relative_to(PROJECT_ROOT)),
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Track used car listings over time")
    parser.add_argument("--name", default=DEFAULT_CONFIG["name"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config_path = DATA_DIR / args.name / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    else:
        config = DEFAULT_CONFIG
        if args.name != DEFAULT_CONFIG["name"]:
            config = {**DEFAULT_CONFIG, "name": args.name}

    summary = run_watch(config)

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(f"Watch: {summary['watch']}")
        print(f"Date:  {summary['date']}")
        print(f"Filters: {json.dumps(summary['filters'])}")
        print(f"Total: {summary['current_count']} listings "
              f"(+{summary['added']} new, "
              f"-{summary['removed']} removed, "
              f"={summary['unchanged']} unchanged)")
        if summary["price_changes"]:
            print(f"Price changes: {summary['price_changes']}")
            for pc in summary["price_change_details"][:10]:
                print(f"  {pc['title']}: ${pc['previous_price']:,} → ${pc['current_price']:,}")
        if summary["added_ids"]:
            print(f"\nNew: {', '.join(summary['added_ids'][:20])}")
            if len(summary['added_ids']) > 20:
                print(f"  ... and {len(summary['added_ids']) - 20} more")
        print(f"\nSnapshot: {summary['snapshot_file']}")

    return summary


if __name__ == "__main__":
    main()
