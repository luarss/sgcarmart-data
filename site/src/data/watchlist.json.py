"""Data loader: passes watchlist.json through to Observable."""
import json
import sys
from pathlib import Path

watchlist_path = (
    Path(__file__).resolve().parents[3]
    / "data" / "used_cars" / "sgd-passenger" / "watchlist.json"
)
data = json.loads(watchlist_path.read_text())
json.dump(data, sys.stdout, ensure_ascii=False)
