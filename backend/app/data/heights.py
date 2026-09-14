"""Derive the storeys-by-footprint-area table used for buildings with no OSM height or levels tag.

config.BUILDING_STOREYS_BY_FOOTPRINT_AREA_M2 is frozen from this script's output, so adding a street never
changes another street's heights. Re-derive with:

    python -m app.data.heights

Samples are OSM buildings with a positive integer building:levels tag, de-duplicated by OSM id because the
fixture windows overlap. See docs/methodology.md, "Building heights".
"""

from statistics import median

from shapely.geometry import Polygon

from app import config


def parse_levels(value) -> int | None:
    """A positive whole number of levels, or None for missing, zero, fractional or free-text tags ("Ground+3")."""
    try:
        levels = float(value)
    except (TypeError, ValueError):
        return None
    return int(levels) if levels > 0 and levels == int(levels) else None


def storeys_by_area(samples: list[tuple[float, int]], upper_bounds_m2: tuple[float, ...]) -> list[dict]:
    """Median levels per area bin. A sample falls in the first bin whose upper bound exceeds its area; the last
    bin is open-ended. Returns one {upper_bound_m2, median_levels, count} per non-empty bin."""
    bounds = list(upper_bounds_m2) + [float("inf")]
    bins: list[list[int]] = [[] for _ in bounds]
    for area_m2, levels in samples:
        bins[next(i for i, bound in enumerate(bounds) if area_m2 < bound)].append(levels)
    return [{"upper_bound_m2": bound, "median_levels": median(levels), "count": len(levels)}
            for bound, levels in zip(bounds, bins) if levels]


def tagged_samples(osm_buildings: list[dict]) -> dict[str, tuple[float, int]]:
    """{osm id: (footprint area m², levels)} for buildings with a usable building:levels tag."""
    samples = {}
    for building in osm_buildings:
        levels = parse_levels(building["tags"].get("building:levels"))
        if levels is not None:
            samples[building["id"]] = (Polygon(building["rings"][0]).area, levels)
    return samples


if __name__ == "__main__":
    from app import pipeline

    samples: dict[str, tuple[float, int]] = {}
    for street_id in pipeline.street_ids():
        samples.update(tagged_samples(pipeline.street_context(street_id).window.osm["buildings"]))
    print(f"{len(samples)} unique OSM buildings with integer building:levels")
    for row in storeys_by_area(list(samples.values()), config.BUILDING_AREA_BIN_UPPER_BOUNDS_M2):
        print(f"  area < {row['upper_bound_m2']:>7} m2: median {row['median_levels']} levels (n={row['count']})")
