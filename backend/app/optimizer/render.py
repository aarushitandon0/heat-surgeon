"""Plain matplotlib render of layouts on the design grid, for validating the optimizer. Not product UI."""

from pathlib import Path

import numpy as np

from app.optimizer.encoding import PERMEABLE, REFLECTIVE, TREE, Objectives, StreetGrid

SURFACE_GREYS = {0: 0.80, 1: 0.62, 2: 0.35, 3: 0.55, 4: 0.70, 5: 0.90}  # bare, canopy, built, carriageway, footway, water


def save_layout_figure(grid: StreetGrid, panels: list[tuple[str, np.ndarray, Objectives]], street_name: str,
                       path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    base = np.vectorize(SURFACE_GREYS.get)(grid.classes).astype(float)
    fig, axes = plt.subplots(1, len(panels), figsize=(4.2 * len(panels), 9.5), dpi=130)
    for ax, (title, genome, objectives) in zip(axes, panels):
        layout = np.asarray(genome).reshape(grid.shape)
        rgb = np.dstack([base, base, base])
        canopy = grid.canopy_from(layout)
        rgb[canopy] = (0.55, 0.78, 0.55)
        rgb[layout == REFLECTIVE] = (0.55, 0.80, 0.95)
        rgb[layout == PERMEABLE] = (0.85, 0.70, 0.45)
        ax.imshow(rgb, origin="lower", interpolation="nearest", aspect="equal")
        trees = np.argwhere(layout == TREE)
        ax.scatter(trees[:, 1], trees[:, 0], s=10, color="#1E5A1E")
        ax.set_title(f"{title}\n{objectives.temp_delta_c_low:+.2f} to {objectives.temp_delta_c_high:+.2f} °C",
                     fontsize=9, loc="left")
        ax.set_xlabel("Across street (2 m cells)")
        ax.set_ylabel("Along street (2 m cells)")
    fig.suptitle(f"{street_name}: matched budget layouts. Modelled surface temperature change, mean over the design "
                 "area (model output, not measurement). Grey: existing surface; green: new canopy; blue: reflective "
                 "coating.", fontsize=9, x=0.01, ha="left", wrap=True)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
