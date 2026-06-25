"""
tests/test_api/test_upload.py

TDD tests for POST /api/v1/matches/{id}/upload-video.

Run with: pytest tests/test_api/test_upload.py -v
"""

import io
from unittest.mock import patch

import pytest

from database.models import Academy, Match


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def upload_match(db_session):
    """A fresh 'pending' match committed to the in-memory DB."""
    from sqlalchemy import select

    academy = db_session.execute(select(Academy)).scalar_one_or_none()
    if academy is None:
        academy = Academy(name="Upload FC", city="Abu Dhabi", country="UAE", tier="pro")
        db_session.add(academy)
        db_session.flush()

    match = Match(
        academy_id=academy.id,
        home_team="Upload Home",
        away_team="Upload Away",
        processing_status="pending",
        fps=25.0,
    )
    db_session.add(match)
    db_session.commit()
    return match


@pytest.fixture
def tmp_raw_dir(tmp_path, monkeypatch):
    """Redirect settings.raw_dir to a temp directory for the duration of the test."""
    from config.settings import settings
    monkeypatch.setattr(settings, "raw_dir", tmp_path)
    return tmp_path


def _mp4(content: bytes = b"fake mp4 bytes") -> dict:
    return {"file": ("match.mp4", io.BytesIO(content), "video/mp4")}


def _pdf() -> dict:
    return {"file": ("report.pdf", io.BytesIO(b"fake"), "application/pdf")}


# ---------------------------------------------------------------------------
# POST /api/v1/matches/{id}/upload-video
# ---------------------------------------------------------------------------

class TestUploadVideo:

    def test_returns_404_for_unknown_match(self, client):
        resp = client.post(
            "/api/v1/matches/00000000-0000-0000-0000-000000000000/upload-video",
            files=_mp4(),
        )
        assert resp.status_code == 404

    def test_returns_400_for_unsupported_format(self, client, upload_match):
        resp = client.post(
            f"/api/v1/matches/{upload_match.id}/upload-video",
            files=_pdf(),
        )
        assert resp.status_code == 400

    def test_returns_202_on_valid_upload(self, client, upload_match, tmp_raw_dir):
        with patch("api.routers.matches.process_match"):
            resp = client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files=_mp4(),
            )
        assert resp.status_code == 202

    def test_response_body_contains_match_id_and_status(self, client, upload_match, tmp_raw_dir):
        with patch("api.routers.matches.process_match"):
            data = client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files=_mp4(),
            ).json()
        assert data["match_id"] == str(upload_match.id)
        assert data["status"] == "processing"

    def test_file_bytes_written_to_raw_dir(self, client, upload_match, tmp_raw_dir):
        payload = b"this is the actual mp4 content"
        with patch("api.routers.matches.process_match"):
            client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files={"file": ("match.mp4", io.BytesIO(payload), "video/mp4")},
            )
        dest = tmp_raw_dir / f"{upload_match.id}.mp4"
        assert dest.exists(), "video file must be created in raw_dir"
        assert dest.read_bytes() == payload

    def test_accepts_non_mp4_extensions(self, client, upload_match, tmp_raw_dir):
        """mkv and avi are valid formats."""
        with patch("api.routers.matches.process_match"):
            resp = client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files={"file": ("clip.mkv", io.BytesIO(b"mkv bytes"), "video/x-matroska")},
            )
        assert resp.status_code == 202

    def test_sets_match_status_to_processing(
        self, client, upload_match, db_session, tmp_raw_dir
    ):
        with patch("api.routers.matches.process_match"):
            client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files=_mp4(),
            )
        db_session.expire_all()
        match = db_session.get(Match, upload_match.id)
        assert match.processing_status == "processing"

    def test_enqueues_process_match_task_with_correct_args(
        self, client, upload_match, tmp_raw_dir
    ):
        with patch("api.routers.matches.process_match") as mock_task:
            client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files=_mp4(),
            )
        mock_task.delay.assert_called_once_with(
            str(upload_match.id),
            str(upload_match.academy_id),
            upload_match.fps,
            upload_match.frame_width,
            upload_match.frame_height,
        )
