"""Settings and cited constants: USE_LIVE_DATA, cost ranges, albedo values, thresholds.

Every constant here is either cited in docs/sources.md or marked `# ASSUMPTION:`
and logged in docs/methodology.md (CLAUDE.md rule 7).
"""

# Design grid cap. Set by SPEC.md §6.1: a street needing more cells raises rather
# than being coarsened.
MAX_DESIGN_GRID_CELLS = 4000
