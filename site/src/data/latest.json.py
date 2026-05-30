"""Data loader: extracts summary stats from latest.json for hero section."""
import json
import re
import sys
from pathlib import Path
from collections import Counter

latest_path = (
    Path(__file__).resolve().parents[3]
    / "data" / "used_cars" / "sgd-passenger" / "latest.json"
)

if not latest_path.exists():
    json.dump({"error": "latest.json not found"}, sys.stdout)
    sys.exit(0)

raw = json.loads(latest_path.read_text())
listings = [v for v in raw.values() if isinstance(v, dict) and "price" in v]


def parse_mileage(val):
    """Parse '83,000 km' -> 83000"""
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"[\d,]+", str(val))
    return float(m.group().replace(",", "")) if m else 0


def parse_number(val):
    """Parse a number from a string, handling commas."""
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"[\d,]+\.?\d*", str(val))
    return float(m.group().replace(",", "")) if m else 0


def parse_owners(val):
    """Parse '1 Owner, ...' or '3' -> 3"""
    if isinstance(val, (int, float)):
        return int(val)
    m = re.match(r"(\d+)", str(val))
    return int(m.group(1)) if m else 0


prices = []
depreciations = []
mileages = []
owner_counts = []
brands = Counter()

for l in listings:
    price = l.get("price", 0) or 0
    depr = l.get("depreciation", 0) or 0
    if price:
        prices.append(price)
    if depr:
        depreciations.append(depr)

    mileage = parse_mileage(l.get("mileage", 0))
    if mileage:
        mileages.append(mileage)

    owners = parse_owners(l.get("owners", 0))
    if owners:
        owner_counts.append(owners)

    title = l.get("title", "")
    brand = title.split()[0] if title else "Unknown"
    brands[brand] += 1


def pct(sorted_vals, p):
    n = len(sorted_vals)
    if n == 0:
        return 0
    return sorted_vals[min(int(n * p / 100), n - 1)]


sp = sorted(prices)
sd = sorted(depreciations)

summary = {
    "total_listings": len(listings),
    "price_stats": {
        "min": sp[0] if sp else 0,
        "p25": pct(sp, 25),
        "median": pct(sp, 50),
        "p75": pct(sp, 75),
        "max": sp[-1] if sp else 0,
        "mean": round(sum(prices) / len(prices)) if prices else 0,
    },
    "depreciation_stats": {
        "min": sd[0] if sd else 0,
        "median": pct(sd, 50),
        "max": sd[-1] if sd else 0,
        "mean": round(sum(depreciations) / len(depreciations)) if depreciations else 0,
    },
    "avg_mileage": round(sum(mileages) / len(mileages)) if mileages else 0,
    "avg_owners": round(sum(owner_counts) / len(owner_counts), 1) if owner_counts else 0,
    "top_brands": [
        {"brand": b, "count": c}
        for b, c in brands.most_common(15)
    ],
    "unique_brands": len(brands),
}

json.dump(summary, sys.stdout, ensure_ascii=False)
