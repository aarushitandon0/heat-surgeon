"""Optimizer jobs: run the GA and baselines on a worker thread and record WebSocket messages (SPEC.md §6.5, §7).

Messages are recorded in order on the job; a WebSocket replays them from the start, so a late subscriber
sees the whole run. Progress is throttled at the source to PROGRESS_MIN_INTERVAL_S. layout_preview is set
only when the best layout improved since the last message sent, and is null otherwise.
"""

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field

import numpy as np

from app import config
from app.contracts import Comparison, OptimizationResult, OptimizeDone, OptimizeError, OptimizeJobHandle, OptimizeProgress, OptimizeRequest
from app.optimizer.encoding import STATE_NAMES


@dataclass
class Job:
    job_id: str
    street_id: str
    request: OptimizeRequest
    messages: list[dict] = field(default_factory=list)
    result: OptimizationResult | None = None
    finished: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, message) -> None:
        with self.lock:
            self.messages.append(message.model_dump(mode="json"))

    def messages_from(self, index: int) -> tuple[list[dict], bool]:
        with self.lock:
            return self.messages[index:], self.finished


JOBS: dict[str, Job] = {}


def run_job(job: Job) -> None:
    from app import pipeline
    from app.optimizer.baselines import design_guideline_layout, greedy_layout
    from app.optimizer.ga import GAParams, fitness_score, run_ga

    try:
        ctx = pipeline.street_context(job.street_id)
        grid = ctx.grid
        request = job.request
        budget = grid.matched(pipeline.budget_for(request))
        guideline = design_guideline_layout(grid, budget)
        params = GAParams(population=request.population, generations=request.generations,
                          cost_weight_c_per_inr=request.cost_weight_c_per_inr, seed=request.seed)
        state = {"last_sent": 0.0, "improved_since_sent": False}

        def on_generation(generation, genome, objectives, score, improved):
            state["improved_since_sent"] |= improved
            now = time.monotonic()
            final = generation == request.generations
            if not final and now - state["last_sent"] < config.PROGRESS_MIN_INTERVAL_S:
                return
            preview = grid.to_interventions(genome) if state["improved_since_sent"] else None
            job.record(OptimizeProgress(
                type="progress", job_id=job.job_id, generation=generation, generations_total=request.generations,
                best_fitness_score=score, best_temp_delta_c_low=objectives.temp_delta_c_low,
                best_temp_delta_c_high=objectives.temp_delta_c_high, best_cost_inr_low=objectives.cost_inr_low,
                best_cost_inr_high=objectives.cost_inr_high, layout_preview=preview))
            state["last_sent"], state["improved_since_sent"] = now, False

        # Not seeded with the guideline layout: seeding would guarantee the GA matches it, and the comparison is the claim.
        ga = run_ga(grid, budget, params, on_generation=on_generation)
        comparison = Comparison(
            random=pipeline.random_arm(grid, budget),
            greedy=pipeline.arm(grid.evaluate(greedy_layout(grid, budget))),
            design_guideline=pipeline.arm(grid.evaluate(guideline)),
            ga=pipeline.arm(ga.objectives),
        )
        job.result = pipeline.optimization_result(job.job_id, job.street_id, ga.genome, comparison)
        job.record(OptimizeDone(type="done", job_id=job.job_id, result_url=f"/api/job/{job.job_id}/result"))
    except Exception as error:  # noqa: BLE001 - surfaced to the client, never swallowed
        traceback.print_exc()
        job.record(OptimizeError(type="error", job_id=job.job_id, code=type(error).__name__, message=str(error)))
    finally:
        with job.lock:
            job.finished = True


def start_job(street_id: str, request: OptimizeRequest, background: bool = True) -> OptimizeJobHandle:
    from app import pipeline

    ctx = pipeline.street_context(street_id)   # fail fast on an uncached street, before a job exists
    pipeline.budget_for(request)               # fail fast on an unpriced rupee budget
    job = Job(job_id=uuid.uuid4().hex[:12], street_id=street_id, request=request)
    JOBS[job.job_id] = job
    if background:
        threading.Thread(target=run_job, args=(job,), daemon=True).start()
    else:
        run_job(job)
    rows, cols = ctx.grid.shape
    return OptimizeJobHandle(job_id=job.job_id, ws_url=f"/ws/optimize/{job.job_id}", grid_shape=(rows, cols),
                             cells=rows * cols, states_per_cell=len(STATE_NAMES), design_grid=ctx.grid.design_grid)
