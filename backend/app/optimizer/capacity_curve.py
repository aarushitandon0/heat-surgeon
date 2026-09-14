"""Search margin over the design-guideline layout against tree budget, trees only, FC Road.

    cd backend && python -m app.optimizer.capacity_curve

Runs the same job runner the API uses (GA, population 120, 400 generations, seed 42, and the baselines) at
each tree budget from well under the street's capacity up to it, prints the table, and writes
docs/figures/capacity-curve.png. Reads fixtures only.
"""

from multiprocessing import Pool

from app import config

STREET_ID = "pune-fc-road"
BUDGET_STEP = 4
FIGURE_PATH = config.BACKEND_DIR.parent / "docs" / "figures" / "capacity-curve.png"


def _run(trees_max: int) -> dict:
    from app.contracts import OptimizeRequest
    from app.jobs import Job, run_job

    request = OptimizeRequest(trees_max=trees_max, reflective_cells_max=0, generations=400, population=120,
                              cost_weight_c_per_inr=0, run_baselines=True, seed=42)
    job = Job(job_id=f"capacity-{trees_max}", street_id=STREET_ID, request=request)
    run_job(job)
    if job.result is None:
        raise RuntimeError(job.messages[-1])
    arms = job.result.comparison
    return {
        "trees_max": trees_max,
        "ga_c": arms.ga.temp_delta_c_high, "ga_trees": arms.ga.trees,
        "guideline_c": arms.design_guideline.temp_delta_c_high, "guideline_trees": arms.design_guideline.trees,
        "random_c": arms.random.temp_delta_c_high, "random_trees": arms.random.trees,
    }


def main() -> None:
    from app import pipeline

    capacity = pipeline.street_context(STREET_ID).grid.tree_capacity()
    budgets = sorted({*range(BUDGET_STEP, capacity, BUDGET_STEP), capacity - 2, capacity})
    with Pool(min(len(budgets), 12)) as pool:
        rows = pool.map(_run, budgets)
    for row in rows:
        row["margin_percent"] = 100 * (row["ga_c"] / row["guideline_c"] - 1)

    print(f"{STREET_ID}, trees only, capacity {capacity} trees")
    print("trees_max  searched_c (trees)  guideline_c (trees)  random_c (trees)  margin_percent")
    for r in rows:
        print(f"{r['trees_max']:9d}  {r['ga_c']:+.3f} ({r['ga_trees']:2d})      {r['guideline_c']:+.3f} ({r['guideline_trees']:2d})"
              f"       {r['random_c']:+.3f} ({r['random_trees']:2d})    {r['margin_percent']:5.1f}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    ax.plot([r["trees_max"] for r in rows], [r["margin_percent"] for r in rows], marker="o", color="black")
    ax.axvline(capacity, color="grey", linestyle="--", linewidth=1)
    ax.text(capacity, ax.get_ylim()[1], f" capacity {capacity}", va="top", ha="right", color="grey")
    ax.set_xlabel("Tree budget (trees at most)")
    ax.set_ylabel("Search over design guideline, % more cooling")
    ax.set_title("FC Road, trees only: the search's edge shrinks to nothing at capacity\n"
                 "Modelled surface temperature, conservative end; GA seed 42, 400 generations", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_PATH)
    print(f"wrote {FIGURE_PATH}")


if __name__ == "__main__":
    main()
