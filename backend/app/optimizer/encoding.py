"""Street-aligned 2 m design grid, flat integer genome, and repair into the feasible set (SPEC.md §6.1–6.2).

Cell states: 0 unchanged, 1 tree, 2 reflective_pavement, 3 permeable_pavement, 4 shade_structure.

repair() projects any genome onto the feasible set instead of rejecting it:
  - a state not allowed on a cell's surface becomes unchanged (nothing on buildings, trees only on
    plantable ground, coatings only on paving, permeable paving only on footways, no shade
    structures until they have a cited effect)
  - trees closer than the minimum spacing are thinned
  - interventions beyond the budget are removed
"""

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import binary_dilation
from shapely.geometry import LineString

from app import config
from app.contracts import DesignGrid, Intervention
from app.data.fixtures import CachedWindow
from app.data.landcover import BARE, CANOPY, CARRIAGEWAY, FOOTWAY, block_fractions
from app.model.delta import CellEffects, before_lst_c, cell_effects
from app.model.heat import HeatModel

UNCHANGED, TREE, REFLECTIVE, PERMEABLE, SHADE = range(5)
STATE_NAMES = ("unchanged", "tree", "reflective_pavement", "permeable_pavement", "shade_structure")
MIN_SIDEWALK_POINTS = 20  # 1 m samples of mapped sidewalk needed on a side before trusting its offset


@dataclass(frozen=True)
class Budget:
    trees: int
    reflective_cells: int
    permeable_cells: int = 0


@dataclass(frozen=True)
class Objectives:
    """Kept separate so a multi-objective selector can use them directly (SPEC.md §6.3)."""

    temp_delta_c_low: float
    temp_delta_c_high: float
    cost_inr_low: float | None
    cost_inr_high: float | None
    trees: int
    reflective_cells: int
    permeable_cells: int

    @property
    def temp_drop_c(self) -> float:
        """Cooling at the conservative (least-cooling) end of the band, as a positive number."""
        return -self.temp_delta_c_high


def _disk_offsets(radius_m: float, cell_m: float, strict: bool) -> np.ndarray:
    reach = int(math.ceil(radius_m / cell_m))
    offsets = []
    for dr in range(-reach, reach + 1):
        for dc in range(-reach, reach + 1):
            distance_m = math.hypot(dr * cell_m, dc * cell_m)
            if (distance_m < radius_m) if strict else (distance_m <= radius_m):
                offsets.append((dr, dc))
    return np.array(offsets)


@dataclass
class StreetGrid:
    design_grid: DesignGrid
    classes: np.ndarray
    effects: CellEffects
    before_lst_c: np.ndarray
    cross_section: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        rows, cols = self.classes.shape
        cell_m = self.design_grid.cell_size_m
        allowed = np.zeros((rows, cols, len(STATE_NAMES)), dtype=bool)
        allowed[..., UNCHANGED] = True
        paved = np.isin(self.classes, (CARRIAGEWAY, FOOTWAY))
        allowed[..., REFLECTIVE] = paved
        allowed[..., PERMEABLE] = self.classes == FOOTWAY
        footway_plantable = config.SIDEWALK_WIDTH_M >= config.MIN_SIDEWALK_WIDTH_FOR_TREES_M
        allowed[..., TREE] = (self.classes == BARE) | ((self.classes == FOOTWAY) & footway_plantable)
        self.allowed = allowed
        crown = _disk_offsets(config.TREE_CROWN_DIAMETER_M / 2, cell_m, strict=False)
        reach = np.abs(crown).max()
        self._crown = np.zeros((2 * reach + 1, 2 * reach + 1), dtype=bool)
        self._crown[crown[:, 0] + reach, crown[:, 1] + reach] = True
        conflicts = _disk_offsets(config.TREE_MIN_SPACING_M, cell_m, strict=True)
        self._conflicts = conflicts[(conflicts != 0).any(axis=1)]

    @property
    def shape(self) -> tuple[int, int]:
        return self.classes.shape

    @property
    def n_cells(self) -> int:
        return self.classes.size

    def canopy_from(self, genome: np.ndarray) -> np.ndarray:
        trees = np.asarray(genome).reshape(self.shape) == TREE
        return binary_dilation(trees, structure=self._crown) if trees.any() else trees

    def tree_fits(self, grid: np.ndarray, row: int, col: int) -> bool:
        """True if no other tree in `grid` (rows x cols states) is closer than the minimum spacing."""
        rows, cols = self.shape
        r, c = row + self._conflicts[:, 0], col + self._conflicts[:, 1]
        inside = (r >= 0) & (r < rows) & (c >= 0) & (c < cols)
        return not (grid[r[inside], c[inside]] == TREE).any()

    def repair(self, genome, budget: Budget, rng: np.random.Generator) -> np.ndarray:
        grid = np.asarray(genome, dtype=np.int8).reshape(self.shape).copy()
        permitted = np.take_along_axis(self.allowed, grid[..., None].astype(np.intp), axis=2)[..., 0]
        grid[~permitted] = UNCHANGED

        trees = np.argwhere(grid == TREE)
        rng.shuffle(trees)
        grid[grid == TREE] = UNCHANGED
        for row, col in trees:
            if self.tree_fits(grid, row, col):
                grid[row, col] = TREE

        flat = grid.ravel()
        for state, limit in ((TREE, budget.trees), (REFLECTIVE, budget.reflective_cells),
                             (PERMEABLE, budget.permeable_cells)):
            cells = np.flatnonzero(flat == state)
            if len(cells) > limit:
                flat[rng.choice(cells, len(cells) - limit, replace=False)] = UNCHANGED
        return flat

    def cell_deltas(self, genome) -> tuple[np.ndarray, np.ndarray]:
        """Per-cell (low, high) change in modelled surface temperature for a layout."""
        grid = np.asarray(genome).reshape(self.shape)
        canopy = self.canopy_from(grid)
        uncovered = ~canopy
        low = np.where(canopy, self.effects.canopy_delta_c, 0.0)
        high = low.copy()
        reflective = (grid == REFLECTIVE) & uncovered
        permeable = (grid == PERMEABLE) & uncovered
        low[reflective] += self.effects.reflective_delta_c_low[reflective]
        high[reflective] += self.effects.reflective_delta_c_high[reflective]
        low[permeable] += self.effects.permeable_delta_c[permeable]
        high[permeable] += self.effects.permeable_delta_c[permeable]
        return low, high

    def evaluate(self, genome) -> Objectives:
        """Mean change in modelled surface temperature over the whole design area, as a band."""
        grid = np.asarray(genome).reshape(self.shape)
        low, high = self.cell_deltas(grid)
        return Objectives(
            temp_delta_c_low=float(low.sum() / self.n_cells),
            temp_delta_c_high=float(high.sum() / self.n_cells),
            cost_inr_low=None,
            cost_inr_high=None,
            trees=int((grid == TREE).sum()),
            reflective_cells=int((grid == REFLECTIVE).sum()),
            permeable_cells=int((grid == PERMEABLE).sum()),
        )

    def to_interventions(self, genome) -> list[Intervention]:
        grid = np.asarray(genome).reshape(self.shape)
        return [
            Intervention(type=STATE_NAMES[state], cells=[(int(r), int(c)) for r, c in np.argwhere(grid == state)])
            for state in (TREE, REFLECTIVE, PERMEABLE, SHADE) if (grid == state).any()
        ]


def _densify(coords: list[list[float]], step_m: float) -> np.ndarray:
    line = LineString(coords)
    distances = np.arange(0, line.length + step_m / 2, step_m)
    return np.array([line.interpolate(d).coords[0] for d in distances])


def grid_from_geometry(window: CachedWindow, model: HeatModel, classes_1m: np.ndarray, subgrid_transform,
                       block_residual_c: np.ndarray) -> StreetGrid:
    """Build the street-aligned design grid for the window's street from its OSM geometry.

    The grid is a DESIGN_SEGMENT_LENGTH_M segment centred on the street's longest OSM way,
    DESIGN_CORRIDOR_WIDTH_M across, split evenly either side of the centreline. Surface classes
    come from the 1 m window classification, then the carriageway and sidewalk bands are set from
    the offsets of the OSM sidewalks mapped along this segment.
    """
    street_name = window.manifest["osm_name"]
    ways = [w for w in window.osm["highways"] if w["tags"].get("name") == street_name]
    if not ways:
        raise ValueError(f"no OSM highway named {street_name!r} in the window")
    way = max(ways, key=lambda w: LineString(w["coords"]).length)
    line = LineString(way["coords"])
    length_m, width_m, cell_m = config.DESIGN_SEGMENT_LENGTH_M, config.DESIGN_CORRIDOR_WIDTH_M, config.DESIGN_CELL_SIZE_M
    if line.length < length_m:
        raise ValueError(f"longest {street_name} way is {line.length:.0f} m, shorter than the {length_m:.0f} m segment")
    start = np.array(line.interpolate(line.length / 2 - length_m / 2).coords[0])
    end = np.array(line.interpolate(line.length / 2 + length_m / 2).coords[0])
    along = (end - start) / length_m
    right = np.array([along[1], -along[0]])
    origin = start - right * width_m / 2
    bearing_deg = math.degrees(math.atan2(along[0], along[1])) % 360
    rows, cols = round(length_m / cell_m), round(width_m / cell_m)
    design_grid = DesignGrid(crs=window.bbox.crs, origin_e_m=float(origin[0]), origin_n_m=float(origin[1]),
                             bearing_deg=bearing_deg, cell_size_m=cell_m, shape=(rows, cols))

    r_idx, c_idx = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    centres = (origin[None, None, :] + ((r_idx + 0.5) * cell_m)[..., None] * along
               + ((c_idx + 0.5) * cell_m)[..., None] * right)
    sub_row = np.floor((subgrid_transform.f - centres[..., 1]) / -subgrid_transform.e).astype(int)
    sub_col = np.floor((centres[..., 0] - subgrid_transform.c) / subgrid_transform.a).astype(int)
    classes = classes_1m[sub_row, sub_col].copy()

    offsets = {"left": [], "right": []}
    for sidewalk in (w for w in window.osm["highways"] if w["tags"].get("footway") == "sidewalk"):
        points = _densify(sidewalk["coords"], 1.0) - start
        a, x = points @ along, points @ right
        keep = (a >= 0) & (a <= length_m) & (np.abs(x) <= width_m / 2)
        offsets["left"].extend(-x[keep & (x < 0)])
        offsets["right"].extend(x[keep & (x > 0)])
    lanes_half_width_m = (way_width := (int(way["tags"]["lanes"]) * config.LANE_WIDTH_M
                                        if str(way["tags"].get("lanes", "")).isdigit()
                                        else config.DEFAULT_CARRIAGEWAY_WIDTH_M[way["tags"]["highway"]])) / 2
    cross_section = {"osm_way": way["id"], "bearing_deg": round(bearing_deg, 1), "lanes_width_m": way_width}
    across_m = (c_idx + 0.5) * cell_m - width_m / 2
    carriageway = np.zeros(classes.shape, dtype=bool)
    sidewalk_band = np.zeros(classes.shape, dtype=bool)
    edges = {}
    for side, sign in (("left", -1), ("right", 1)):
        values = offsets[side]
        if len(values) >= MIN_SIDEWALK_POINTS:
            centre_m = float(np.median(values))
            edges[side] = centre_m - config.SIDEWALK_WIDTH_M / 2
            band = (sign * across_m >= edges[side]) & (sign * across_m < centre_m + config.SIDEWALK_WIDTH_M / 2)
            sidewalk_band |= band
            cross_section[f"{side}_sidewalk_offset_m"] = round(centre_m, 1)
        else:
            edges[side] = lanes_half_width_m
            cross_section[f"{side}_sidewalk_offset_m"] = None
        carriageway |= (sign * across_m >= 0) & (sign * across_m < edges[side])
    cross_section["carriageway_width_m"] = round(edges["left"] + edges["right"], 1)
    not_canopy = classes != CANOPY
    classes[carriageway & not_canopy] = CARRIAGEWAY
    classes[sidewalk_band & not_canopy] = FOOTWAY

    window_bounds = window.bbox.bounds
    block_m = config.CALIBRATION_BLOCK_CELLS * config.LANDSAT_CELL_SIZE_M
    block_row = np.floor((window_bounds[3] - centres[..., 1]) / block_m).astype(int)
    block_col = np.floor((centres[..., 0] - window_bounds[0]) / block_m).astype(int)
    residual_c = block_residual_c[block_row, block_col]

    return StreetGrid(design_grid=design_grid, classes=classes, effects=cell_effects(model, classes),
                      before_lst_c=before_lst_c(model, classes, residual_c), cross_section=cross_section)


def street_grid_for(window: CachedWindow, model: HeatModel) -> StreetGrid:
    """Convenience: classify the window, compute calibration-cell residuals, and build the design grid."""
    from app.model.validate import calibration_cells, window_surfaces

    classes_1m, transform = window_surfaces(window)
    cover, lst_c, _ = calibration_cells(window, classes_1m)
    residual_c = lst_c - model.predict_c(cover.canopy_fraction, cover.built_fraction, cover.bare_fraction)
    return grid_from_geometry(window, model, classes_1m, transform, residual_c)
