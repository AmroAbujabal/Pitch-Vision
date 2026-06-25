"""
tests/test_db/test_speed_zones_and_heatmap.py

TDD tests for:
  - metrics/physical.py  — speed zone breakdown
  - metrics/heatmap.py   — heatmap grid accumulation

Pure-function tests — no DB, no GPU, no cv2 required.

Run with: pytest tests/test_db/test_speed_zones_and_heatmap.py -v
"""

import numpy as np
import pytest

from metrics.physical import compute_physical_metrics, ZONE_WALK, ZONE_JOG, ZONE_RUN
from metrics.heatmap import compute_heatmap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _straight(n: int, speed: float, fps: float = 25.0, start=(0.0, 0.0)) -> np.ndarray:
    step = speed / fps
    xs = np.arange(n) * step + start[0]
    ys = np.full(n, start[1])
    return np.column_stack([xs, ys])


# ---------------------------------------------------------------------------
# Speed zones — compute_physical_metrics
# ---------------------------------------------------------------------------

class TestSpeedZones:

    def test_all_walking_gives_100_pct_walk(self):
        positions = _straight(100, 1.0)  # 1 m/s → walk
        m = compute_physical_metrics(1, positions, fps=25.0)
        assert m.speed_zones["walk_pct"] == pytest.approx(1.0, abs=0.01)
        assert m.speed_zones["sprint_pct"] == pytest.approx(0.0, abs=0.01)

    def test_all_sprinting_gives_100_pct_sprint(self):
        positions = _straight(100, 8.0)  # 8 m/s → sprint (≥ 7.0)
        m = compute_physical_metrics(1, positions, fps=25.0)
        assert m.speed_zones["sprint_pct"] == pytest.approx(1.0, abs=0.01)
        assert m.speed_zones["walk_pct"] == pytest.approx(0.0, abs=0.01)

    def test_zones_sum_to_one(self):
        walk_pos   = _straight(50, 1.0)
        sprint_pos = _straight(50, 8.0, start=(walk_pos[-1][0], 0.0))
        positions  = np.vstack([walk_pos, sprint_pos])
        m = compute_physical_metrics(1, positions, fps=25.0)
        total = sum(m.speed_zones.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_zone_keys_present(self):
        m = compute_physical_metrics(1, _straight(50, 3.0), fps=25.0)
        assert set(m.speed_zones.keys()) == {"walk_pct", "jog_pct", "run_pct", "sprint_pct"}

    def test_single_position_returns_zero_zones(self):
        positions = np.array([[0.0, 0.0]])
        m = compute_physical_metrics(1, positions, fps=25.0)
        assert all(v == 0.0 for v in m.speed_zones.values())

    def test_jog_speed_classified_correctly(self):
        # 3 m/s is between ZONE_WALK (2.0) and ZONE_JOG (4.0) → jog
        positions = _straight(100, 3.0)
        m = compute_physical_metrics(1, positions, fps=25.0)
        assert m.speed_zones["jog_pct"] == pytest.approx(1.0, abs=0.01)

    def test_run_speed_classified_correctly(self):
        # 5 m/s is between ZONE_JOG (4.0) and ZONE_RUN (7.0) → run
        positions = _straight(100, 5.0)
        m = compute_physical_metrics(1, positions, fps=25.0)
        assert m.speed_zones["run_pct"] == pytest.approx(1.0, abs=0.01)

    def test_mixed_activity_reflects_proportions(self):
        """50% walk + 50% sprint should give ~0.5 each."""
        walk_pos   = _straight(50, 1.0)
        sprint_pos = _straight(50, 8.0, start=(walk_pos[-1][0], 0.0))
        positions  = np.vstack([walk_pos, sprint_pos])
        m = compute_physical_metrics(1, positions, fps=25.0)
        # The speed array has n-1 entries; 49 walk speeds + 49 sprint = 98 total.
        # One transition frame makes it not exactly 50/50 but close.
        assert m.speed_zones["walk_pct"] == pytest.approx(0.5, abs=0.06)
        assert m.speed_zones["sprint_pct"] == pytest.approx(0.5, abs=0.06)


# ---------------------------------------------------------------------------
# Heatmap — compute_heatmap
# ---------------------------------------------------------------------------

class TestComputeHeatmap:

    def test_returns_required_keys(self):
        positions = np.array([[10.0, 5.0], [20.0, 10.0]])
        result = compute_heatmap(positions)
        assert "grid" in result
        assert "cols" in result
        assert "rows" in result
        assert "max_count" in result

    def test_grid_shape_matches_cols_rows(self):
        positions = np.random.rand(50, 2) * np.array([105.0, 68.0])
        result = compute_heatmap(positions, grid_cols=24, grid_rows=16)
        assert len(result["grid"]) == 16
        assert len(result["grid"][0]) == 24
        assert result["cols"] == 24
        assert result["rows"] == 16

    def test_empty_positions_returns_all_zeros(self):
        result = compute_heatmap(np.empty((0, 2)))
        for row in result["grid"]:
            assert all(v == 0 for v in row)
        assert result["max_count"] == 0

    def test_single_position_has_one_nonzero_cell(self):
        positions = np.array([[52.5, 34.0]])  # pitch centre
        result = compute_heatmap(positions, grid_cols=10, grid_rows=10,
                                 pitch_length=105.0, pitch_width=68.0)
        flat = [v for row in result["grid"] for v in row]
        nonzero = [v for v in flat if v > 0]
        assert len(nonzero) == 1
        assert nonzero[0] == pytest.approx(1.0, abs=0.01)

    def test_grid_values_sum_to_one_for_nonempty_positions(self):
        np.random.seed(42)
        positions = np.random.rand(200, 2) * np.array([105.0, 68.0])
        result = compute_heatmap(positions)
        total = sum(v for row in result["grid"] for v in row)
        assert total == pytest.approx(1.0, abs=1e-3)

    def test_max_count_reflects_densest_cell(self):
        # Cluster 90 points in one corner
        positions = np.vstack([
            np.full((90, 2), [1.0, 1.0]),
            np.full((10, 2), [100.0, 60.0]),
        ])
        result = compute_heatmap(positions)
        assert result["max_count"] == 90

    def test_positions_clamped_to_pitch_bounds(self):
        """Out-of-bounds positions should not cause index errors."""
        positions = np.array([[-5.0, -5.0], [200.0, 200.0], [52.5, 34.0]])
        result = compute_heatmap(positions, pitch_length=105.0, pitch_width=68.0)
        assert result["max_count"] >= 1  # at least the centre point registered
