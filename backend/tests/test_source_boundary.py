"""Vendor SDKs are imported only by their adapter module (CLAUDE.md rule 3)."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

ALLOWED_IMPORTERS = {
    "ee": {"data/earth_engine.py"},
    "pystac_client": {"data/planetary.py"},
    "planetary_computer": {"data/planetary.py"},
}


def test_vendor_sdks_are_imported_only_by_their_adapter():
    offenders = []
    for module in APP.rglob("*.py"):
        relative = module.relative_to(APP).as_posix()
        source = module.read_text(encoding="utf-8")
        for sdk, allowed in ALLOWED_IMPORTERS.items():
            if relative not in allowed and re.search(rf"^\s*(import|from)\s+{sdk}\b", source, flags=re.M):
                offenders.append(f"{relative} imports {sdk}")
    assert offenders == []
