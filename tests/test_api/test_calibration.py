"""
tests/test_api/test_calibration.py

Tests for PUT /api/v1/matches/{id}/calibration and the formations surfaced on
the match summary.

Run with: pytest tests/test_api/test_calibration.py -v
"""

from database.models import Match


# Four pitch corners in a 1920x1080 frame, ordered TL -> TR -> BR -> BL.
VALID_CORNERS = [[100.0, 400.0], [1820.0, 400.0], [1900.0, 1000.0], [20.0, 1000.0]]


def _put(client, match_id, **overrides):
    payload = {"pitch_corners": VALID_CORNERS, "home_defends_end": "low"}
    payload.update(overrides)
    return client.put(f"/api/v1/matches/{match_id}/calibration", json=payload)


# ---------------------------------------------------------------------------
# PUT /api/v1/matches/{id}/calibration
# ---------------------------------------------------------------------------

class TestSetCalibration:

    def test_stores_corners_and_defended_end(self, client, seeded, db_session):
        match_id = seeded["match"].id
        resp = _put(client, match_id)

        assert resp.status_code == 200
        assert resp.json() == {
            "pitch_corners": VALID_CORNERS,
            "home_defends_end": "low",
        }

        db_session.expire_all()
        match = db_session.get(Match, match_id)
        assert match.pitch_corners == VALID_CORNERS
        assert match.home_defends_end == "low"

    def test_overwrites_previous_calibration(self, client, seeded, db_session):
        match_id = seeded["match"].id
        _put(client, match_id, home_defends_end="low")
        _put(client, match_id, home_defends_end="high")

        db_session.expire_all()
        assert db_session.get(Match, match_id).home_defends_end == "high"

    def test_unknown_match_returns_404(self, client, seeded):
        resp = _put(client, "00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_rejects_wrong_number_of_corners(self, client, seeded):
        assert _put(client, seeded["match"].id,
                    pitch_corners=VALID_CORNERS[:3]).status_code == 422

    def test_rejects_corner_that_is_not_a_point(self, client, seeded):
        bad = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0, 9.0]]
        assert _put(client, seeded["match"].id,
                    pitch_corners=bad).status_code == 422

    def test_rejects_unknown_defended_end(self, client, seeded):
        assert _put(client, seeded["match"].id,
                    home_defends_end="sideways").status_code == 422

    def test_rejects_missing_defended_end(self, client, seeded):
        resp = client.put(
            f"/api/v1/matches/{seeded['match'].id}/calibration",
            json={"pitch_corners": VALID_CORNERS},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Formations on GET /api/v1/matches/{id}/summary
# ---------------------------------------------------------------------------

class TestSummaryFormations:

    def test_null_until_the_pipeline_writes_them(self, client, seeded):
        data = client.get(f"/api/v1/matches/{seeded['match'].id}/summary").json()
        assert data["home_formation"] is None
        assert data["away_formation"] is None

    def test_reports_detected_formations(self, client, seeded, db_session):
        match = db_session.get(Match, seeded["match"].id)
        match.home_formation = "4-3-3"
        match.away_formation = "unknown"
        db_session.commit()

        data = client.get(f"/api/v1/matches/{match.id}/summary").json()
        assert data["home_formation"] == "4-3-3"
        assert data["away_formation"] == "unknown"
