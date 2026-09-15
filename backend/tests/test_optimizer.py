"""Intervention deltas, repair, evaluation, baselines and the GA on small synthetic grids.

Grids and coefficients here are synthetic test fixtures, not data.
"""

import numpy as np

from app import config
from app.contracts import DesignGrid
from app.data.landcover import BARE, BUILT, CANOPY, CARRIAGEWAY, FOOTWAY
from app.model.delta import cell_effects
from app.model.heat import HeatModel
from app.optimizer.baselines import design_guideline_layout, greedy_layout, random_layout
from app.optimizer.encoding import REFLECTIVE, TREE, UNCHANGED, Budget, StreetGrid
from app.optimizer.ga import GAParams, clone_layout, run_ga

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


def test_design_guideline_spaces_trees_evenly_on_both_strips_and_coats_a_contiguous_run():
    # 50 x 10 grid: carriageway columns 3-6, plantable tree-pit strips in columns 1 and 8.
    classes = np.full((50, 10), FOOTWAY)
    classes[:, 3:7] = CARRIAGEWAY
    plantable = np.zeros((50, 10), dtype=bool)
    plantable[:, 1] = plantable[:, 8] = True
    design = DesignGrid(crs="EPSG:32643", origin_e_m=0.0, origin_n_m=0.0, bearing_deg=0.0,
                        cell_size_m=config.DESIGN_CELL_SIZE_M, shape=classes.shape)
    grid = StreetGrid(design_grid=design, classes=classes, effects=cell_effects(MODEL, classes),
                      before_lst_c=np.zeros(classes.shape), plantable=plantable,
                      coatable=np.isin(classes, (CARRIAGEWAY,)))
    layout = design_guideline_layout(grid, Budget(trees=4, reflective_cells=8)).reshape(classes.shape)
    trees = np.argwhere(layout == TREE)
    assert len(trees) == 4
    assert sorted(set(trees[:, 1].tolist())) == [1, 8]           # two on each strip
    for col in (1, 8):
        rows = trees[trees[:, 1] == col, 0]
        # span of 49 rows split over 2 trees -> step 24.5 rows (49 m), well above the 8 m minimum
        assert abs(rows[1] - rows[0]) * config.DESIGN_CELL_SIZE_M >= config.TREE_MIN_SPACING_M
    coated = np.argwhere(layout == REFLECTIVE)
    assert len(coated) == 8
    assert set(coated[:, 1].tolist()) <= {3, 4, 5, 6}
    assert np.ptp(coated[:, 0]) == 1                               # two whole rows next to each other


def test_design_guideline_reaches_capacity_when_the_strips_hold_unequal_counts():
    # 20 x 10 grid. Left strip (column 1) is plantable on rows 0-8 only: at 8 m spacing on 2 m cells it holds
    # rows 0, 4, 8 = 3 trees. Right strip (column 8) is plantable on all 20 rows and packs 5. Capacity is 8.
    # An even 4/4 split leaves the left side one short, so it passes one to the right: 3 + 5 = 8.
    # Right side, evenly spaced: span 19 rows, step max(4, 19 / 5) = 4, run 4 * 4 = 16 centred in 19 starts at
    # row 1.5; nearest free rows give 1, 5, 9, 13, 17.
    classes = np.full((20, 10), FOOTWAY)
    plantable = np.zeros((20, 10), dtype=bool)
    plantable[0:9, 1] = True
    plantable[:, 8] = True
    design = DesignGrid(crs="EPSG:32643", origin_e_m=0.0, origin_n_m=0.0, bearing_deg=0.0,
                        cell_size_m=config.DESIGN_CELL_SIZE_M, shape=classes.shape)
    grid = StreetGrid(design_grid=design, classes=classes, effects=cell_effects(MODEL, classes),
                      before_lst_c=np.zeros(classes.shape), plantable=plantable,
                      coatable=np.zeros(classes.shape, dtype=bool))
    assert grid.tree_capacity() == 8
    layout = design_guideline_layout(grid, Budget(trees=8, reflective_cells=0)).reshape(classes.shape)
    trees = np.argwhere(layout == TREE)
    assert len(trees) == 8
    assert sorted(trees[trees[:, 1] == 1, 0].tolist()) == [0, 4, 8]
    assert sorted(trees[trees[:, 1] == 8, 0].tolist()) == [1, 5, 9, 13, 17]
    for i in range(len(trees)):
        for j in range(i + 1, len(trees)):
            distance_m = np.hypot(*(trees[i] - trees[j])) * config.DESIGN_CELL_SIZE_M
            assert distance_m >= config.TREE_MIN_SPACING_M


def test_evaluate_reports_cost_only_when_every_intervention_is_priced():
    grid = make_grid(np.full((7, 7), BARE))
    genome = np.zeros(49, dtype=np.int8)
    genome[24] = TREE
    result = grid.evaluate(genome)
    assert (result.cost_inr_low, result.cost_inr_high) == config.COST_INR_BY_INTERVENTION["tree"]
    classes = np.full((7, 7), CARRIAGEWAY)
    coated = np.zeros(49, dtype=np.int8)
    coated[0] = REFLECTIVE
    result = make_grid(classes).evaluate(coated)
    assert result.cost_inr_low is None and result.unpriced_interventions == ("reflective_pavement",)


def test_clone_layout_copies_genes_fitness_and_objectives_without_sharing_the_genes():
    from deap import creator

    original = creator.Layout([0, 1, 2, 0])
    original.fitness.values = (0.5,)
    original.objectives = "frozen objectives stand-in"
    copied = clone_layout(original)
    assert list(copied) == [0, 1, 2, 0] and copied.fitness.values == (0.5,) and copied.objectives is original.objectives
    copied[1] = 0
    del copied.fitness.values
    assert list(original) == [0, 1, 2, 0] and original.fitness.valid and original.fitness.values == (0.5,)
    # An individual whose fitness was invalidated clones as invalid.
    assert not clone_layout(copied).fitness.valid


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
