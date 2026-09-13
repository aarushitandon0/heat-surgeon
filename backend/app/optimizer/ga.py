"""Single-objective genetic algorithm (DEAP) over repaired street layouts (SPEC.md §6.3), and the Day 3 comparison CLI.

Fitness is scalarized from separate objectives, so the Tier 3 NSGA-II upgrade swaps the
selection operator, not the evaluation:

    fitness_score = temp_drop_c - cost_weight_c_per_inr * cost_inr_high

temp_drop_c is the conservative (least-cooling) end of the modelled band. Costs are not sourced
yet, so cost is None and the cost term is zero until they are.

Operators: tournament selection, two-point crossover, low-probability mutation to a random
allowed state, elitism. repair() runs after initialisation, after crossover and after mutation.

    python -m app.optimizer.ga --street pune-fc-road
"""

import argparse
import random
import sys
from dataclasses import dataclass

import numpy as np
from deap import base, creator, tools

from app.optimizer.encoding import STATE_NAMES, Budget, Objectives, StreetGrid

if not hasattr(creator, "LayoutFitness"):
    creator.create("LayoutFitness", base.Fitness, weights=(1.0,))
    creator.create("Layout", list, fitness=creator.LayoutFitness, objectives=None)


@dataclass(frozen=True)
class GAParams:
    population: int = 120
    generations: int = 400
    crossover_probability: float = 0.7
    mutation_probability: float = 0.3
    mutated_genes_mean: float = 2.0
    tournament_size: int = 3
    elite: int = 4
    cost_weight_c_per_inr: float = 0.0
    seed: int = 42


def fitness_score(objectives: Objectives, cost_weight_c_per_inr: float) -> float:
    """Dimensionless scalarized objective. Not a physical quantity; never display it as one."""
    cost_inr = objectives.cost_inr_high or 0.0
    return objectives.temp_drop_c - cost_weight_c_per_inr * cost_inr


@dataclass
class GARun:
    genome: np.ndarray
    objectives: Objectives
    best_score_by_generation: list[float]


def run_ga(grid: StreetGrid, budget: Budget, params: GAParams, seed_layouts: list[np.ndarray] | None = None) -> GARun:
    from app.optimizer.baselines import random_layout

    rng = np.random.default_rng(params.seed)
    random.seed(params.seed)
    flat_allowed = grid.allowed.reshape(-1, len(STATE_NAMES))
    actionable = np.flatnonzero(flat_allowed[:, 1:].any(axis=1))
    toolbox = base.Toolbox()

    def evaluate(individual) -> None:
        individual.objectives = grid.evaluate(np.asarray(individual, dtype=np.int8))
        individual.fitness.values = (fitness_score(individual.objectives, params.cost_weight_c_per_inr),)

    def repaired(individual) -> None:
        individual[:] = grid.repair(np.asarray(individual, dtype=np.int8), budget, rng).tolist()

    def mutate(individual) -> None:
        size = min(len(actionable), max(1, rng.poisson(params.mutated_genes_mean)))
        for gene in rng.choice(actionable, size=size, replace=False):
            states = np.flatnonzero(flat_allowed[gene])
            individual[gene] = int(rng.choice(states))

    population = []
    for layout in (seed_layouts or []):
        population.append(creator.Layout(np.asarray(layout).tolist()))
    while len(population) < params.population:
        population.append(creator.Layout(random_layout(grid, budget, rng).tolist()))
    for individual in population:
        repaired(individual)
        evaluate(individual)

    history = []
    for _ in range(params.generations):
        elite = [toolbox.clone(i) for i in tools.selBest(population, params.elite)]
        offspring = [toolbox.clone(i) for i in tools.selTournament(population, params.population - params.elite,
                                                                   tournsize=params.tournament_size)]
        for first, second in zip(offspring[::2], offspring[1::2]):
            if random.random() < params.crossover_probability:
                tools.cxTwoPoint(first, second)
                repaired(first)
                repaired(second)
                del first.fitness.values, second.fitness.values
        for individual in offspring:
            if random.random() < params.mutation_probability:
                mutate(individual)
                repaired(individual)
                del individual.fitness.values
        for individual in offspring:
            if not individual.fitness.valid:
                evaluate(individual)
        population = elite + offspring
        history.append(tools.selBest(population, 1)[0].fitness.values[0])

    best = tools.selBest(population, 1)[0]
    return GARun(genome=np.asarray(best, dtype=np.int8), objectives=best.objectives, best_score_by_generation=history)


def main(argv: list[str] | None = None) -> None:
    from pathlib import Path

    from app import config
    from app.data.fixtures import load_window
    from app.model.validate import calibrate
    from app.optimizer.baselines import greedy_layout, random_layout
    from app.optimizer.encoding import street_grid_for
    from app.optimizer.render import save_layout_figure

    parser = argparse.ArgumentParser(description="Compare the GA with random and greedy placement at matched budget.")
    parser.add_argument("--street", required=True)
    parser.add_argument("--trees", type=int, default=20)
    parser.add_argument("--reflective-cells", type=int, default=150)
    parser.add_argument("--generations", type=int, default=GAParams.generations)
    parser.add_argument("--population", type=int, default=GAParams.population)
    parser.add_argument("--ga-seeds", type=int, default=3)
    parser.add_argument("--random-seeds", type=int, default=30)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    window = load_window(args.street)
    run = calibrate(args.street)
    grid = street_grid_for(window, run.model)
    budget = Budget(trees=args.trees, reflective_cells=args.reflective_cells)
    dg = grid.design_grid

    print(f"Design grid  {args.street}: {dg.shape[0]} x {dg.shape[1]} cells at {dg.cell_size_m:.0f} m, "
          f"bearing {dg.bearing_deg:.1f}°, origin ({dg.origin_e_m:.1f}, {dg.origin_n_m:.1f}) {dg.crs}")
    print(f"Cross-section {grid.cross_section}")
    labels = {0: "bare", 1: "canopy", 2: "built", 3: "carriageway", 4: "footway", 5: "water"}
    print("Surfaces     " + ", ".join(f"{labels[k]} {int((grid.classes == k).sum())}" for k in labels))
    print("Allowed      " + ", ".join(f"{STATE_NAMES[s]} {int(grid.allowed[..., s].sum())}" for s in range(1, 5)))
    print(f"Budget       {budget.trees} trees, {budget.reflective_cells} reflective cells "
          f"({budget.reflective_cells * dg.cell_size_m ** 2:.0f} m²), {budget.permeable_cells} permeable cells")
    print("Delta        mean change in modelled surface temperature over the design area; low is more cooling")
    print()

    def describe(o: Objectives) -> str:
        return (f"{o.temp_delta_c_low:+.3f} to {o.temp_delta_c_high:+.3f} °C  "
                f"(trees {o.trees}, reflective {o.reflective_cells}, permeable {o.permeable_cells})")

    random_runs = [grid.evaluate(random_layout(grid, budget, np.random.default_rng(seed)))
                   for seed in range(args.random_seeds)]
    random_high = np.array([o.temp_delta_c_high for o in random_runs])
    random_example = random_layout(grid, budget, np.random.default_rng(0))
    greedy = greedy_layout(grid, budget)
    greedy_objectives = grid.evaluate(greedy)

    params = GAParams(generations=args.generations, population=args.population)
    ga_runs = []
    for seed in range(args.ga_seeds):
        ga_run = run_ga(grid, budget, GAParams(**{**params.__dict__, "seed": seed}))
        ga_runs.append(ga_run)
        h = ga_run.best_score_by_generation
        checkpoints = [0, len(h) // 4, len(h) // 2, 3 * len(h) // 4, len(h) - 1]
        print(f"GA seed {seed}  best fitness_score by generation " + ", ".join(f"g{i + 1} {h[i]:.4f}" for i in checkpoints))
    best_ga = min(ga_runs, key=lambda r: r.objectives.temp_delta_c_high)

    print()
    print(f"Random       mean of {args.random_seeds} seeds: high end {random_high.mean():+.3f} °C "
          f"(best {random_high.min():+.3f}, worst {random_high.max():+.3f}); seed 0: {describe(random_runs[0])}")
    print(f"Greedy       {describe(greedy_objectives)}")
    for seed, r in enumerate(ga_runs):
        print(f"GA seed {seed}    {describe(r.objectives)}")

    ga_high = best_ga.objectives.temp_delta_c_high
    beats_greedy = all(r.objectives.temp_delta_c_high < greedy_objectives.temp_delta_c_high for r in ga_runs)
    beats_random = all(r.objectives.temp_delta_c_high < random_high.min() for r in ga_runs)
    print()
    print(f"GA beats greedy on every seed: {beats_greedy}; GA beats the best of {args.random_seeds} random layouts on every seed: {beats_random}")
    print(f"Conservative cooling: random {-random_high.mean():.3f} °C, greedy {greedy_objectives.temp_drop_c:.3f} °C, "
          f"GA {-ga_high:.3f} °C")

    figure = config.BACKEND_DIR.parent / "docs" / "figures" / f"{args.street}-layouts.png"
    save_layout_figure(grid, [("Random (seed 0)", random_example, grid.evaluate(random_example)),
                              ("Greedy, hottest cell first", greedy, greedy_objectives),
                              (f"Genetic algorithm (best of {args.ga_seeds} seeds)", best_ga.genome, best_ga.objectives)],
                       window.manifest["name"], Path(figure))
    print(f"Figure       {Path(figure).relative_to(config.BACKEND_DIR.parent).as_posix()}")


if __name__ == "__main__":
    main()
