"""
One-shot helper: discover Google Place IDs for CPO dealers via Text Search.

Run once, review the candidates, then manually confirm the correct place_id
in data/dealer_review_sources.json.

Usage:
    uv run python scripts/find_place_ids.py
    uv run python scripts/find_place_ids.py --write   # auto-write top result per dealer
"""
import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "analysis" / ".env")

from sgcarmart.core.maps import (  # noqa: E402
    DEALER_SOURCES_FILE,
    PlacesClient,
    UsageTracker,
    get_api_key,
    load_dealer_sources,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Find Google Place IDs for CPO dealers")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the top search result place_id back to dealer_review_sources.json",
    )
    args = parser.parse_args()

    api_key = get_api_key()
    if not api_key:
        raise SystemExit("GOOGLE_MAPS_API_KEY not set. Add it to analysis/.env or the environment.")

    sources = load_dealer_sources()
    tracker = UsageTracker()
    client = PlacesClient(api_key, tracker)

    updates: dict[str, str] = {}

    for source_id, config in sources.items():
        if config.get("place_id"):
            print(f"[{source_id}] already configured: {config['place_id']}")
            continue

        query = config["search_query"]
        print(f"\n[{source_id}] searching: {query!r}")
        try:
            places = client.search_place(query)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        if not places:
            print("  no results")
            continue

        for i, p in enumerate(places[:3]):
            pid = p.get("id", "")
            name = p.get("displayName", {}).get("text", "")
            addr = p.get("formattedAddress", "")
            marker = "  →" if i == 0 else "   "
            print(f"{marker} [{i+1}] {name} | {addr} | {pid}")

        if args.write and places:
            top = places[0]
            updates[source_id] = top["id"]
            print(f"  will write: {top['id']}")

    print(f"\nQuota used this month: {tracker.calls_this_month}/{tracker.remaining + tracker.calls_this_month}")

    if args.write and updates:
        sources = load_dealer_sources()  # reload fresh
        for source_id, place_id in updates.items():
            sources[source_id]["place_id"] = place_id
        with open(DEALER_SOURCES_FILE, "w") as f:
            json.dump(sources, f, indent=2)
        print(f"\nWrote {len(updates)} place_id(s) to {DEALER_SOURCES_FILE}")
        print("Review the file and correct any mismatches before committing.")


if __name__ == "__main__":
    main()
