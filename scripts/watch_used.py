"""
Daily used car listing tracker — idempotent snapshot & diff.

Usage:
    uv run python scripts/watch_used.py
    uv run python scripts/watch_used.py --name my-watch --json
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sgcarmart.core.used import SEARCH_PARAMS, UsedCarSearch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "used_cars"

MAX_SAFE_PAGES = 100  # upper bound to prevent unbounded loops from user config

# COE-renewed car title patterns — these cars have had their 10-yr COE extended,
# so the reg_date reflects the renewal date, not the car's true age.
_COE_RENEWED_RE = re.compile(
    r"COE\s+(?:till?|until|to)\s+\d|New\s+(?:5|10)[-\s]?yr\s+COE|\bCOE\s+renewed\b|"
    r"\bRenewed\s+COE\b",
    re.IGNORECASE,
)

# ── Tunable watch configuration ─────────────────────────────────────────────
# Filter keys must match SEARCH_PARAMS (see sgcarmart/core/used.py for full list).
# Modify these values to change what listings are tracked.
DEFAULT_CONFIG = {
    "name": "sgd-passenger",
    "filters": {
        "min_price": 60000,
        "max_price": 100000,
        "year_from": 2016,
        "vts": 2,  # "All Passenger Cars" — excludes vans/commercial
        "avl": "a",
        "sortby": "REG_DESC",
        "limit": 100,
    },
    "max_pages": 50,
    "exclude_coe_renewed": True,
}


def _listing_id(href: str) -> str:
    """Extract numeric listing ID from an info URL."""
    if not href:
        return ""
    # e.g. /used-cars/info/mercedes-benz-c-class-...-1504441/
    import re

    m = re.search(r"-(\d{6,})/", href)
    return m.group(1) if m else ""


def _capture_debug(search, watch_dir: Path, page_num: int) -> None:
    """Capture screenshot and HTML when no listings found — CI debugging."""
    debug_dir = watch_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        search.page.screenshot(path=str(debug_dir / f"page-{page_num}-{ts}.png"))
    except Exception as e:
        print(f"DEBUG: screenshot failed: {e}")
    try:
        html = search.page.content()
        (debug_dir / f"page-{page_num}-{ts}.html").write_text(html)
    except Exception as e:
        print(f"DEBUG: html capture failed: {e}")
    print(f"DEBUG: no listings on page {page_num}, url={search.page.url}")


def _filter_coe_renewed(current: dict) -> dict:
    """Remove COE-renewed cars from listing dict (title-based check)."""
    before = len(current)
    filtered = {lid: c for lid, c in current.items() if not _COE_RENEWED_RE.search(c["title"])}
    if before != len(filtered):
        print(f"Excluded {before - len(filtered)} COE-renewed cars")
    return filtered


def _compute_diff(current, previous):
    """Compute added, removed, and price-change listings between snapshots."""
    current_ids = set(current.keys())
    previous_ids = set(previous.keys())

    added_ids = current_ids - previous_ids
    removed_ids = previous_ids - current_ids
    unchanged_ids = current_ids & previous_ids

    price_changes = []
    for lid in unchanged_ids:
        prev_price = previous[lid].get("price")
        curr_price = current[lid].get("price")
        if prev_price != curr_price and prev_price is not None and curr_price is not None:
            price_changes.append(
                {
                    "id": lid,
                    "title": current[lid]["title"],
                    "url": current[lid]["url"],
                    "previous_price": prev_price,
                    "current_price": curr_price,
                }
            )

    return added_ids, removed_ids, price_changes


def _fetch_current_listings(filters, max_pages, watch_dir):
    """Fetch all listings across pages into a dict keyed by listing ID."""
    current = {}
    with UsedCarSearch(headless=True) as s:
        s.search(**filters)
        for page_num in range(max_pages):
            cards = s.get_listings()
            if not cards:
                _capture_debug(s, watch_dir, page_num)
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
    return current


def run_watch(config: dict) -> dict:
    """Fetch current listings, diff against previous snapshot, save new snapshot."""
    name = config["name"]
    filters = config["filters"]
    max_pages = min(config.get("max_pages", 10), MAX_SAFE_PAGES)

    unknown = [k for k in filters if k not in SEARCH_PARAMS]
    if unknown:
        raise ValueError(f"Unknown filter keys: {unknown}. Valid keys: {list(SEARCH_PARAMS)}")

    watch_dir = DATA_DIR / name
    watch_dir.mkdir(parents=True, exist_ok=True)

    with open(watch_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2, default=str)

    current = _fetch_current_listings(filters, max_pages, watch_dir)

    if config.get("exclude_coe_renewed"):
        current = _filter_coe_renewed(current)

    previous_path = watch_dir / "latest.json"
    previous = {}
    if previous_path.exists():
        with open(previous_path) as f:
            previous = json.load(f)

    added_ids, removed_ids, price_changes = _compute_diff(current, previous)

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

    with open(previous_path, "w") as f:
        json.dump(current, f, indent=2, default=str)

    return {
        "watch": name,
        "date": today,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters,
        "current_count": len(current),
        "previous_count": len(previous),
        "added": len(added_ids),
        "removed": len(removed_ids),
        "unchanged": len(current) - len(added_ids),
        "price_changes": len(price_changes),
        "added_ids": sorted(added_ids),
        "removed_ids": sorted(removed_ids),
        "price_change_details": price_changes,
        "snapshot_file": str(snapshot_path.relative_to(PROJECT_ROOT)),
    }


def _load_config(name):
    config_path = DATA_DIR / name / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    if name != DEFAULT_CONFIG["name"]:
        return {**DEFAULT_CONFIG, "name": name}
    return DEFAULT_CONFIG


def _print_summary_text(summary):
    print(f"Watch: {summary['watch']}")
    print(f"Date:  {summary['date']}")
    print(f"Filters: {json.dumps(summary['filters'])}")
    print(
        f"Total: {summary['current_count']} listings "
        f"(+{summary['added']} new, "
        f"-{summary['removed']} removed, "
        f"={summary['unchanged']} unchanged)"
    )
    if summary["price_changes"]:
        print(f"Price changes: {summary['price_changes']}")
        for pc in summary["price_change_details"][:10]:
            print(f"  {pc['title']}: ${pc['previous_price']:,} → ${pc['current_price']:,}")
    if summary["added_ids"]:
        print(f"\nNew: {', '.join(summary['added_ids'][:20])}")
        if len(summary["added_ids"]) > 20:
            print(f"  ... and {len(summary['added_ids']) - 20} more")
    print(f"\nSnapshot: {summary['snapshot_file']}")


def main():
    parser = argparse.ArgumentParser(description="Track used car listings over time")
    parser.add_argument("--name", default=DEFAULT_CONFIG["name"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    config = _load_config(args.name)
    summary = run_watch(config)

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        _print_summary_text(summary)

    return summary


if __name__ == "__main__":
    main()
