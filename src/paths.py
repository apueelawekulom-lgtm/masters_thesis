import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

with open(ROOT / "config/paths.yaml") as f:
    PATHS = yaml.safe_load(f)


def get(chapter: str, key: str) -> Path:
    """Return an absolute path for a given chapter and key."""
    return ROOT / PATHS[chapter][key]
