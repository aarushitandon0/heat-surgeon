"""random_layout() and greedy_layout() at matched budget, for the comparison claim (SPEC.md §6.4).

Matched budget means the same number of trees, reflective cells and permeable cells the GA may
use. Both baselines place interventions one at a time, trees first, and respect the same
constraints the GA's repair enforces.
"""

import numpy as np

from app.optimizer.encoding import PERMEABLE, REFLECTIVE, TREE, UNCHANGED, Budget, StreetGrid


def _place(grid: StreetGrid, budget: Budget, order_for) -> np.ndarray:
    layout = np.full(grid.shape, UNCHANGED, dtype=np.int8)
    for state, count in ((TREE, budget.trees), (REFLECTIVE, budget.reflective_cells), (PERMEABLE, budget.permeable_cells)):
        if count == 0:
            continue
        canopy = grid.canopy_from(layout)
        placed = 0
        for flat in order_for(state):
            if placed == count:
                break
            row, col = divmod(int(flat), grid.shape[1])
            if layout[row, col] != UNCHANGED or not grid.allowed[row, col, state]:
                continue
            if state == TREE:
                if not grid.tree_fits(layout, row, col):
                    continue
            elif canopy[row, col]:
                continue  # a coating under a new crown does nothing
            layout[row, col] = state
            placed += 1
    return layout.ravel()


def random_layout(grid: StreetGrid, budget: Budget, rng: np.random.Generator) -> np.ndarray:
    """The budget placed on uniformly random valid cells."""
    return _place(grid, budget, lambda state: rng.permutation(grid.n_cells))


def greedy_layout(grid: StreetGrid, budget: Budget) -> np.ndarray:
    """The budget placed one at a time on the currently hottest valid cell (by modelled surface temperature today)."""
    order = np.argsort(-grid.before_lst_c.ravel(), kind="stable")
    return _place(grid, budget, lambda state: order)
