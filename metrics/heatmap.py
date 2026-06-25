"""
metrics/heatmap.py

Accumulates player pitch positions into a discretised occupancy grid.

Output is stored as JSON in PlayerMatchStats.heatmap_data and served by
GET /api/v1/players/{id}/heatmap — the dashboard renders it as a heat overlay.
"""

from __future__ import annotations

import numpy as np

from config.settings import settings

# Grid resolution (cells)
HEATMAP_COLS = 24   # along pitch length (x)
HEATMAP_ROWS = 16   # along pitch width  (y)


def compute_heatmap(
    pitch_positions: np.ndarray,
    grid_cols: int = HEATMAP_COLS,
    grid_rows: int = HEATMAP_ROWS,
    pitch_length: float | None = None,
    pitch_width: float | None = None,
) -> dict:
    """
    Accumulate (x, y) pitch positions into a 2-D occupancy grid.

    Args:
        pitch_positions: (N, 2) array of [x, y] in metres
        grid_cols:       number of columns (along pitch length axis)
        grid_rows:       number of rows    (along pitch width  axis)
        pitch_length:    pitch length in metres (defaults to settings value)
        pitch_width:     pitch width  in metres (defaults to settings value)

    Returns:
        dict with:
            "grid"      — list[list[float]] shape (grid_rows, grid_cols),
                          each cell is the fraction of frames the player
                          occupied that zone [0.0 – 1.0]
            "cols"      — int
            "rows"      — int
            "max_count" — int (raw peak cell count, useful for colour scaling)
    """
    pl = pitch_length if pitch_length is not None else settings.pitch_length
    pw = pitch_width  if pitch_width  is not None else settings.pitch_width

    counts = np.zeros((grid_rows, grid_cols), dtype=np.int32)

    if len(pitch_positions) > 0:
        xs = np.clip(pitch_positions[:, 0], 0, pl - 1e-9)
        ys = np.clip(pitch_positions[:, 1], 0, pw - 1e-9)

        col_idx = (xs / pl * grid_cols).astype(np.int32)
        row_idx = (ys / pw * grid_rows).astype(np.int32)

        for r, c in zip(row_idx, col_idx):
            counts[r, c] += 1

    total = int(counts.sum())
    if total > 0:
        grid_norm = (counts / total).round(5).tolist()
    else:
        grid_norm = counts.tolist()

    return {
        "grid":      grid_norm,
        "cols":      grid_cols,
        "rows":      grid_rows,
        "max_count": int(counts.max()),
    }
