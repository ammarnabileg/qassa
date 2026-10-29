"""Every DomainError code raised by the backend has an Arabic and English message in the web app,
otherwise staff see a generic 'unknown error'."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_error_code_is_translated():
    codes = set()
    for f in (ROOT / "backend" / "apps").rglob("*.py"):
        if "migrations" not in f.parts:
            codes |= set(re.findall(r'DomainError\([^)]*?code="([a-z_]+)"', f.read_text(encoding="utf-8"), re.S))
    assert len(codes) > 50
    for lang in ("ar", "en"):
        errors = json.loads((ROOT / "frontend" / "src" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))["errors"]
        missing = sorted(codes - errors.keys())
        assert not missing, f"{lang}: {missing}"
