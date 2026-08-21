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
def upload_match(db_session, auth_academy):
    """
    A fresh 'pending' match committed to the in-memory DB, owned by the academy
    the fake token authenticates as — upload is scoped to the caller's academy.
    """
    from sqlalchemy import select

    academy = db_session.execute(select(Academy)).scalar_one_or_none()
    if academy is None:
        academy = Academy(name="Upload FC", city="Calgary", country="Canada", tier="pro")
        db_session.add(academy)
        db_session.flush()
    auth_academy["id"] = academy.id

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


class TestBrokerFailureDoesNotStrandTheMatch:
    """
    Regression: the status is committed as "processing" before the task is
    enqueued, so a broker that is down used to leave the match reading
    "processing" forever with nothing to pick it up. Found by clicking Upload
    on a machine with no Redis running.
    """

    def test_returns_503_when_the_task_cannot_be_queued(
        self, client, upload_match, tmp_raw_dir
    ):
        with patch("api.routers.matches.process_match") as mock_task:
            mock_task.delay.side_effect = OSError("no broker")
            resp = client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files=_mp4(),
            )
        assert resp.status_code == 503

    def test_match_is_marked_failed_not_left_processing(
        self, client, upload_match, tmp_raw_dir, db_session
    ):
        with patch("api.routers.matches.process_match") as mock_task:
            mock_task.delay.side_effect = OSError("no broker")
            client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files=_mp4(),
            )
        db_session.expire_all()
        match = db_session.get(Match, upload_match.id)
        assert match.processing_status == "failed"
        # The 503 tells the caller the video is on disk and to retry, which is
        # only true if the name was recorded too. Assigning video_path after
        # _enqueue_processing instead of before would lose it here and leave
        # reprocess reporting a file that is actually there as missing.
        assert match.video_path == f"{upload_match.id}.mp4"

    def test_the_saved_video_is_kept_so_the_upload_can_be_retried(
        self, client, upload_match, tmp_raw_dir
    ):
        with patch("api.routers.matches.process_match") as mock_task:
            mock_task.delay.side_effect = OSError("no broker")
            client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files=_mp4(b"kept"),
            )
        assert (tmp_raw_dir / f"{upload_match.id}.mp4").read_bytes() == b"kept"


# ---------------------------------------------------------------------------
# POST /api/v1/matches/{id}/reprocess
# ---------------------------------------------------------------------------

class TestReprocess:
    """
    Re-running the pipeline on the video already on disk, so calibration saved
    after an upload can actually take effect.
    """

    def test_returns_404_for_unknown_match(self, client, tmp_raw_dir):
        resp = client.post(
            "/api/v1/matches/00000000-0000-0000-0000-000000000000/reprocess"
        )
        assert resp.status_code == 404

    def test_returns_404_when_no_video_is_on_disk(
        self, client, upload_match, tmp_raw_dir
    ):
        resp = client.post(f"/api/v1/matches/{upload_match.id}/reprocess")
        assert resp.status_code == 404

    def test_returns_202_and_enqueues_when_the_video_exists(
        self, client, upload_match, tmp_raw_dir
    ):
        (tmp_raw_dir / f"{upload_match.id}.mp4").write_bytes(b"already uploaded")

        with patch("api.routers.matches.process_match") as mock_task:
            resp = client.post(f"/api/v1/matches/{upload_match.id}/reprocess")

        assert resp.status_code == 202
        assert resp.json()["status"] == "processing"
        mock_task.delay.assert_called_once_with(
            str(upload_match.id),
            str(upload_match.academy_id),
            upload_match.fps,
            upload_match.frame_width,
            upload_match.frame_height,
        )

    def test_finds_a_video_saved_under_any_allowed_extension(
        self, client, upload_match, tmp_raw_dir
    ):
        (tmp_raw_dir / f"{upload_match.id}.mov").write_bytes(b"quicktime")

        with patch("api.routers.matches.process_match"):
            resp = client.post(f"/api/v1/matches/{upload_match.id}/reprocess")
        assert resp.status_code == 202

    def test_broker_failure_marks_the_match_failed_not_processing(
        self, client, upload_match, tmp_raw_dir, db_session
    ):
        (tmp_raw_dir / f"{upload_match.id}.mp4").write_bytes(b"already uploaded")

        with patch("api.routers.matches.process_match") as mock_task:
            mock_task.delay.side_effect = OSError("no broker")
            resp = client.post(f"/api/v1/matches/{upload_match.id}/reprocess")

        assert resp.status_code == 503
        db_session.expire_all()
        assert db_session.get(Match, upload_match.id).processing_status == "failed"

    def test_returns_409_when_a_run_is_already_in_flight(
        self, client, upload_match, tmp_raw_dir, db_session
    ):
        (tmp_raw_dir / f"{upload_match.id}.mp4").write_bytes(b"already uploaded")
        upload_match.processing_status = "processing"
        db_session.commit()

        with patch("api.routers.matches.process_match") as mock_task:
            resp = client.post(f"/api/v1/matches/{upload_match.id}/reprocess")

        assert resp.status_code == 409
        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# Match.video_path
# ---------------------------------------------------------------------------

class TestUploadRecordsWhereTheVideoWent:
    """
    `Match.video_path` existed since the initial migration but was never
    assigned, so every reader had to guess the file name back from the match id
    and a list of extensions. Upload now records it.
    """

    def test_upload_stores_the_file_name(
        self, client, upload_match, tmp_raw_dir, db_session
    ):
        with patch("api.routers.matches.process_match"):
            client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files=_mp4(),
            )
        db_session.expire_all()
        match = db_session.get(Match, upload_match.id)
        assert match.video_path == f"{upload_match.id}.mp4"

    def test_the_stored_name_is_not_an_absolute_path(
        self, client, upload_match, tmp_raw_dir, db_session
    ):
        """
        raw_dir differs between this laptop and Cloud Run, so a stored absolute
        path would not survive the trip.
        """
        with patch("api.routers.matches.process_match"):
            client.post(
                f"/api/v1/matches/{upload_match.id}/upload-video",
                files={"file": ("clip.MOV", io.BytesIO(b"bytes"), "video/quicktime")},
            )
        db_session.expire_all()
        match = db_session.get(Match, upload_match.id)
        assert match.video_path == f"{upload_match.id}.mov"
        assert "/" not in match.video_path

    def test_reprocess_uses_the_recorded_name(
        self, client, upload_match, tmp_raw_dir, db_session
    ):
        """
        The recorded name is authoritative, not merely a faster way to reach the
        same guess. Deliberately a name the extension scan cannot derive from
        the match id: if this passed with a `{id}.mkv` file it would prove
        nothing, since the scan finds that too.
        """
        upload_match.video_path = "not-derivable-from-the-id.mkv"
        db_session.commit()
        (tmp_raw_dir / "not-derivable-from-the-id.mkv").write_bytes(b"recorded")

        with patch("api.routers.matches.process_match"):
            resp = client.post(f"/api/v1/matches/{upload_match.id}/reprocess")
        assert resp.status_code == 202

    def test_reprocess_404s_when_the_recorded_file_is_gone(
        self, client, upload_match, tmp_raw_dir, db_session
    ):
        """
        A stale name must not fall through to guessing and pick up an unrelated
        leftover file for the same match.
        """
        upload_match.video_path = f"{upload_match.id}.mkv"
        db_session.commit()
        (tmp_raw_dir / f"{upload_match.id}.mp4").write_bytes(b"a different upload")

        resp = client.post(f"/api/v1/matches/{upload_match.id}/reprocess")
        assert resp.status_code == 404

    def test_reprocess_still_works_for_matches_uploaded_before_this_column(
        self, client, upload_match, tmp_raw_dir
    ):
        """video_path is NULL for every row that predates it."""
        assert upload_match.video_path is None
        (tmp_raw_dir / f"{upload_match.id}.mp4").write_bytes(b"legacy upload")

        with patch("api.routers.matches.process_match"):
            resp = client.post(f"/api/v1/matches/{upload_match.id}/reprocess")
        assert resp.status_code == 202

    def test_a_directory_component_in_the_stored_name_cannot_escape_raw_dir(
        self, client, upload_match, tmp_raw_dir, db_session, tmp_path
    ):
        """
        Only upload writes this column today, from a UUID and an allowlisted
        suffix. This holds the line structurally so a future writer — an import
        or a manual DB fixup — cannot turn it into a traversal.
        """
        outside = tmp_path.parent / "outside.mp4"
        outside.write_bytes(b"not in raw_dir")
        upload_match.video_path = f"../{outside.name}"
        db_session.commit()

        resp = client.post(f"/api/v1/matches/{upload_match.id}/reprocess")
        assert resp.status_code == 404
