import hashlib
import json
import threading
from pathlib import Path

MANIFEST_PATH = Path("data/pricelists/manifest.json")

_manifest: dict[str, str] = {}
_lock = threading.Lock()


def load(path: Path = MANIFEST_PATH) -> None:
    global _manifest
    if path.exists():
        with open(path) as f:
            _manifest = json.load(f)
    else:
        _manifest = {}


def save(path: Path = MANIFEST_PATH) -> None:
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(_manifest, f, indent=2, sort_keys=True)


def is_known(rel_path: str) -> bool:
    return rel_path in _manifest


def record(rel_path: str, content: bytes) -> None:
    md5 = hashlib.md5(content).hexdigest()
    with _lock:
        _manifest[rel_path] = md5
