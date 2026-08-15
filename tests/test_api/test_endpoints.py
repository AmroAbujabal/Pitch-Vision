"""
tests/test_api/test_endpoints.py

TDD tests for the three dashboard-facing API endpoints:
  GET /api/v1/matches/{id}/summary
  GET /api/v1/matches/{id}/players
  GET /api/v1/players/{id}/stats

Run with: pytest tests/test_api/test_endpoints.py -v
"""

import pytest


# ---------------------------------------------------------------------------
# GET /api/v1/matches/?academy_id=...
# ---------------------------------------------------------------------------

class TestListMatches:

    def test_returns_200(self, client, seeded):
        academy_id = seeded["academy"].id
        resp = client.get(f"/api/v1/matches/?academy_id={academy_id}")
        assert resp.status_code == 200

    def test_returns_list(self, client, seeded):
        academy_id = seeded["academy"].id
        data = client.get(f"/api/v1/matches/?academy_id={academy_id}").json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_match_fields_present(self, client, seeded):
        academy_id = seeded["academy"].id
        data = client.get(f"/api/v1/matches/?academy_id={academy_id}").json()
        row = next(r for r in data if r["id"] == str(seeded["match"].id))
        assert row["home_team"] == "Al Ain"
        assert row["away_team"] == "Al Jazira"
        assert row["processing_status"] == "done"

    def test_foreign_academy_id_in_query_is_ignored(self, client, seeded):
        """The listing is scoped by the bearer token. A client-supplied
        academy_id must not be able to select another academy's matches."""
        data = client.get(
            "/api/v1/matches/?academy_id=00000000-0000-0000-0000-000000000000"
        ).json()
        assert [r["id"] for r in data] == [str(seeded["match"].id)]

    def test_no_academy_id_needed(self, client, seeded):
        resp = client.get("/api/v1/matches/")
        assert resp.status_code == 200
        assert [r["id"] for r in resp.json()] == [str(seeded["match"].id)]


# ---------------------------------------------------------------------------
# GET /api/v1/matches/{id}/summary
# ---------------------------------------------------------------------------

class TestMatchSummary:

    def test_returns_200_for_existing_match(self, client, seeded):
        match_id = seeded["match"].id
        resp = client.get(f"/api/v1/matches/{match_id}/summary")
        assert resp.status_code == 200

    def test_returns_404_for_unknown_match(self, client, seeded):
        resp = client.get("/api/v1/matches/00000000-0000-0000-0000-000000000000/summary")
        assert resp.status_code == 404

    def test_response_contains_team_names(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/summary").json()
        assert data["home_team"] == "Al Ain"
        assert data["away_team"] == "Al Jazira"

    def test_player_count_correct(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/summary").json()
        assert data["player_count"] == 2

    def test_home_top_speed_is_maximum_across_home_players(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/summary").json()
        assert data["home_top_speed_ms"] == pytest.approx(9.4, rel=0.01)

    def test_away_top_speed_correct(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/summary").json()
        assert data["away_top_speed_ms"] == pytest.approx(8.9, rel=0.01)

    def test_home_press_count_is_sum_across_home_players(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/summary").json()
        assert data["home_press_count"] == 8

    def test_away_press_count_correct(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/summary").json()
        assert data["away_press_count"] == 4

    def test_home_pitch_control_is_mean_of_home_players(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/summary").json()
        assert data["home_pitch_control_pct"] == pytest.approx(0.58, rel=0.01)

    def test_processing_status_included(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/summary").json()
        assert data["processing_status"] == "done"


# ---------------------------------------------------------------------------
# GET /api/v1/matches/{id}/players
# ---------------------------------------------------------------------------

class TestMatchPlayers:

    def test_returns_200(self, client, seeded):
        match_id = seeded["match"].id
        resp = client.get(f"/api/v1/matches/{match_id}/players")
        assert resp.status_code == 200

    def test_returns_404_for_unknown_match(self, client, seeded):
        resp = client.get("/api/v1/matches/00000000-0000-0000-0000-000000000000/players")
        assert resp.status_code == 404

    def test_returns_all_players(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/players").json()
        assert len(data) == 2

    def test_each_row_has_player_name(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/players").json()
        names = {row["player_name"] for row in data}
        assert "Track 1" in names
        assert "Track 2" in names

    def test_each_row_has_team_label(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/players").json()
        teams = {row["team"] for row in data}
        assert "home" in teams
        assert "away" in teams

    def test_distance_covered_populated(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/players").json()
        home_row = next(r for r in data if r["team"] == "home")
        assert home_row["distance_covered_m"] == pytest.approx(9200.0, rel=0.01)

    def test_sprint_count_populated(self, client, seeded):
        match_id = seeded["match"].id
        data = client.get(f"/api/v1/matches/{match_id}/players").json()
        home_row = next(r for r in data if r["team"] == "home")
        assert home_row["sprint_count"] == 5


# ---------------------------------------------------------------------------
# GET /api/v1/players/{id}/stats
# ---------------------------------------------------------------------------

class TestPlayerStats:

    def test_returns_200_for_existing_player(self, client, seeded):
        player_id = seeded["home_player"].id
        resp = client.get(f"/api/v1/players/{player_id}/stats")
        assert resp.status_code == 200

    def test_returns_404_for_unknown_player(self, client, seeded):
        resp = client.get("/api/v1/players/00000000-0000-0000-0000-000000000000/stats")
        assert resp.status_code == 404

    def test_returns_one_entry_per_match(self, client, seeded):
        player_id = seeded["home_player"].id
        data = client.get(f"/api/v1/players/{player_id}/stats").json()
        assert len(data) == 1

    def test_match_context_included(self, client, seeded):
        player_id = seeded["home_player"].id
        data = client.get(f"/api/v1/players/{player_id}/stats").json()
        row = data[0]
        assert row["home_team"] == "Al Ain"
        assert row["away_team"] == "Al Jazira"

    def test_physical_metrics_in_response(self, client, seeded):
        player_id = seeded["home_player"].id
        data = client.get(f"/api/v1/players/{player_id}/stats").json()
        row = data[0]
        assert row["top_speed_ms"] == pytest.approx(9.4, rel=0.01)
        assert row["distance_covered_m"] == pytest.approx(9200.0, rel=0.01)
        assert row["sprint_count"] == 5

    def test_pressing_metrics_in_response(self, client, seeded):
        player_id = seeded["home_player"].id
        data = client.get(f"/api/v1/players/{player_id}/stats").json()
        row = data[0]
        assert row["press_count"] == 8
        assert row["press_success_rate"] == pytest.approx(0.625, rel=0.01)

    def test_pitch_control_in_response(self, client, seeded):
        player_id = seeded["home_player"].id
        data = client.get(f"/api/v1/players/{player_id}/stats").json()
        row = data[0]
        assert row["pitch_control_contribution"] == pytest.approx(0.58, rel=0.01)
