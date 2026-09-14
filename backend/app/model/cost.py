"""Intervention cost ranges (low/high, INR) from cited figures in config.py (SPEC.md §8).

A layout's cost is the sum of its interventions' ranges. If the layout uses any intervention with no
sourced rate, the layout has no cost: layout_cost_inr returns None, never a partial or estimated sum.
Every figure and its scope (first-year tree care only) is in docs/sources.md and docs/methodology.md.
"""

from app import config


def unit_cost_inr(intervention_type: str) -> tuple[float, float] | None:
    """(low, high) cost of one unit of an intervention, or None if no rate is sourced."""
    return config.COST_INR_BY_INTERVENTION[intervention_type]


def unpriced(counts: dict[str, int]) -> list[str]:
    """Intervention types used in `counts` that have no sourced rate."""
    return sorted(kind for kind, count in counts.items() if count > 0 and unit_cost_inr(kind) is None)


def layout_cost_inr(counts: dict[str, int]) -> tuple[float, float] | None:
    """(low, high) cost of a layout given units per intervention type; None if any used type is unpriced."""
    if unpriced(counts):
        return None
    low = high = 0.0
    for kind, count in counts.items():
        if count > 0:
            unit_low, unit_high = unit_cost_inr(kind)
            low += count * unit_low
            high += count * unit_high
    return low, high
