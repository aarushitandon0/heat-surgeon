"""Baselines at matched budget, for the comparison claim (SPEC.md §6.4).

  random_layout()            the budget on uniformly random valid cells
  greedy_layout()            one at a time on the currently hottest valid cell. Kept for the record; in a
                             linear model an intervention's gain does not depend on how hot a cell is, so
                             this is a weak baseline (docs/methodology.md)
  design_guideline_layout()  what a competent street designer would do with the same budget: trees evenly
                             spaced along the plantable strips on both sides, coating on the widest
                             continuous run of paving. No optimisation. This is the counterfactual that matters.

Matched budget means the same number of trees and coated cells. All respect the constraints repair enforces.
"""

import math

import numpy as np

from app import config
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


def _plant_side(grid: StreetGrid, layout: np.ndarray, columns: np.ndarray, count: int) -> int:
    """Plant up to `count` trees evenly along the plantable strip in `columns`; returns how many fit."""
    allowed = grid.allowed[:, columns, TREE]
    if count == 0 or not allowed.any():
        return 0
    col = columns[int(np.argmax(allowed.sum(axis=0)))]  # the strip's best-covered column
    rows = np.flatnonzero(grid.allowed[:, col, TREE])
    cell_m = grid.design_grid.cell_size_m
    span_rows = rows[-1] - rows[0]
    min_step = math.ceil(config.TREE_MIN_SPACING_M / cell_m)
    step = max(min_step, span_rows / count if count > 1 else span_rows)
    placed = 0
    target = rows[0] + (span_rows - step * (count - 1)) / 2 if span_rows >= step * (count - 1) else rows[0]
    for _ in range(count):
        candidates = rows[np.argsort(np.abs(rows - target), kind="stable")]
        for row in candidates:
            if layout[row, col] == UNCHANGED and grid.tree_fits(layout, row, col):
                layout[row, col] = TREE
                placed += 1
                break
        target += step
    return placed


def _strip_packing(grid: StreetGrid, columns: np.ndarray) -> np.ndarray:
    """[row, col] of the densest packing along one side's strip at the minimum spacing, in order along the street.

    The same row-by-row packing as StreetGrid.tree_capacity(), so the two sides' packings sum to the capacity.
    """
    layout = np.full(grid.shape, UNCHANGED, dtype=np.int8)
    for col in columns:
        for row in np.flatnonzero(grid.allowed[:, col, TREE]):
            if grid.tree_fits(layout, row, col):
                layout[row, col] = TREE
    trees = np.argwhere(layout == TREE)
    return trees[np.argsort(trees[:, 0], kind="stable")]


def _side_shares(total: int, capacities: list[int]) -> list[int]:
    """The budget split evenly between two sides, with what one side cannot hold moved to the other."""
    shares = [total - total // 2, total // 2]
    for i, j in ((0, 1), (1, 0)):
        excess = max(0, shares[i] - capacities[i])
        shares[i] -= excess
        shares[j] += excess
    return [min(share, capacity) for share, capacity in zip(shares, capacities)]


def _plant_packed_subset(grid: StreetGrid, layout: np.ndarray, packing: np.ndarray, count: int) -> int:
    """Plant `count` trees evenly chosen from a valid packing; any subset of it keeps the minimum spacing."""
    if count == 0 or len(packing) == 0:
        return 0
    picks = np.unique(np.floor(np.linspace(0, len(packing) - 1, min(count, len(packing))) + 0.5).astype(int))
    placed = 0
    for row, col in packing[picks]:
        if layout[row, col] == UNCHANGED and grid.tree_fits(layout, row, col):
            layout[row, col] = TREE
            placed += 1
    return placed


def design_guideline_layout(grid: StreetGrid, budget: Budget) -> np.ndarray:
    """Good street design practice at the same budget, with no optimisation.

    Trees: the budget split evenly between the plantable strips left and right of the centreline (a side that
    cannot hold its half passes the rest to the other), each side evenly spaced along the segment at no less
    than the IRC:SP:21 minimum spacing. Where buildings or existing canopy interrupt a strip so that even
    spacing cannot fit the side's share, the side instead takes evenly chosen positions from its densest
    packing, so the layout reaches the matched budget whenever the street can hold it. Coating: whole rows of
    coatable paving not under a new crown, a contiguous run of the widest rows along the street.
    """
    rows, cols = grid.shape
    layout = np.full(grid.shape, UNCHANGED, dtype=np.int8)
    half = cols // 2
    sides = [np.arange(0, half), np.arange(half, cols)]
    packings = [_strip_packing(grid, side) for side in sides]
    shares = _side_shares(budget.trees, [len(p) for p in packings])
    placed = 0
    for side, packing, share in zip(sides, packings, shares):
        attempt = layout.copy()
        spaced = _plant_side(grid, attempt, side, share)
        if spaced < share:
            attempt = layout.copy()
            spaced = _plant_packed_subset(grid, attempt, packing, share)
        layout[:] = attempt
        placed += spaced
    # Any trees an even spacing could not fit go on the first free plantable cells along either strip.
    for row, col in np.argwhere(grid.allowed[..., TREE]):
        if placed >= budget.trees:
            break
        if layout[row, col] == UNCHANGED and grid.tree_fits(layout, row, col):
            layout[row, col] = TREE
            placed += 1

    if budget.reflective_cells:
        canopy = grid.canopy_from(layout)
        coat = grid.allowed[..., REFLECTIVE] & ~canopy & (layout == UNCHANGED)
        widths = coat.sum(axis=1)
        if widths.max() > 0:
            typical = max(1, int(np.median(widths[widths > 0])))
            run = min(rows, math.ceil(budget.reflective_cells / typical))
            window_sums = np.convolve(widths, np.ones(run, dtype=int), mode="valid")
            first = int(np.argmax(window_sums))
            remaining = budget.reflective_cells
            for row in list(range(first, rows)) + list(range(first - 1, -1, -1)):
                for col in np.flatnonzero(coat[row]):
                    if remaining == 0:
                        break
                    layout[row, col] = REFLECTIVE
                    remaining -= 1
                if remaining == 0:
                    break
    return layout.ravel()
