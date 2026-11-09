import json
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WATCH_DIR = PROJECT_ROOT / "data" / "used_cars" / "sgd-passenger"
COE_DIR = PROJECT_ROOT / "data" / "coe"
SNAPSHOT_GLOB = "20[2-9][0-9]-[01][0-9]-[0-3][0-9].json"
COE_START_YEAR = 2016
PARTIAL_SCRAPE_RATIO = 0.5
TRAILING_WINDOW = 14


def load_snapshot_prices():
    snapshots = []
    for snapshot_file in sorted(WATCH_DIR.glob(SNAPSHOT_GLOB)):
        listings = json.loads(snapshot_file.read_text()).get("listings", {})
        prices = {listing_id: entry.get("price") for listing_id, entry in listings.items() if isinstance(entry, dict)}
        snapshots.append((snapshot_file.stem, prices))
    return snapshots


def is_partial(count, healthy_counts):
    window = healthy_counts[-TRAILING_WINDOW:]
    if not window:
        return count == 0
    return count < statistics.median(window) * PARTIAL_SCRAPE_RATIO


def summarise_day(snapshot_date, prices, previous_prices):
    valid_prices = [price for price in prices.values() if price]
    carried_over = [listing_id for listing_id in prices if listing_id in previous_prices]
    drops = [
        previous_prices[listing_id] - prices[listing_id]
        for listing_id in carried_over
        if prices[listing_id] and previous_prices[listing_id] and prices[listing_id] < previous_prices[listing_id]
    ]
    return {
        "date": snapshot_date,
        "count": len(prices),
        "median_price": statistics.median(valid_prices) if valid_prices else None,
        "new_listings": len(prices) - len(carried_over) if previous_prices else None,
        "price_drops": len(drops) if previous_prices else None,
        "median_drop": statistics.median(drops) if drops else None,
        "partial": False,
    }


def load_daily_snapshots():
    days = []
    healthy_counts = []
    previous_prices = {}
    for snapshot_date, prices in load_snapshot_prices():
        if is_partial(len(prices), healthy_counts):
            days.append({"date": snapshot_date, "count": len(prices), "partial": True})
            continue
        days.append(summarise_day(snapshot_date, prices, previous_prices))
        healthy_counts.append(len(prices))
        previous_prices = prices
    return days


def load_coe_series():
    series = []
    for coe_file in sorted(COE_DIR.glob("coe_results_*.json")):
        year = int(coe_file.stem.rsplit("_", 1)[-1])
        if year < COE_START_YEAR:
            continue
        for record in json.loads(coe_file.read_text()):
            if record["vehicle_class"] not in ("Category A", "Category B"):
                continue
            series.append(
                {
                    "month": record["month"],
                    "round": int(record["bidding_no"]),
                    "category": record["vehicle_class"],
                    "premium": int(str(record["premium"]).replace(",", "")),
                }
            )
    return sorted(series, key=lambda point: (point["month"], point["round"], point["category"]))


json.dump(
    {"days": load_daily_snapshots(), "coe": load_coe_series()},
    sys.stdout,
    separators=(",", ":"),
)
