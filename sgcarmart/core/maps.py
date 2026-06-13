"""
Google Maps Places API client for CPO dealer reviews.

Quota model
-----------
Places API Place Details Pro tier: 5,000 free requests/month.
We enforce a 50% ceiling (2,500/month) tracked locally in data/api_usage/google_maps.json.

Fields fetched: displayName, rating, userRatingCount (all Pro-tier fields).
Review text requires the Enterprise tier, which we do not use.

Google does not expose a public endpoint for remaining free-tier credits.
The authoritative view is Google Cloud Console → Billing → Credits.
"""
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import requests

# --- Quota constants ----------------------------------------------------------

_MONTHLY_FREE_REQUESTS = 5_000   # Places API Place Details Pro free tier
MONTHLY_QUOTA_LIMIT = int(_MONTHLY_FREE_REQUESTS * 0.50)  # 2_500

USAGE_FILE = Path("data/api_usage/google_maps.json")
DEALER_SOURCES_FILE = Path("data/dealer_review_sources.json")

PLACES_API_BASE = "https://places.googleapis.com/v1"

# Pro-tier fields (reviews requires Enterprise, which we do not use)
_DETAIL_FIELDS = "displayName,rating,userRatingCount"
_SEARCH_FIELDS = "places.id,places.displayName,places.formattedAddress"

# Singapore bounding box for text search
_SG_BOUNDS = {
    "rectangle": {
        "low": {"latitude": 1.15, "longitude": 103.60},
        "high": {"latitude": 1.47, "longitude": 104.00},
    }
}


# --- Exceptions ---------------------------------------------------------------


class QuotaExceededError(RuntimeError):
    pass


# --- Usage tracker ------------------------------------------------------------


class UsageTracker:
    """Persists monthly API call counts in a JSON file."""

    def __init__(self, usage_file: Path = USAGE_FILE):
        self._file = usage_file
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict:
        if self._file.exists():
            with open(self._file) as f:
                return json.load(f)
        return {"month": "", "calls": 0}

    def _save(self) -> None:
        with open(self._file, "w") as f:
            json.dump(self._state, f, indent=2)

    def _current_month(self) -> str:
        return date.today().strftime("%Y-%m")

    def _maybe_reset(self) -> None:
        current = self._current_month()
        if self._state.get("month") != current:
            self._state = {"month": current, "calls": 0}
            self._save()

    @property
    def calls_this_month(self) -> int:
        self._maybe_reset()
        return self._state["calls"]

    @property
    def remaining(self) -> int:
        return max(0, MONTHLY_QUOTA_LIMIT - self.calls_this_month)

    def check_quota(self) -> None:
        """Raise QuotaExceededError if at or above the 50% ceiling."""
        if self.calls_this_month >= MONTHLY_QUOTA_LIMIT:
            raise QuotaExceededError(
                f"Monthly limit reached: {self.calls_this_month}/{MONTHLY_QUOTA_LIMIT} calls "
                f"(50% of ~{_MONTHLY_FREE_REQUESTS} free requests). Resets next month."
            )

    def increment(self, n: int = 1) -> None:
        self._maybe_reset()
        self._state["calls"] += n
        self._save()

    def summary(self) -> dict:
        self._maybe_reset()
        return {
            "month": self._state["month"],
            "calls": self._state["calls"],
            "limit": MONTHLY_QUOTA_LIMIT,
            "remaining": self.remaining,
            "free_tier_total": _MONTHLY_FREE_REQUESTS,
            "note": "Authoritative remaining balance: Google Cloud Console → Billing → Credits",
        }


# --- Places API client --------------------------------------------------------


class PlacesClient:
    def __init__(self, api_key: str, tracker: UsageTracker | None = None):
        self._key = api_key
        self._tracker = tracker or UsageTracker()

    def _headers(self, field_mask: str) -> dict:
        return {
            "X-Goog-Api-Key": self._key,
            "X-Goog-FieldMask": field_mask,
            "Content-Type": "application/json",
        }

    def get_place_details(self, place_id: str) -> dict:
        """Fetch place details (1 API call, Basic SKU)."""
        self._tracker.check_quota()
        url = f"{PLACES_API_BASE}/places/{place_id}"
        resp = requests.get(url, headers=self._headers(_DETAIL_FIELDS), timeout=10)
        self._tracker.increment()
        resp.raise_for_status()
        return resp.json()

    def search_place(self, query: str) -> list[dict]:
        """Text search to find candidate place IDs (1 API call, Atmosphere SKU)."""
        self._tracker.check_quota()
        url = f"{PLACES_API_BASE}/places:searchText"
        resp = requests.post(
            url,
            headers=self._headers(_SEARCH_FIELDS),
            json={"textQuery": query, "locationRestriction": _SG_BOUNDS},
            timeout=10,
        )
        self._tracker.increment()
        resp.raise_for_status()
        return resp.json().get("places", [])


# --- Public helpers -----------------------------------------------------------


def load_dealer_sources(path: Path = DEALER_SOURCES_FILE) -> dict:
    with open(path) as f:
        return json.load(f)


def fetch_all_dealer_reviews(
    api_key: str,
    sources_path: Path = DEALER_SOURCES_FILE,
    tracker: UsageTracker | None = None,
) -> dict:
    """
    Fetch Google Maps reviews for all dealers that have a place_id configured.
    Returns a dict keyed by source_id.
    """
    sources = load_dealer_sources(sources_path)
    tracker = tracker or UsageTracker()
    client = PlacesClient(api_key, tracker)

    results: dict[str, dict] = {}
    for source_id, config in sources.items():
        place_id = config.get("place_id")
        if not place_id:
            print(f"  skip {source_id}: no place_id (run scripts/find_place_ids.py)")
            results[source_id] = {"status": "not_configured"}
            continue

        try:
            data = client.get_place_details(place_id)
            results[source_id] = {
                "status": "ok",
                "fetched_at": datetime.now(UTC).isoformat(),
                "place_id": place_id,
                "name": config["name"],
                "rating": data.get("rating"),
                "user_rating_count": data.get("userRatingCount"),
            }
            rating = data.get("rating", "–")
            count = data.get("userRatingCount", 0)
            print(f"  ✓ {source_id}: {rating} ★ ({count} reviews)")
        except QuotaExceededError as e:
            print(f"  ✗ {source_id}: quota exceeded — {e}")
            results[source_id] = {"status": "quota_exceeded"}
            break
        except Exception as e:
            print(f"  ✗ {source_id}: {e}")
            results[source_id] = {"status": "error", "error": str(e)}

    return results


def save_reviews(reviews: dict, tracker: UsageTracker, output_dir: str = "data/cpo") -> str:
    """Save reviews snapshot and update latest.json."""
    today = date.today().isoformat()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    payload = {
        "date": today,
        "saved_at": datetime.now(UTC).isoformat(),
        "quota_usage": tracker.summary(),
        "reviews": reviews,
    }

    dated_path = out / f"reviews_{today}.json"
    with open(dated_path, "w") as f:
        json.dump(payload, f, indent=2)

    latest_path = out / "reviews_latest.json"
    with open(latest_path, "w") as f:
        json.dump(payload, f, indent=2)

    return str(dated_path)




def get_api_key() -> str | None:
    return os.getenv("GOOGLE_MAPS_API_KEY")
