"""
Fetch Google Maps ratings for all configured CPO dealers and save to data/cpo/.

Usage:
    uv run python scripts/fetch_reviews.py
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "analysis" / ".env")

from sgcarmart.core.maps import (  # noqa: E402
    UsageTracker,
    fetch_all_dealer_reviews,
    get_api_key,
    save_reviews,
)


def main() -> None:
    api_key = get_api_key()
    if not api_key:
        raise SystemExit("GOOGLE_MAPS_API_KEY not set. Add it to analysis/.env or the environment.")

    tracker = UsageTracker()
    limit = tracker.calls_this_month + tracker.remaining
    print(f"Quota: {tracker.calls_this_month}/{limit} used this month")

    print("\nFetching dealer reviews...")
    reviews = fetch_all_dealer_reviews(api_key, tracker=tracker)

    path = save_reviews(reviews, tracker)
    print(f"\nSaved to {path}")
    print(f"Quota after: {tracker.calls_this_month}/{limit}")


if __name__ == "__main__":
    main()
