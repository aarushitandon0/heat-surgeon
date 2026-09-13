"""Settings and cited constants: USE_LIVE_DATA, cost ranges, albedo values, thresholds.

Every constant here is either cited in docs/sources.md or marked `# ASSUMPTION:`
and logged in docs/methodology.md (CLAUDE.md rule 7).
"""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "fixtures"
CACHE_DIR = FIXTURES_DIR / "cache"
STREETS_DIR = FIXTURES_DIR / "streets"


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes"}


# Offline by default: the demo path is the fixture path (CLAUDE.md rule 4).
# Set USE_LIVE_DATA=true to let cache misses reach the network.
USE_LIVE_DATA = _env_flag("USE_LIVE_DATA", False)

# Design grid cap. Set by SPEC.md §6.1: a street needing more cells raises rather
# than being coarsened.
MAX_DESIGN_GRID_CELLS = 4000
