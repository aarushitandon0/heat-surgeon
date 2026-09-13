"""Intervention deltas, repair, evaluation, baselines and the GA on small synthetic grids.

Grids and coefficients here are synthetic test fixtures, not data.
"""

import numpy as np

from app import config
from app.contracts import DesignGrid
from app.data.landcover import BARE, BUILT, CANOPY, CARRIAGEWAY, FOOTWAY
from app.model.delta import cell_effects
from app.model.heat import HeatModel
from app.optimizer.baselines import greedy_layout, random_layout
from app.optimizer.encoding import REFLECTIVE, TREE, UNCHANGED, Budget, StreetGrid
from app.optimizer.ga import GAParams, run_ga

MODEL = HeatModel(t_base_c=40.0, k_canopy_c_per_fraction=5.0, k_built_c_per_fraction=-3.0, k_bare_c_per_fraction=2.0)


def make_grid(classes, before=None) -> StreetGrid:
    classes = np.asarray(classes)
    design = DesignGrid(crs="EPSG:32643", origin_e_m=0.0, origin_n_m=0.0, bearing_deg=0.0,
                        cell_size_m=config.DESIGN_CELL_SIZE_M, shape=classes.shape)
    before = np.zeros(classes.shape) if before is None else np.asarray(before, dtype=float)
    return StreetGrid(design_grid=design, classes=classes, effects=cell_effects(MODEL, classes), before_lst_c=before)


def test_cell_effects_hand_checked():
    effects = cell_effects(MODEL, np.array([[CARRIAGEWAY, FOOTWAY, BARE, BUILT, CANOPY]]))
    # canopy over paving -5; over bare -5 - 2 = -7; over built -5 - (-3) = -2; existing canopy 0
    assert effects.canopy_delta_c.tolist() == [[-5.0, -5.0, -7.0, -2.0, 0.0]]
    coat = config.ALBEDO_BY_MATERIAL["high_albedo_coating"]
    asphalt, concrete = config.ALBEDO_BY_MATERIAL["asphalt_aged"], config.ALBEDO_BY_MATERIAL["concrete_aged"]
    k_low, k_high = config.K_ALBEDO_LOW_C_PER_UNIT_ALBEDO, config.K_ALBEDO_HIGH_C_PER_UNIT_ALBEDO
    # with the cited values: asphalt -27 * (0.50 - 0.10) = -10.8 to -5 * (0.50 - 0.20) = -1.5
    assert np.isclose(effects.reflective_delta_c_low[0, 0], -k_high * (coat[1] - asphalt[0]))
    assert np.isclose(effects.reflective_delta_c_high[0, 0], -k_low * (coat[0] - asphalt[1]))
    assert np.isclose(effects.reflective_delta_c_low[0, 1], -k_high * (coat[1] - concrete[0]))
    assert np.isnan(effects.reflective_delta_c_low[0, 2])
    assert effects.permeable_delta_c[0, 1] == 2.0 and np.isnan(effects.permeable_delta_c[0, 0])


def test_repair_removes_disallowed_states_thins_trees_and_enforces_budget():
    grid = make_grid(np.full((12, 12), BARE))
    genome = np.full(144, UNCHANGED, dtype=np.int8)
    genome[0] = REFLECTIVE                       # not allowed on bare ground
    genome[[13, 14, 60, 140]] = TREE             # cells 13 and 14 are 2 m apart
    repaired = grid.repair(genome, Budget(trees=2, reflective_cells=5), np.random.default_rng(0))
    assert repaired[0] == UNCHANGED
    trees = np.flatnonzero(repaired == TREE)
    assert len(trees) == 2
    positions = [divmod(int(t), 12) for t in trees]
    (r1, c1), (r2, c2) = positions
    assert np.hypot(r1 - r2, c1 - c2) * config.DESIGN_CELL_SIZE_M >= config.TREE_MIN_SPACING_M


def test_evaluate_tree_on_bare_ground_hand_checked():
    # 7 x 7 bare grid, one tree in the centre. An 8 m crown on 2 m cells covers the 13 cells within 4 m.
    # Each gains -7 C: mean over 49 cells = 13 * -7 / 49.
    grid = make_grid(np.full((7, 7), BARE))
    genome = np.zeros(49, dtype=np.int8)
    genome[24] = TREE
    result = grid.evaluate(genome)
    assert np.isclose(result.temp_delta_c_low, 13 * -7 / 49)
    assert result.temp_delta_c_low == result.temp_delta_c_high  # no albedo intervention, no band


def test_greedy_takes_hottest_valid_cell_and_random_respects_budget():
    classes = np.full((6, 6), BUILT)
    classes[0, :] = CARRIAGEWAY
    before = np.zeros((6, 6))
    before[0, 4] = 45.0                          # hottest paved cell
    before[5, 5] = 50.0                          # hotter, but a building
    grid = make_grid(classes, before)
    greedy = greedy_layout(grid, Budget(trees=0, reflective_cells=1))
    assert np.flatnonzero(greedy == REFLECTIVE).tolist() == [4]
    layout = random_layout(grid, Budget(trees=0, reflective_cells=3), np.random.default_rng(1))
    assert (layout == REFLECTIVE).sum() == 3
    assert all(classes.ravel()[i] == CARRIAGEWAY for i in np.flatnonzero(layout == REFLECTIVE))


def test_ga_finds_the_best_single_tree_position():
    # Bare strip on the left (a tree there gains -7 per crown cell), built on the right (-2 per cell).
    classes = np.full((9, 9), BUILT)
    classes[:, :4] = BARE
    grid = make_grid(classes)
    budget = Budget(trees=1, reflective_cells=0)
    run = run_ga(grid, budget, GAParams(population=24, generations=30, seed=0))
    brute = min(
        (grid.evaluate(np.eye(81, dtype=np.int8)[i]).temp_delta_c_high for i in range(81) if grid.allowed.reshape(-1, 5)[i, TREE]),
    )
    assert np.isclose(run.objectives.temp_delta_c_high, brute)
