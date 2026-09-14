"""Street cross-section: how the right of way is divided, and where a tree may be planted.

Order of preference, each labelled by CrossSection.source:
  osm_tag            the OSM way tags a carriageway width and both sidewalk widths
  published_design   right of way measured from building footprints, divided by the PMC Urban Street
                     Design Guidelines (2016) template for that width. This is the city's design standard
                     applied to the measured width, NOT the street's surveyed as-built layout.
  default_assumption carriageway from lanes or road class, sidewalks at the IRC:103 minimum, no tree pits

Bands are offsets across the street from the OSM centreline, negative to the left of the bearing. The
carriageway (with any median) is centred on the centreline. Outside the right of way is private property,
where nothing is placed.
"""

import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon

from app import config
from app.contracts import CrossSection, CrossSectionBand

MIN_TEMPLATE_ROW_M = 9.0


def _parse_width(value) -> float | None:
    try:
        return float(str(value).lower().replace("m", "").strip())
    except (TypeError, ValueError):
        return None


def measure_right_of_way_m(buildings: list[dict], start: np.ndarray, along: np.ndarray, length_m: float
                           ) -> tuple[float, float] | None:
    """(left, right) distance from the centreline to the building line, median over stations; None if unknown."""
    polygons = [Polygon(ring) for b in buildings for ring in b["rings"]]
    polygons = [p if p.is_valid else p.buffer(0) for p in polygons]
    tree = STRtree(polygons)
    right = np.array([along[1], -along[0]])
    reach = config.ROW_SEARCH_REACH_M
    stations = np.arange(0.0, length_m + 1e-9, config.DESIGN_CELL_SIZE_M)
    distances = {"left": [], "right": []}
    for s in stations:
        origin = start + along * s
        origin_point = Point(origin)
        for side, sign in (("left", -1.0), ("right", 1.0)):
            ray = LineString([origin, origin + sign * right * reach])
            hits = [origin_point.distance(ray.intersection(polygons[i])) for i in tree.query(ray)
                    if ray.intersects(polygons[i])]
            if hits:
                distances[side].append(min(hits))
    if any(len(d) < config.ROW_MIN_STATION_SHARE * len(stations) for d in distances.values()):
        return None
    return float(np.median(distances["left"])), float(np.median(distances["right"]))


def template_for(right_of_way_m: float) -> str | None:
    """The USDG template to use: the widest one no wider than the right of way (USDG chapter 8)."""
    fitting = [(sum(w for _, w in bands), name) for name, bands in config.USDG_TEMPLATES.items()
               if sum(w for _, w in bands) <= right_of_way_m + 1e-9]
    return max(fitting)[1] if fitting else None


def _bands_from_widths(widths: list[tuple[str, float]], left_m: float, right_m: float) -> list[CrossSectionBand]:
    """Lay bands left to right so the carriageway block is centred on offset 0, then private property outside."""
    kinds = [k for k, _ in widths]
    first = kinds.index("carriageway")
    last = len(kinds) - 1 - kinds[::-1].index("carriageway")
    block_m = sum(w for _, w in widths[first:last + 1])
    offset = -block_m / 2 - sum(w for _, w in widths[:first])
    bands = [CrossSectionBand(kind="private_property", offset_from_m=-config.DESIGN_CORRIDOR_WIDTH_M,
                              offset_to_m=offset, plantable=False)] if offset > -config.DESIGN_CORRIDOR_WIDTH_M else []
    for kind, width in widths:
        bands.append(CrossSectionBand(kind=kind, offset_from_m=offset, offset_to_m=offset + width,
                                      plantable=kind == "tree_pit"))
        offset += width
    bands.append(CrossSectionBand(kind="private_property", offset_from_m=offset,
                                  offset_to_m=config.DESIGN_CORRIDOR_WIDTH_M, plantable=False))
    return bands


def usdg_cross_section(left_m: float, right_m: float) -> CrossSection | None:
    """Published-design cross-section for a measured right of way, or None if it is narrower than any template."""
    right_of_way_m = left_m + right_m
    name = template_for(right_of_way_m)
    if name is None:
        return None
    widths = list(config.USDG_TEMPLATES[name])
    spare_m = right_of_way_m - sum(w for _, w in widths)
    # USDG: width beyond the template goes to non-motorised space; split onto the outermost footways.
    footways = [i for i, (k, _) in enumerate(widths) if k == "footway"]
    outer = [footways[0], footways[-1]] if len(footways) > 1 else footways
    for i in outer:
        widths[i] = (widths[i][0], widths[i][1] + spare_m / len(outer))
    return CrossSection(
        source="published_design",
        reference=f"PMC Urban Street Design Guidelines 2016, template {name}, applied to a right of way of "
                  f"{right_of_way_m:.1f} m measured from building footprints; not a surveyed as-built layout",
        right_of_way_m=round(right_of_way_m, 2),
        right_of_way_source="building_footprints",
        bands=_bands_from_widths(widths, left_m, right_m),
    )


def osm_cross_section(tags: dict) -> CrossSection | None:
    """Cross-section from OSM tags, only when carriageway width and both sidewalk widths are tagged."""
    road_m = _parse_width(tags.get("width"))
    both = _parse_width(tags.get("sidewalk:both:width"))
    left = _parse_width(tags.get("sidewalk:left:width")) or both
    right = _parse_width(tags.get("sidewalk:right:width")) or both
    if not (road_m and left and right):
        return None
    widths = [("footway", left), ("carriageway", road_m), ("footway", right)]
    return CrossSection(source="osm_tag", reference="OSM tags width and sidewalk widths",
                        right_of_way_m=road_m + left + right, right_of_way_source="osm_tag",
                        bands=_bands_from_widths(widths, 0, 0))


def default_cross_section(tags: dict) -> CrossSection:
    """Carriageway from lanes or class default, IRC:103 minimum sidewalks, no tree pits."""
    if str(tags.get("lanes", "")).isdigit():
        road_m = int(tags["lanes"]) * config.LANE_WIDTH_M
    else:
        road_m = config.DEFAULT_CARRIAGEWAY_WIDTH_M[tags["highway"]]
    widths = [("footway", config.SIDEWALK_WIDTH_M), ("carriageway", road_m), ("footway", config.SIDEWALK_WIDTH_M)]
    return CrossSection(source="default_assumption",
                        reference="Carriageway from OSM lanes or road class; sidewalks at the IRC:103 minimum; "
                                  "no tree pits",
                        right_of_way_m=road_m + 2 * config.SIDEWALK_WIDTH_M, right_of_way_source="default_assumption",
                        bands=_bands_from_widths(widths, 0, 0))


def cross_section_for(tags: dict, buildings: list[dict], start: np.ndarray, along: np.ndarray,
                      length_m: float) -> CrossSection:
    tagged = osm_cross_section(tags)
    if tagged is not None:
        return tagged
    measured = measure_right_of_way_m(buildings, start, along, length_m)
    if measured is not None:
        published = usdg_cross_section(*measured)
        if published is not None:
            return published
    return default_cross_section(tags)


def band_masks(cross_section: CrossSection, across_m: np.ndarray) -> dict[str, np.ndarray]:
    """Boolean mask per band kind for an array of across-street offsets (cell centres)."""
    masks = {}
    for band in cross_section.bands:
        inside = (across_m >= band.offset_from_m) & (across_m < band.offset_to_m)
        masks[band.kind] = masks.get(band.kind, np.zeros(across_m.shape, dtype=bool)) | inside
    return masks


def plantable_mask(cross_section: CrossSection, across_m: np.ndarray) -> np.ndarray:
    mask = np.zeros(across_m.shape, dtype=bool)
    for band in cross_section.bands:
        if band.plantable:
            mask |= (across_m >= band.offset_from_m) & (across_m < band.offset_to_m)
    return mask
