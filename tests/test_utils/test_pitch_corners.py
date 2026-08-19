"""
tests/test_utils/test_pitch_corners.py

Tests for utils/pitch_corners.corner_problem.

The orders that matter are the ones that are geometrically valid: cv2 fits them
without complaint and the only symptom is a mirrored or transposed pitch. Of the
24 permutations of four corners exactly one is right, so the test that carries
the most weight is the exhaustive one.

Run with: pytest tests/test_utils/test_pitch_corners.py -v
"""

import itertools

from utils.pitch_corners import corner_problem


# A real camera view: the near touchline is wider than the far one.
PERSPECTIVE = [(400.0, 300.0), (1500.0, 300.0), (1850.0, 1000.0), (70.0, 1000.0)]


class TestCornerProblem:

    def test_accepts_a_perspective_quad(self):
        assert corner_problem(PERSPECTIVE) is None

    def test_accepts_a_plain_rectangle(self):
        assert corner_problem(
            [(0.0, 0.0), (1920.0, 0.0), (1920.0, 1080.0), (0.0, 1080.0)]
        ) is None

    def test_accepts_exactly_one_of_the_24_orderings(self):
        # The property the whole module exists for. Winding alone would accept
        # four of them: the correct order plus its three rotations, which are
        # all clockwise too.
        good = [
            order for order in itertools.permutations(PERSPECTIVE)
            if corner_problem(list(order)) is None
        ]
        assert good == [tuple(PERSPECTIVE)]

    def test_rejects_the_same_quad_walked_in_reverse(self):
        # BL -> BR -> TR -> TL. Convex, right area, every corner a real pitch
        # corner — only the direction is wrong. Mirrors pitch width, so the left
        # wing's heatmap comes back on the right.
        assert "out of order" in corner_problem(list(reversed(PERSPECTIVE)))

    def test_rejects_the_180_degree_rotation(self):
        # BR -> BL -> TL -> TR. Clockwise, so the winding test passes it, but
        # it mirrors pitch LENGTH: x=0 lands on the far goal and a 4-2-3-1 is
        # reported as 1-3-2-4. This is the case the winding check alone missed.
        rotated = PERSPECTIVE[2:] + PERSPECTIVE[:2]
        assert "wrong corner" in corner_problem(rotated)

    def test_rejects_the_90_degree_rotations(self):
        # Also clockwise, and worse: these lay the 105 m goal-to-goal axis
        # across the frame's vertical extent, so formation clustering reads the
        # near-far touchline direction as depth.
        for shift in (1, 3):
            rotated = PERSPECTIVE[shift:] + PERSPECTIVE[:shift]
            assert "wrong corner" in corner_problem(rotated)

    def test_rejects_a_corner_that_is_not_a_point(self):
        # Match.pitch_corners is free-form JSON. This used to raise IndexError
        # past the caller, which scripts/run_pipeline.py does not catch.
        assert corner_problem([(1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0,)]) is not None
        assert corner_problem(
            [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0, 9.0)]
        ) is not None

    def test_rejects_a_bowtie(self):
        # BR and BL swapped: the quad crosses over itself.
        bowtie = [PERSPECTIVE[0], PERSPECTIVE[1], PERSPECTIVE[3], PERSPECTIVE[2]]
        assert "out of order" in corner_problem(bowtie)

    def test_rejects_collinear_corners(self):
        assert "collinear" in corner_problem(
            [(100.0, 100.0), (400.0, 400.0), (700.0, 700.0), (1000.0, 1000.0)]
        )

    def test_rejects_three_collinear_corners(self):
        assert "collinear" in corner_problem(
            [(100.0, 100.0), (500.0, 100.0), (900.0, 100.0), (500.0, 800.0)]
        )

    def test_rejects_duplicate_corners(self):
        assert corner_problem(
            [(400.0, 300.0), (400.0, 300.0), (1850.0, 1000.0), (70.0, 1000.0)]
        ) is not None

    def test_rejects_a_quad_too_small_to_be_a_pitch(self):
        assert "too small" in corner_problem(
            [(100.0, 100.0), (104.0, 100.0), (104.0, 104.0), (100.0, 104.0)]
        )

    def test_rejects_the_wrong_number_of_corners(self):
        assert corner_problem(PERSPECTIVE[:3]) is not None
        assert corner_problem(PERSPECTIVE + [(1.0, 1.0)]) is not None

    def test_accepts_lists_as_well_as_tuples(self):
        # The API hands it pydantic-parsed tuples; run_pipeline hands it lists.
        assert corner_problem([list(c) for c in PERSPECTIVE]) is None
