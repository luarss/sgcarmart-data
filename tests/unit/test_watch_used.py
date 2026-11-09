import json

import pytest

from scripts import watch_used


def _listings(count: int) -> dict:
    return {str(i): {"id": str(i), "title": f"Car {i}", "price": 70000} for i in range(count)}


@pytest.fixture
def watch_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(watch_used, "DATA_DIR", tmp_path)
    monkeypatch.setattr(watch_used, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(watch_used, "FETCH_RETRY_WAIT_MULTIPLIER", 0)
    directory = tmp_path / "test-watch"
    directory.mkdir()
    return directory


def _config() -> dict:
    return {"name": "test-watch", "filters": {}, "max_pages": 1}


def _write_previous(watch_dir, count: int) -> None:
    (watch_dir / "latest.json").write_text(json.dumps(_listings(count)))


@pytest.mark.unit
class TestPartialScrapeGuard:
    def test_minimum_expected_is_half_of_previous(self):
        assert watch_used.minimum_expected_listings(2000) == 1000
        assert watch_used.minimum_expected_listings(3) == 2
        assert watch_used.minimum_expected_listings(0) == 0

    def test_partial_fetch_raises_and_writes_nothing(self, watch_dir, monkeypatch):
        _write_previous(watch_dir, 2000)
        calls = []

        def fake_fetch(filters, max_pages):
            calls.append(1)
            return _listings(190)

        monkeypatch.setattr(watch_used, "_fetch_current_listings", fake_fetch)

        with pytest.raises(watch_used.DegenerateFetchError, match="partial scrape"):
            watch_used.run_watch(_config())

        assert len(calls) == watch_used.FETCH_RETRY_ATTEMPTS
        assert len(json.loads((watch_dir / "latest.json").read_text())) == 2000
        assert sorted(path.name for path in watch_dir.glob("*.json")) == ["config.json", "latest.json"]

    def test_retry_recovers_from_partial_fetch(self, watch_dir, monkeypatch):
        _write_previous(watch_dir, 2000)
        results = iter([_listings(190), _listings(1990)])
        monkeypatch.setattr(watch_used, "_fetch_current_listings", lambda filters, max_pages: next(results))

        summary = watch_used.run_watch(_config())

        assert summary["current_count"] == 1990
        assert len(json.loads((watch_dir / "latest.json").read_text())) == 1990

    def test_allow_partial_accepts_small_result(self, watch_dir, monkeypatch):
        _write_previous(watch_dir, 2000)
        monkeypatch.setattr(watch_used, "_fetch_current_listings", lambda filters, max_pages: _listings(190))

        summary = watch_used.run_watch(_config(), allow_partial=True)

        assert summary["current_count"] == 190

    def test_first_run_without_previous_accepts_any_nonempty_result(self, watch_dir, monkeypatch):
        monkeypatch.setattr(watch_used, "_fetch_current_listings", lambda filters, max_pages: _listings(5))

        summary = watch_used.run_watch(_config())

        assert summary["current_count"] == 5

    def test_empty_fetch_still_raises(self, watch_dir, monkeypatch):
        _write_previous(watch_dir, 2000)
        monkeypatch.setattr(watch_used, "_fetch_current_listings", lambda filters, max_pages: {})

        with pytest.raises(watch_used.DegenerateFetchError, match="0 listings"):
            watch_used.run_watch(_config(), allow_partial=True)

    def test_returns_largest_short_result(self, monkeypatch):
        monkeypatch.setattr(watch_used, "FETCH_RETRY_WAIT_MULTIPLIER", 0)
        results = iter([_listings(100), _listings(300), _listings(200)])
        monkeypatch.setattr(watch_used, "_fetch_current_listings", lambda filters, max_pages: next(results))

        assert len(watch_used.fetch_current_listings({}, 1, min_expected=1000)) == 300
