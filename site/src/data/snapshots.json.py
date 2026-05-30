"""Data loader: aggregates daily snapshots into compact time-series."""
import json
import sys
from pathlib import Path
from datetime import datetime

snapshot_dir = (
    Path(__file__).resolve().parents[3]
    / "data" / "used_cars" / "sgd-passenger"
)

dates = []
daily_stats = []
listings_index = {}

for f in sorted(snapshot_dir.glob("20[2-9][0-9]-[01][0-9]-[0-3][0-9].json")):
    date_str = f.stem
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        continue

    raw = json.loads(f.read_text())
    listing_dict = raw.get("listings", raw)
    # remove metadata keys
    meta = {"date", "fetched_at", "filters", "total_listings", "listings"}
    ids = [k for k in listing_dict if k not in meta]

    dates.append(date_str)

    prices = []
    for lid in ids:
        entry = listing_dict[lid]
        if not isinstance(entry, dict):
            continue
        price = entry.get("price", 0) or 0
        depr = entry.get("depreciation", 0) or 0
        title = entry.get("title", "")
        prices.append(price)

        if lid not in listings_index:
            listings_index[lid] = {
                "id": lid,
                "title": title,
                "url": entry.get("url", ""),
                "first_seen": date_str,
                "last_seen": date_str,
                "history": [],
            }
        else:
            listings_index[lid]["last_seen"] = date_str

        listings_index[lid]["history"].append({
            "date": date_str,
            "price": price,
            "depreciation": depr,
        })

    daily_stats.append({
        "date": date_str,
        "count": len(ids),
        "avg_price": round(sum(prices) / len(prices)) if prices else 0,
        "min_price": min(prices) if prices else 0,
        "max_price": max(prices) if prices else 0,
    })

# Filter to listings that appear in multiple snapshots (for price tracking)
tracked = [
    v for v in listings_index.values()
    if len(v["history"]) >= 2
]

result = {
    "dates": dates,
    "date_count": len(dates),
    "daily_stats": daily_stats,
    "tracked_listings": tracked,
    "total_listings_tracked": len(listings_index),
    "multi_day_listings": len(tracked),
}

json.dump(result, sys.stdout, ensure_ascii=False)
