"""Street-aligned 2 m design grid, flat integer genome, and repair into the feasible set (SPEC.md §6.1–6.2).

Cell states: 0 unchanged, 1 tree, 2 reflective_pavement, 3 permeable_pavement, 4 shade_structure.

Where each state may go comes from the street's cross-section (app/data/cross_section.py), not from
"anything that is not a building":
  - trees only in plantable bands (tree pits), never on a building or existing canopy
  - coatings only on paved carriageway, footway or cycle track inside the right of way
  - nothing on private property outside the right of way
  - permeable paving and shade structures nowhere (docs/methodology.md)

repair() projects any genome onto the feasible set instead of rejecting it:
  - a state not allowed on a cell becomes unchanged
  - trees closer than the minimum spacing are thinned
  - interventions beyond the budget are removed
"""

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import binary_dilation
from shapely.geometry import LineString

from app import config
from app.contracts import CrossSection, DesignGrid, Intervention
from app.data.cross_section import band_masks, cross_section_for, plantable_mask
from app.data.fixtures import CachedWindow
from app.data.landcover import BARE, BUILT, CANOPY, CARRIAGEWAY, FOOTWAY
from app.model.cost import layout_cost_inr, unpriced
from app.model.delta import CellEffects, before_lst_c, cell_effects
from app.model.heat import HeatModel

UNCHANGED, TREE, REFLECTIVE, PERMEABLE, SHADE = range(5)
STATE_NAMES = ("unchanged", "tree", "reflective_pavement", "permeable_pavement", "shade_structure")

# Cross-section band kinds, as the surface class a design cell inside them is modelled as today.
BAND_SURFACE = {
    "carriageway": CARRIAGEWAY, "bus_stop": CARRIAGEWAY,
    "footway": FOOTWAY, "cycle_track": FOOTWAY, "tree_pit": FOOTWAY,
    "buffer": BARE, "median": BARE,
}
COATABLE_BANDS = ("carriageway", "bus_stop", "footway", "cycle_track")


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
    unpriced_interventions: tuple[str, ...]
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
    plantable: np.ndarray | None = None
    coatable: np.ndarray | None = None
    cross_section: CrossSection | None = None
    segment: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        rows, cols = self.classes.shape
        cell_m = self.design_grid.cell_size_m
        if self.plantable is None:
            self.plantable = self.classes == BARE
        if self.coatable is None:
            self.coatable = np.isin(self.classes, (CARRIAGEWAY, FOOTWAY))
        allowed = np.zeros((rows, cols, len(STATE_NAMES)), dtype=bool)
        allowed[..., UNCHANGED] = True
        allowed[..., TREE] = self.plantable & ~np.isin(self.classes, (BUILT, CANOPY))
        allowed[..., REFLECTIVE] = self.coatable & np.isin(self.classes, (CARRIAGEWAY, FOOTWAY))
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

    def tree_capacity(self) -> int:
        """Most trees the plantable cells hold at the minimum spacing, packed row by row along each column."""
        layout = np.full(self.shape, UNCHANGED, dtype=np.int8)
        count = 0
        for col in range(self.shape[1]):
            for row in np.flatnonzero(self.allowed[:, col, TREE]):
                if self.tree_fits(layout, row, col):
                    layout[row, col] = TREE
                    count += 1
        return count

    def matched(self, budget: Budget) -> Budget:
        """The budget every arm gets: the tree count capped at what the street can physically hold."""
        return Budget(trees=min(budget.trees, self.tree_capacity()), reflective_cells=budget.reflective_cells,
                      permeable_cells=budget.permeable_cells)

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

    def counts(self, genome) -> dict[str, int]:
        grid = np.asarray(genome)
        return {STATE_NAMES[s]: int((grid == s).sum()) for s in (TREE, REFLECTIVE, PERMEABLE, SHADE)}

    def evaluate(self, genome) -> Objectives:
        """Mean change in modelled surface temperature over the whole design area, as a band, and cost."""
        grid = np.asarray(genome).reshape(self.shape)
        low, high = self.cell_deltas(grid)
        counts = self.counts(grid)
        cost = layout_cost_inr(counts)
        return Objectives(
            temp_delta_c_low=float(low.sum() / self.n_cells),
            temp_delta_c_high=float(high.sum() / self.n_cells),
            cost_inr_low=None if cost is None else cost[0],
            cost_inr_high=None if cost is None else cost[1],
            unpriced_interventions=tuple(unpriced(counts)),
            trees=counts["tree"],
            reflective_cells=counts["reflective_pavement"],
            permeable_cells=counts["permeable_pavement"],
        )

    def to_interventions(self, genome) -> list[Intervention]:
        grid = np.asarray(genome).reshape(self.shape)
        return [
            Intervention(type=STATE_NAMES[state], cells=[(int(r), int(c)) for r, c in np.argwhere(grid == state)])
            for state in (TREE, REFLECTIVE, PERMEABLE, SHADE) if (grid == state).any()
        ]


def segment_frame(window: CachedWindow) -> dict:
    """The design segment: DESIGN_SEGMENT_LENGTH_M centred on the street's longest OSM way in the window."""
    street_name = window.manifest["osm_name"]
    ways = [w for w in window.osm["highways"] if w["tags"].get("name") == street_name]
    if not ways:
        raise ValueError(f"no OSM highway named {street_name!r} in the window")
    way = max(ways, key=lambda w: LineString(w["coords"]).length)
    line = LineString(way["coords"])
    length_m, width_m = config.DESIGN_SEGMENT_LENGTH_M, config.DESIGN_CORRIDOR_WIDTH_M
    if line.length < length_m:
        raise ValueError(f"longest {street_name} way is {line.length:.0f} m, shorter than the {length_m:.0f} m segment")
    start = np.array(line.interpolate(line.length / 2 - length_m / 2).coords[0])
    end = np.array(line.interpolate(line.length / 2 + length_m / 2).coords[0])
    along = (end - start) / length_m
    right = np.array([along[1], -along[0]])
    return {"way": way, "start": start, "end": end, "along": along, "right": right,
            "origin": start - right * width_m / 2, "bearing_deg": math.degrees(math.atan2(along[0], along[1])) % 360}


def grid_from_geometry(window: CachedWindow, model: HeatModel, classes_1m: np.ndarray, subgrid_transform,
                       block_residual_c: np.ndarray) -> StreetGrid:
    """Build the street-aligned design grid for the window's street from its geometry and cross-section.

    Surface classes come from the 1 m window classification (canopy from NDVI, buildings from merged
    footprints). Inside the right of way, cells that are not canopy or building take the surface of their
    cross-section band. Allowed interventions follow the bands.
    """
    frame = segment_frame(window)
    length_m, width_m, cell_m = config.DESIGN_SEGMENT_LENGTH_M, config.DESIGN_CORRIDOR_WIDTH_M, config.DESIGN_CELL_SIZE_M
    origin, along, right = frame["origin"], frame["along"], frame["right"]
    rows, cols = round(length_m / cell_m), round(width_m / cell_m)
    design_grid = DesignGrid(crs=window.bbox.crs, origin_e_m=float(origin[0]), origin_n_m=float(origin[1]),
                             bearing_deg=frame["bearing_deg"], cell_size_m=cell_m, shape=(rows, cols))

    r_idx, c_idx = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    centres = (origin[None, None, :] + ((r_idx + 0.5) * cell_m)[..., None] * along
               + ((c_idx + 0.5) * cell_m)[..., None] * right)
    sub_row = np.floor((subgrid_transform.f - centres[..., 1]) / -subgrid_transform.e).astype(int)
    sub_col = np.floor((centres[..., 0] - subgrid_transform.c) / subgrid_transform.a).astype(int)
    classes = classes_1m[sub_row, sub_col].copy()

    cross_section = cross_section_for(frame["way"]["tags"], window.buildings, frame["start"], along, length_m)
    across_m = (c_idx + 0.5) * cell_m - width_m / 2
    masks = band_masks(cross_section, across_m)
    fixed = np.isin(classes, (CANOPY, BUILT))
    for kind, surface in BAND_SURFACE.items():
        if kind in masks:
            classes[masks[kind] & ~fixed] = surface
    coatable = np.zeros(classes.shape, dtype=bool)
    for kind in COATABLE_BANDS:
        coatable |= masks.get(kind, coatable)

    window_bounds = window.bbox.bounds
    block_m = config.CALIBRATION_BLOCK_CELLS * config.LANDSAT_CELL_SIZE_M
    block_row = np.floor((window_bounds[3] - centres[..., 1]) / block_m).astype(int)
    block_col = np.floor((centres[..., 0] - window_bounds[0]) / block_m).astype(int)
    residual_c = block_residual_c[block_row, block_col]

    return StreetGrid(design_grid=design_grid, classes=classes, effects=cell_effects(model, classes),
                      before_lst_c=before_lst_c(model, classes, residual_c),
                      plantable=plantable_mask(cross_section, across_m), coatable=coatable,
                      cross_section=cross_section,
                      segment={"osm_way": frame["way"]["id"], "bearing_deg": round(frame["bearing_deg"], 1),
                               "start_utm": [round(float(v), 1) for v in frame["start"]],
                               "end_utm": [round(float(v), 1) for v in frame["end"]]})


def street_grid_for(window: CachedWindow, model: HeatModel) -> StreetGrid:
    """Convenience: classify the window, compute calibration-cell residuals, and build the design grid."""
    from app.model.validate import calibration_cells, window_surfaces

    classes_1m, transform = window_surfaces(window)
    cover, lst_c, _ = calibration_cells(window, classes_1m)
    residual_c = lst_c - model.predict_c(cover.canopy_fraction, cover.built_fraction, cover.bare_fraction)
    return grid_from_geometry(window, model, classes_1m, transform, residual_c)
