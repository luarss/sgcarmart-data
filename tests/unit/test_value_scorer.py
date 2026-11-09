import json
from datetime import date

import pytest

from analysis.value_scorer import load_first_seen, score_listings

REFERENCE_DATE = date(2026, 11, 9)
COE_LOOKUP = {("2021-12", "Category A"): 57000, ("2026-11", "Category A"): 139001, ("2026-11", "Category B"): 132334}


def _listing(listing_id: str, posted_date: str = "08-Nov-2026", **overrides) -> dict:
    listing = {
        "id": listing_id,
        "title": f"Honda Jazz 1.5A {listing_id}",
        "price": 66000,
        "depreciation": 10900,
        "reg_date": "31-Dec-2021",
        "coe_left": "5y 1m",
        "mileage": 63000,
        "eng_cap": "1,332 cc",
        "owners": "1 Owner",
        "posted_date": posted_date,
    }
    listing.update(overrides)
    return listing


def _days_on_market(scored: list[dict]) -> dict[str, int]:
    return {row["id"]: row["days_on_market"] for row in scored}


@pytest.mark.unit
class TestDaysOnMarket:
    def test_uses_posted_date_without_snapshot_history(self):
        scored, _ = score_listings([_listing("1"), _listing("2", price=68000)], COE_LOOKUP, REFERENCE_DATE)

        assert _days_on_market(scored) == {"1": 1, "2": 1}

    def test_reposted_listing_uses_first_snapshot_date(self):
        listings = [_listing("1"), _listing("2", price=68000)]
        first_seen = {"1": date(2026, 10, 1)}

        scored, _ = score_listings(listings, COE_LOOKUP, REFERENCE_DATE, first_seen)

        assert _days_on_market(scored) == {"1": 39, "2": 1}

    def test_earlier_posted_date_wins_over_later_first_seen(self):
        listings = [_listing("1", posted_date="01-Sep-2026"), _listing("2", price=68000)]
        first_seen = {"1": date(2026, 10, 1)}

        scored, _ = score_listings(listings, COE_LOOKUP, REFERENCE_DATE, first_seen)

        assert _days_on_market(scored)["1"] == 69


@pytest.mark.unit
class TestLoadFirstSeen:
    def test_records_first_snapshot_per_listing(self, tmp_path):
        snapshots = {
            "2026-11-01": ["a"],
            "2026-11-02": ["a", "b"],
            "2026-11-10": ["c"],
        }
        for snapshot_date, ids in snapshots.items():
            payload = {"date": snapshot_date, "listings": {listing_id: {} for listing_id in ids}}
            (tmp_path / f"{snapshot_date}.json").write_text(json.dumps(payload))
        (tmp_path / "latest.json").write_text(json.dumps({"z": {}}))
        (tmp_path / "watchlist.json").write_text("{}")

        first_seen = load_first_seen(tmp_path, REFERENCE_DATE)

        assert first_seen == {"a": date(2026, 11, 1), "b": date(2026, 11, 2)}

